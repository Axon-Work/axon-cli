from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    score: float
    details: dict[str, Any]
    error: str | None = None
