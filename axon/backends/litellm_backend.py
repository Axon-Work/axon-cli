"""LiteLLM backend — wraps existing call_llm() logic."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from axon.backends.base import BackendResult
from axon.backends.registry import register

log = logging.getLogger("axon.backend.litellm")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@register("litellm")
class LiteLLMBackend:
    name = "litellm"

    def __init__(self, config: dict):
        self._model = config.get("default_model", "anthropic/claude-sonnet-4-20250514")
        self._api_base = config.get("api_base", "")

    def call(self, prompt: str, task: dict) -> BackendResult:
        from axon.llm import call_llm
        started_at = _now_iso()
        started_mono = time.monotonic()
        log.info(
            "LiteLLM start started_at=%s model=%s prompt_chars=%d api_base=%s",
            started_at,
            self._model,
            len(prompt),
            self._api_base or "",
        )
        thinking, answer, usage = call_llm(prompt, self._model, self._api_base)
        log.info(
            "LiteLLM finished started_at=%s finished_at=%s duration_s=%.2f answer_chars=%d thinking_chars=%d total_tokens=%s cost=%s",
            started_at,
            _now_iso(),
            time.monotonic() - started_mono,
            len(answer or ""),
            len(thinking or ""),
            usage.get("total_tokens", 0),
            usage.get("cost", 0.0),
        )
        return BackendResult(thinking=thinking, answer=answer, usage=usage)

    def display_name(self) -> str:
        return self._model
