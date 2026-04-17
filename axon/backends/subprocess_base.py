"""Shared helpers for subprocess-based CLI backends (claude-cli, codex-cli).

Both backends spawn an external CLI as a child process, feed the prompt via
stdin, enforce a timeout, log stdout/stderr samples, and normalize errors.
The mechanics are identical; only the command vector and response parsing
differ.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from datetime import datetime

_STREAM_SAMPLE_LIMIT = 20
_STREAM_SAMPLE_BYTES = 240

# Subscription-based backends don't report per-call metering; mining display
# treats this sentinel dict as "no cost data".
SUBSCRIPTION_USAGE: dict = {
    "billing_mode": "subscription",
    "tokens": None,
    "cost_usd": None,
    "total_tokens": None,
    "prompt_tokens": None,
    "completion_tokens": None,
    "cost": None,
}


def now_iso() -> str:
    """ISO-8601 timestamp in local timezone, seconds precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_output(output: str | bytes | None) -> str:
    """Decode bytes to str, replace undecodable bytes. None becomes ''."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def log_output_sample(log: logging.Logger, label: str, stream_name: str, output: str) -> None:
    """Emit up to `_STREAM_SAMPLE_LIMIT` lines of a stream for diagnostics."""
    if not output:
        return
    lines = output.splitlines()
    for line_count, line in enumerate(lines[:_STREAM_SAMPLE_LIMIT], start=1):
        log.info("%s %s[%d]: %s", label, stream_name, line_count, line[:_STREAM_SAMPLE_BYTES])
    if len(lines) > _STREAM_SAMPLE_LIMIT:
        log.info("%s %s: further output truncated after %d lines",
                 label, stream_name, _STREAM_SAMPLE_LIMIT)


def kill_process_group(proc: subprocess.Popen, log: logging.Logger) -> None:
    """Send SIGTERM → wait → SIGKILL to the process group.

    Works because the subprocess was started with `start_new_session=True`,
    giving it its own process group. Falls back to `proc.kill()` if the
    group lookup fails (e.g., child already exited).
    """
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


def run_cli_subprocess(
    *,
    label: str,
    cmd: list[str],
    prompt: str,
    timeout: int | None,
    log: logging.Logger,
    env: dict | None = None,
    start_ctx: dict | None = None,
) -> str:
    """Run a CLI subprocess, pipe prompt via stdin, enforce timeout, return stdout.

    `label` is used as a prefix in log lines (e.g., "Claude CLI").
    `start_ctx` is an optional dict of extra fields to log at start
    (e.g., eval_type, tools, model).

    Raises:
        TimeoutError: if the subprocess exceeds `timeout` seconds.
        RuntimeError: if the subprocess exits non-zero or produces no stdout.
    """
    started_at = now_iso()
    started_mono = time.monotonic()
    timeout_label = "none" if timeout is None else f"{timeout}s"

    extras = " ".join(f"{k}={v}" for k, v in (start_ctx or {}).items())
    log.info(
        "%s start started_at=%s timeout=%s prompt_chars=%d%s cmd=%s",
        label, started_at, timeout_label, len(prompt),
        (" " + extras) if extras else "",
        _shlex_join(cmd),
    )

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = normalize_output(exc.stdout)
        stderr = normalize_output(exc.stderr)
        kill_process_group(proc, log)
        log_output_sample(log, label, "stdout", stdout)
        log_output_sample(log, label, "stderr", stderr)
        log.error(
            "%s timeout started_at=%s finished_at=%s duration_s=%.2f cmd=%s",
            label, started_at, now_iso(),
            time.monotonic() - started_mono, _shlex_join(cmd),
        )
        raise TimeoutError(f"{label} timed out after {timeout}s") from None

    log_output_sample(log, label, "stdout", stdout)
    log_output_sample(log, label, "stderr", stderr)

    if proc.returncode != 0:
        log.error(
            "%s failed started_at=%s finished_at=%s duration_s=%.2f returncode=%s cmd=%s stderr=%s",
            label, started_at, now_iso(),
            time.monotonic() - started_mono, proc.returncode,
            _shlex_join(cmd), stderr[:1000],
        )
        raise RuntimeError(f"{label} exited with code {proc.returncode}: {stderr[:500]}")

    if stderr:
        log.debug("%s stderr: %s", label, stderr[:500])

    log.info(
        "%s finished started_at=%s finished_at=%s duration_s=%.2f returncode=%s "
        "stdout_chars=%d stderr_chars=%d",
        label, started_at, now_iso(),
        time.monotonic() - started_mono, proc.returncode,
        len(stdout), len(stderr),
    )
    return stdout


def _shlex_join(cmd: list[str]) -> str:
    import shlex
    return shlex.join(cmd)
