"""Backend registry and factory function."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    from axon.backends.base import Backend

_REGISTRY: dict[str, type] = {}

_T = TypeVar("_T", bound=type)


def register(name: str) -> Callable[[_T], _T]:
    """Decorator to register a backend class by name."""
    def wrapper(cls: _T) -> _T:
        _REGISTRY[name] = cls
        return cls
    return wrapper


def auto_detect_backend() -> str:
    """Pick the best available backend: claude-cli > codex-cli > litellm."""
    import shutil
    if shutil.which("claude"):
        return "claude-cli"
    if shutil.which("codex"):
        return "codex-cli"
    return "litellm"


def create_backend(backend_name: str, config: dict) -> Backend:
    """Create a backend instance by name.

    If backend_name is "auto", detect the best available CLI tool.
    Lazily imports backend modules so we don't pull in dependencies
    (litellm, subprocess, etc.) until actually needed.
    """
    if backend_name == "auto":
        backend_name = auto_detect_backend()

    # Ensure all backends are registered
    _ensure_loaded()

    if backend_name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"Unknown backend '{backend_name}'. Available: {available}")

    return _REGISTRY[backend_name](config)


_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Import backend modules to trigger @register decorators
    import axon.backends.litellm_backend  # noqa: F401
    import axon.backends.claude_cli  # noqa: F401
    import axon.backends.codex_cli  # noqa: F401
