"""OpenAI Codex CLI backend — runs `codex exec` as subprocess."""
from __future__ import annotations

import json
import logging
import re

from axon.backends.base import BackendResult
from axon.backends.registry import register
from axon.backends.subprocess_base import SUBSCRIPTION_USAGE, run_cli_subprocess
from axon.config import resolve_cli_timeout

log = logging.getLogger("axon.backend.codex")

# Codex doesn't support --json-schema, so we embed format instructions in the prompt
_FORMAT_WRAPPER = """
{prompt}

## OUTPUT FORMAT
You MUST output your response as valid JSON with exactly this structure:
{{"thinking": "your step-by-step reasoning", "answer": "your final answer"}}

If the task expects code, the "answer" field must contain ONLY raw executable Python code.
Do NOT include XML tags, markdown fences, or prose in the "answer" field.

Output ONLY the JSON object, nothing else.
"""


@register("codex-cli")
class CodexCLIBackend:
    name = "codex-cli"

    def __init__(self, config: dict) -> None:
        self._timeout = resolve_cli_timeout(config)
        self._model = config.get("codex_cli_model", "")

    def call(self, prompt: str, task: dict) -> BackendResult:
        wrapped_prompt = _FORMAT_WRAPPER.format(prompt=prompt).strip()

        # Prompt passed via stdin ("-" flag) to avoid OS arg-length limits
        cmd = ["codex", "exec", "-", "--full-auto"]
        if self._model:
            cmd.extend(["--model", self._model])

        stdout = run_cli_subprocess(
            label="Codex CLI",
            cmd=cmd,
            prompt=wrapped_prompt,
            timeout=self._timeout,
            log=log,
        )
        return _parse_response(stdout)

    def display_name(self) -> str:
        return f"codex-cli{f' ({self._model})' if self._model else ''}"


def _parse_response(stdout: str) -> BackendResult:
    """Parse Codex CLI output. Tries to extract JSON {thinking, answer}."""
    stdout = stdout.strip()
    if not stdout:
        raise RuntimeError("Codex CLI returned empty output")

    # Try direct JSON parse
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and "answer" in data:
            return BackendResult(
                thinking=data.get("thinking", ""),
                answer=data["answer"],
                usage=dict(SUBSCRIPTION_USAGE),
            )
    except json.JSONDecodeError:
        pass

    # JSON object with single-line "answer" value
    match = re.search(r'\{[^{}]*"answer"\s*:\s*"[^"]*"[^{}]*\}', stdout, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return BackendResult(
                thinking=data.get("thinking", ""),
                answer=data["answer"],
                usage=dict(SUBSCRIPTION_USAGE),
            )
        except json.JSONDecodeError:
            pass

    # Multi-line JSON extraction
    match = re.search(r'\{[\s\S]*?"thinking"[\s\S]*?"answer"[\s\S]*?\}', stdout)
    if match:
        try:
            data = json.loads(match.group())
            return BackendResult(
                thinking=data.get("thinking", ""),
                answer=data["answer"],
                usage=dict(SUBSCRIPTION_USAGE),
            )
        except json.JSONDecodeError:
            pass

    # Fallback: entire stdout as answer
    return BackendResult(
        thinking="",
        answer=stdout,
        usage=dict(SUBSCRIPTION_USAGE),
    )
