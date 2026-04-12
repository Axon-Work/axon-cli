"""Backend protocol and result type for mining LLM calls."""
from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class BackendResult(TypedDict):
    thinking: str
    answer: str
    usage: dict  # {billing_mode, tokens, cost_usd, total_tokens, prompt_tokens, completion_tokens, cost}


@runtime_checkable
class Backend(Protocol):
    name: str

    def call(self, prompt: str, task: dict) -> BackendResult:
        """Call the backend with a prompt and task context. Returns structured result."""
        ...

    def display_name(self) -> str:
        """Human-readable name for display in status lines."""
        ...
