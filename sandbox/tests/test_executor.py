"""Tests for sandbox executor — subprocess fallback (no Modal key needed)."""
import pytest
from axon_sandbox.executor import _run_subprocess, _parse_score, ExecResult


def test_parse_score_found():
    assert _parse_score("hello\nSCORE:42.5\nbye", "SCORE:") == 42.5


def test_parse_score_not_found():
    assert _parse_score("no score here", "SCORE:") is None


def test_parse_score_invalid():
    assert _parse_score("SCORE:notanumber", "SCORE:") is None


def test_parse_score_negative():
    assert _parse_score("SCORE:-297.0", "SCORE:") == -297.0


def test_subprocess_success():
    r = _run_subprocess(
        "def solve(): return 42",
        'print(f"SCORE:{solve()}")',
        timeout=10, score_prefix="SCORE:",
    )
    assert r.score == 42.0
    assert r.error is None


def test_subprocess_crash():
    r = _run_subprocess(
        "def solve(): raise ValueError('boom')",
        'solve()',
        timeout=10, score_prefix="SCORE:",
    )
    assert r.score is None
    assert r.error is not None
    assert "crashed" in r.error.lower() or "ValueError" in r.error


def test_subprocess_timeout():
    r = _run_subprocess(
        "import time\ndef solve(): time.sleep(100)",
        'solve()',
        timeout=2, score_prefix="SCORE:",
    )
    assert r.score is None
    assert "timed out" in r.error.lower()


def test_subprocess_no_score():
    r = _run_subprocess(
        "def solve(): print('hello')",
        'solve()',
        timeout=10, score_prefix="SCORE:",
    )
    assert r.score is None
    assert "No SCORE:" in r.error


def test_subprocess_triple_quotes():
    """Miner code and setup both using triple quotes should not conflict."""
    r = _run_subprocess(
        'TEXT = """hello world"""\ndef compress(t): return t.encode()\ndef decompress(d): return d.decode()',
        'import sys\nTEXT = """hello world"""\nc = compress(TEXT)\nif decompress(c) != TEXT:\n    sys.exit(1)\nprint(f"SCORE:{-len(c)}")',
        timeout=10, score_prefix="SCORE:",
    )
    assert r.score is not None
    assert r.error is None


def test_subprocess_runtime_tracked():
    r = _run_subprocess("x = 1", 'print("SCORE:1")', timeout=10, score_prefix="SCORE:")
    assert r.runtime_seconds >= 0
    assert r.runtime_seconds < 5


def test_exec_result_gpu_field():
    r = ExecResult(score=1.0, stdout="ok", stderr="", error=None)
    assert r.gpu_used is None
    assert r.runtime_seconds == 0.0
