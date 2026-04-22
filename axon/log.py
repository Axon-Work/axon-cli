"""Centralized logging — all errors auto-saved to ~/.axon/logs/."""
from __future__ import annotations

import logging
import sys
from types import TracebackType

from axon.config import AXON_HOME

LOG_DIR = AXON_HOME / "logs"
LOG_FILE = LOG_DIR / "axon.log"


def setup_logging() -> None:
    """Configure logging: errors go to file, always. Call once at startup."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers from leaking to stdout
    for name in ("LiteLLM", "litellm", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Also catch unhandled exceptions
    _original_excepthook = sys.excepthook

    def _excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if not issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            logging.getLogger("axon").critical(
                "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb),
            )
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


def get_logger(name: str = "axon") -> logging.Logger:
    return logging.getLogger(name)
