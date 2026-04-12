"""Claude Code CLI backend — runs `claude -p` as subprocess."""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import signal
import subprocess
import time
from datetime import datetime

from axon.backends.base import BackendResult
from axon.backends.registry import register
from axon.config import resolve_cli_timeout

log = logging.getLogger("axon.backend.claude")
_STREAM_SAMPLE_LIMIT = 20
_STREAM_SAMPLE_BYTES = 240
_SUBSCRIPTION_USAGE = {
    "billing_mode": "subscription",
    "tokens": None,
    "cost_usd": None,
    "total_tokens": None,
    "prompt_tokens": None,
    "completion_tokens": None,
    "cost": None,
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _log_output_sample(stream_name: str, output: str):
    if not output:
        return
    lines = output.splitlines()
    for line_count, line in enumerate(lines[:_STREAM_SAMPLE_LIMIT], start=1):
        log.info("Claude CLI %s[%d]: %s", stream_name, line_count, line[:_STREAM_SAMPLE_BYTES])
    if len(lines) > _STREAM_SAMPLE_LIMIT:
        log.info("Claude CLI %s: further output truncated after %d lines", stream_name, _STREAM_SAMPLE_LIMIT)

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

    def __init__(self, config: dict):
        self._timeout = resolve_cli_timeout(config)
        self._model = config.get("claude_cli_model", "")

    def call(self, prompt: str, task: dict) -> BackendResult:
        eval_type = task.get("eval_type", "")
        tools = _TOOLS_BY_EVAL_TYPE.get(eval_type, _DEFAULT_TOOLS)
        system_prompt = _SYSTEM_PROMPTS.get(eval_type, _DEFAULT_SYSTEM)

        # Prompt is passed via stdin (no positional arg) to avoid OS arg-length limits.
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

        started_at = _now_iso()
        started_mono = time.monotonic()
        timeout_label = "none" if self._timeout is None else f"{self._timeout}s"
        log.info(
            "Claude CLI start started_at=%s eval_type=%s tools=%s timeout=%s prompt_chars=%d cmd=%s",
            started_at,
            eval_type,
            tools,
            timeout_label,
            len(prompt),
            shlex.join(cmd),
        )

        # Clear env vars that make Claude CLI refuse to run inside another session
        _blocked_env = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"}
        env = {k: v for k, v in os.environ.items() if k not in _blocked_env}

        # start_new_session creates a process group so we can kill all children
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True, env=env,
        )
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            stdout = _normalize_output(exc.stdout)
            stderr = _normalize_output(exc.stderr)
            _kill_process_group(proc)
            _log_output_sample("stdout", stdout)
            _log_output_sample("stderr", stderr)
            log.error(
                "Claude CLI timeout started_at=%s finished_at=%s duration_s=%.2f cmd=%s",
                started_at,
                _now_iso(),
                time.monotonic() - started_mono,
                shlex.join(cmd),
            )
            raise TimeoutError(f"Claude CLI timed out after {self._timeout}s") from None

        _log_output_sample("stdout", stdout)
        _log_output_sample("stderr", stderr)
        if proc.returncode != 0:
            log.error(
                "Claude CLI failed started_at=%s finished_at=%s duration_s=%.2f returncode=%s cmd=%s stderr=%s",
                started_at,
                _now_iso(),
                time.monotonic() - started_mono,
                proc.returncode,
                shlex.join(cmd),
                stderr[:1000],
            )
            raise RuntimeError(f"Claude CLI exited with code {proc.returncode}: {stderr[:500]}")

        if stderr:
            log.debug("Claude CLI stderr: %s", stderr[:500])

        log.info(
            "Claude CLI finished started_at=%s finished_at=%s duration_s=%.2f returncode=%s stdout_chars=%d stderr_chars=%d",
            started_at,
            _now_iso(),
            time.monotonic() - started_mono,
            proc.returncode,
            len(stdout),
            len(stderr),
        )

        return _parse_response(stdout)

    def display_name(self) -> str:
        return f"claude-cli{f' ({self._model})' if self._model else ''}"


def _kill_process_group(proc: subprocess.Popen):
    """Kill the process and its entire process group."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            log.warning("Process %d did not exit after SIGKILL", proc.pid)


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
        usage = _extract_usage(data)
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
        usage = _extract_usage(result_block)
    elif isinstance(data, dict):
        # Direct dict with thinking/answer keys
        return BackendResult(
            thinking=data.get("thinking", ""),
            answer=data.get("answer", str(data)),
            usage=dict(_SUBSCRIPTION_USAGE),
        )
    else:
        raise RuntimeError(f"Unexpected Claude CLI output type: {type(data)}")

    return _extract_answer(content, usage)


def _extract_usage(envelope: dict) -> dict:
    """Return subscription usage — Claude CLI is subscription-based, not metered."""
    return dict(_SUBSCRIPTION_USAGE)


def _extract_answer(content, usage: dict) -> BackendResult:
    """Parse the result field into thinking + answer."""
    # If content is already a dict, extract fields
    if isinstance(content, dict):
        return BackendResult(
            thinking=content.get("thinking", ""),
            answer=content.get("answer", str(content)),
            usage=usage,
        )

    text = str(content).strip()

    # Try 1: Parse as JSON object with thinking/answer
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

    # Try 2: Extract <thinking> and <answer> XML tags
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
