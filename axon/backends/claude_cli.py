"""Claude Code CLI backend — runs `claude -p` as subprocess."""
from __future__ import annotations

import json
import logging
import os
import re

from axon.backends.base import BackendResult
from axon.backends.registry import register
from axon.backends.subprocess_base import SUBSCRIPTION_USAGE, run_cli_subprocess
from axon.config import resolve_cli_timeout

log = logging.getLogger("axon.backend.claude")

# Tool sets by eval_type
_TOOLS_BY_EVAL_TYPE = {
    "code_output": "Bash,Read,Write,Grep,Glob",
    "llm_judge": "Read,WebSearch,WebFetch,Grep,Glob",
}
_DEFAULT_TOOLS = "Read,WebSearch,Grep,Glob"

# System prompts include output format instructions (no --json-schema, which
# conflicts with agentic multi-turn tool use and can cause infinite retries).
_SYSTEM_PROMPTS = {
    "code_output": (
        "You are solving a coding task. Write executable code that produces the correct output. "
        "Use Bash to test your code before submitting your final answer. "
        "Iterate until tests pass.\n\n"
        "YOUR FINAL MESSAGE must contain ONLY raw executable Python code.\n"
        "Do NOT wrap it in <answer> tags. Do NOT use markdown fences. Do NOT add explanation.\n"
        "The evaluator writes your submission directly to solution.py and executes it."
    ),
    "llm_judge": (
        "You are solving a research/reasoning task. Use WebSearch and WebFetch to find "
        "accurate information. Verify facts before submitting. "
        "Provide a thorough, well-reasoned answer in your final message."
    ),
}
_DEFAULT_SYSTEM = (
    "You are solving a task. Use available tools to research and verify your answer. "
    "Be thorough and accurate. Put your final answer in your last message."
)


@register("claude-cli")
class ClaudeCLIBackend:
    name = "claude-cli"

    def __init__(self, config: dict) -> None:
        self._timeout = resolve_cli_timeout(config)
        self._model = config.get("claude_cli_model", "")

    def call(self, prompt: str, task: dict) -> BackendResult:
        eval_type = task.get("eval_type", "")
        tools = _TOOLS_BY_EVAL_TYPE.get(eval_type, _DEFAULT_TOOLS)
        system_prompt = _SYSTEM_PROMPTS.get(eval_type, _DEFAULT_SYSTEM)

        # Prompt passed via stdin (no positional arg) to avoid OS arg-length limits.
        # No --json-schema: it conflicts with agentic tool-use and causes hangs.
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--allowedTools", tools,
            "--system-prompt", system_prompt,
            "--dangerously-skip-permissions",
        ]
        if self._model:
            cmd.extend(["--model", self._model])

        # Claude CLI refuses to run inside an existing Claude Code session
        _blocked_env = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"}
        env = {k: v for k, v in os.environ.items() if k not in _blocked_env}

        stdout = run_cli_subprocess(
            label="Claude CLI",
            cmd=cmd,
            prompt=prompt,
            timeout=self._timeout,
            log=log,
            env=env,
            start_ctx={"eval_type": eval_type, "tools": tools},
        )
        return _parse_response(stdout)

    def display_name(self) -> str:
        return f"claude-cli{f' ({self._model})' if self._model else ''}"


def _parse_response(stdout: str) -> BackendResult:
    """Parse Claude CLI JSON output.

    `claude -p --output-format json` returns a single JSON object:
      {type: "result", result: "...", total_cost_usd: ..., usage: {...}}
    """
    stdout = stdout.strip()
    if not stdout:
        raise RuntimeError("Claude CLI returned empty output")

    data = json.loads(stdout)

    # Extract the result text and usage from the response envelope
    if isinstance(data, dict) and data.get("type") == "result":
        content = data.get("result", "")
        usage = dict(SUBSCRIPTION_USAGE)
    elif isinstance(data, list):
        # Fallback: older array format [{type:"system",...}, {type:"result",...}]
        result_block = None
        for block in data:
            if isinstance(block, dict) and block.get("type") == "result":
                result_block = block
                break
        if result_block is None:
            raise RuntimeError("No result block found in Claude CLI output")
        content = result_block.get("result", "")
        usage = dict(SUBSCRIPTION_USAGE)
    elif isinstance(data, dict):
        # Direct dict with thinking/answer keys
        return BackendResult(
            thinking=data.get("thinking", ""),
            answer=data.get("answer", str(data)),
            usage=dict(SUBSCRIPTION_USAGE),
        )
    else:
        raise RuntimeError(f"Unexpected Claude CLI output type: {type(data)}")

    return _extract_answer(content, usage)


def _extract_answer(content: object, usage: dict) -> BackendResult:
    """Parse the result field into thinking + answer."""
    if isinstance(content, dict):
        return BackendResult(
            thinking=content.get("thinking", ""),
            answer=content.get("answer", str(content)),
            usage=usage,
        )

    text = str(content).strip()

    # Try 1: JSON object with thinking/answer
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "answer" in parsed:
            return BackendResult(
                thinking=parsed.get("thinking", ""),
                answer=parsed["answer"],
                usage=usage,
            )
    except (json.JSONDecodeError, TypeError):
        pass

    # Try 2: <thinking> and <answer> XML tags
    think_match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
    answer_match = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)
    if answer_match:
        return BackendResult(
            thinking=think_match.group(1).strip() if think_match else "",
            answer=answer_match.group(1).strip(),
            usage=usage,
        )

    # Try 3: Strip markdown fences (common in code responses)
    cleaned = re.sub(r"^```[\w]*\s*\n?", "", text)
    cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned)

    return BackendResult(thinking="", answer=cleaned.strip(), usage=usage)
