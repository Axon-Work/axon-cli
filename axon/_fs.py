"""Atomic filesystem helpers for ~/.axon/ state files.

Why: `config.json`, `session/<id>.json`, `wallet.json` are rewritten in place.
A plain `Path.write_text()` truncates first, so a process crash between
truncate and write leaves an empty or half-written file. The helpers here
write to a sibling temp file, fsync, then `os.replace` — which is atomic
on POSIX/NT.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path | str, content: str, *, mode: int | None = None) -> None:
    """Write `content` to `path` atomically.

    Strategy: temp file in the same directory (same filesystem) → fsync → rename.
    If `mode` is given, chmod the temp file before the rename so the final
    file never briefly exists with permissive defaults.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path | str, data: Any, *, indent: int = 2,
                      mode: int | None = None) -> None:
    """JSON-encode and atomic-write. Trailing newline preserved."""
    atomic_write_text(
        path,
        json.dumps(data, indent=indent, default=str) + "\n",
        mode=mode,
    )


def atomic_append_jsonl(path: Path | str, record: Any) -> None:
    """Append one JSON record as a single line to a JSONL file.

    On POSIX, `open(..., 'a')` + one `write()` of size ≤ PIPE_BUF (usually
    4 KiB) is atomic. Records larger than that may tear under concurrent
    writers; `load_history()` already tolerates corrupt lines by skipping.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str) + "\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(line)
