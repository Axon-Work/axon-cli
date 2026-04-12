"""OpenAI Codex CLI backend — runs `codex exec` as subprocess."""
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

log = logging.getLogger("axon.backend.codex")
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
        log.info("Codex CLI %s[%d]: %s", stream_name, line_count, line[:_STREAM_SAMPLE_BYTES])
    if len(lines) > _STREAM_SAMPLE_LIMIT:
        log.info("Codex CLI %s: further output truncated after %d lines", stream_name, _STREAM_SAMPLE_LIMIT)

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

    def __init__(self, config: dict):
        self._timeout = resolve_cli_timeout(config)
        self._model = config.get("codex_cli_model", "")

    def call(self, prompt: str, task: dict) -> BackendResult:
        wrapped_prompt = _FORMAT_WRAPPER.format(prompt=prompt).strip()

        # Prompt passed via stdin ("-" flag) to avoid OS arg-length limits
        cmd = ["codex", "exec", "-", "--full-auto"]
        if self._model:
            cmd.extend(["--model", self._model])

        started_at = _now_iso()
        started_mono = time.monotonic()
        timeout_label = "none" if self._timeout is None else f"{self._timeout}s"
        log.info(
            "Codex CLI start started_at=%s timeout=%s prompt_chars=%d cmd=%s",
            started_at,
            timeout_label,
            len(wrapped_prompt),
            shlex.join(cmd),
        )

        # start_new_session creates a process group so we can kill all children
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(input=wrapped_prompt, timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            stdout = _normalize_output(exc.stdout)
            stderr = _normalize_output(exc.stderr)
            _kill_process_group(proc)
            _log_output_sample("stdout", stdout)
            _log_output_sample("stderr", stderr)
            log.error(
                "Codex CLI timeout started_at=%s finished_at=%s duration_s=%.2f cmd=%s",
                started_at,
                _now_iso(),
                time.monotonic() - started_mono,
                shlex.join(cmd),
            )
            raise TimeoutError(f"Codex CLI timed out after {self._timeout}s")

        _log_output_sample("stdout", stdout)
        _log_output_sample("stderr", stderr)
        if proc.returncode != 0:
            log.error(
                "Codex CLI failed started_at=%s finished_at=%s duration_s=%.2f returncode=%s cmd=%s stderr=%s",
                started_at,
                _now_iso(),
                time.monotonic() - started_mono,
                proc.returncode,
                shlex.join(cmd),
                stderr[:1000],
            )
            raise RuntimeError(f"Codex CLI exited with code {proc.returncode}: {stderr[:500]}")

        if stderr:
            log.debug("Codex CLI stderr: %s", stderr[:500])

        log.info(
            "Codex CLI finished started_at=%s finished_at=%s duration_s=%.2f returncode=%s stdout_chars=%d stderr_chars=%d",
            started_at,
            _now_iso(),
            time.monotonic() - started_mono,
            proc.returncode,
            len(stdout),
            len(stderr),
        )

        return _parse_response(stdout)

    def display_name(self) -> str:
        return f"codex-cli{f' ({self._model})' if self._model else ''}"


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
        proc.wait(timeout=3)


def _parse_response(stdout: str) -> BackendResult:
    """Parse Codex CLI output. Tries to extract JSON {thinking, answer}."""
    stdout = stdout.strip()
    if not stdout:
        raise RuntimeError("Codex CLI returned empty output")

    # Try to parse as JSON directly
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and "answer" in data:
            return BackendResult(
                thinking=data.get("thinking", ""),
                answer=data["answer"],
                usage=dict(_SUBSCRIPTION_USAGE),
            )
    except json.JSONDecodeError:
        pass

    # Try to find JSON object within the output
    match = re.search(r'\{[^{}]*"answer"\s*:\s*"[^"]*"[^{}]*\}', stdout, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return BackendResult(
                thinking=data.get("thinking", ""),
                answer=data["answer"],
                usage=dict(_SUBSCRIPTION_USAGE),
            )
        except json.JSONDecodeError:
            pass

    # Try more aggressive JSON extraction with multiline
    match = re.search(r'\{[\s\S]*?"thinking"[\s\S]*?"answer"[\s\S]*?\}', stdout)
    if match:
        try:
            data = json.loads(match.group())
            return BackendResult(
                thinking=data.get("thinking", ""),
                answer=data["answer"],
                usage=dict(_SUBSCRIPTION_USAGE),
            )
        except json.JSONDecodeError:
            pass

    # Fallback: treat entire output as answer
    return BackendResult(
        thinking="",
        answer=stdout,
        usage=dict(_SUBSCRIPTION_USAGE),
    )
