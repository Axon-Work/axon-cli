"""Tests for all eval types."""
import pytest
from axon_server.eval.exact_match import eval_exact_match
from axon_server.eval.numeric import eval_numeric
from axon_server.eval.pattern import eval_contains, eval_regex
from axon_server.eval.code_output import eval_code_output


# --- exact_match ---

@pytest.mark.asyncio
async def test_exact_match_hit():
    r = await eval_exact_match("42", {"expected": "42"})
    assert r.score == 1.0

@pytest.mark.asyncio
async def test_exact_match_miss():
    r = await eval_exact_match("41", {"expected": "42"})
    assert r.score == 0.0

@pytest.mark.asyncio
async def test_exact_match_case_insensitive():
    r = await eval_exact_match("Hello", {"expected": "hello", "case_sensitive": False})
    assert r.score == 1.0

@pytest.mark.asyncio
async def test_exact_match_strip_whitespace():
    r = await eval_exact_match("  42  \n", {"expected": "42", "strip_whitespace": True})
    assert r.score == 1.0


# --- numeric ---

@pytest.mark.asyncio
async def test_numeric_exact():
    r = await eval_numeric("3.14159", {"expected": 3.14159, "scoring": "abs_error"})
    assert abs(r.score) < 1e-5

@pytest.mark.asyncio
async def test_numeric_within_tolerance():
    r = await eval_numeric("3.14", {"expected": 3.14159, "tolerance": 0.01, "scoring": "within_tolerance"})
    assert r.score == 1.0

@pytest.mark.asyncio
async def test_numeric_outside_tolerance():
    r = await eval_numeric("3.0", {"expected": 3.14159, "tolerance": 0.01, "scoring": "within_tolerance"})
    assert r.score == 0.0

@pytest.mark.asyncio
async def test_numeric_extracts_last_number():
    r = await eval_numeric("The answer is approximately 42.5 degrees", {"expected": 42.5, "scoring": "abs_error"})
    assert abs(r.score) < 1e-5

@pytest.mark.asyncio
async def test_numeric_no_number():
    r = await eval_numeric("no numbers here", {"expected": 42})
    assert r.score == 0.0


# --- contains ---

@pytest.mark.asyncio
async def test_contains_all():
    r = await eval_contains("neural networks dream of light", {"must_contain": ["neural", "dream", "light"]})
    assert r.score == 1.0

@pytest.mark.asyncio
async def test_contains_partial():
    r = await eval_contains("neural networks are cool", {"must_contain": ["neural", "dream", "light"]})
    assert abs(r.score - 1/3) < 1e-6

@pytest.mark.asyncio
async def test_contains_none():
    r = await eval_contains("hello world", {"must_contain": ["neural", "dream"]})
    assert r.score == 0.0


# --- regex ---

@pytest.mark.asyncio
async def test_regex_match():
    r = await eval_regex("2024-01-15", {"pattern": r"\d{4}-\d{2}-\d{2}"})
    assert r.score == 1.0

@pytest.mark.asyncio
async def test_regex_no_match():
    r = await eval_regex("not a date", {"pattern": r"\d{4}-\d{2}-\d{2}"})
    assert r.score == 0.0


# --- code_output ---

@pytest.mark.asyncio
async def test_code_output_success():
    answer = "def solve():\n    return 42"
    setup = 'result = solve()\nprint(f"SCORE:{result}")'
    r = await eval_code_output(answer, {"setup_code": setup, "timeout": 10, "score_prefix": "SCORE:"})
    assert r.score == 42.0
    assert r.error is None

@pytest.mark.asyncio
async def test_code_output_crash():
    answer = "def solve():\n    raise ValueError('boom')"
    setup = 'result = solve()\nprint(f"SCORE:{result}")'
    r = await eval_code_output(answer, {"setup_code": setup, "timeout": 10, "score_prefix": "SCORE:"})
    assert r.score == 0.0
    assert r.error is not None

@pytest.mark.asyncio
async def test_code_output_triple_quote_conflict():
    """Miner code and setup both use triple quotes — should not conflict."""
    answer = '''import zlib

TEXT_COPY = """Hello world, this is a test."""

def compress(text: str) -> bytes:
    return zlib.compress(text.encode(), 9)

def decompress(data: bytes) -> str:
    return zlib.decompress(data).decode()
'''
    setup = '''import sys

TEXT = """Hello world, this is a test."""

try:
    compressed = compress(TEXT)
    decompressed = decompress(compressed)
    if decompressed != TEXT:
        print("ERROR: mismatch")
        sys.exit(1)
    print(f"SCORE:{-len(compressed)}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
'''
    r = await eval_code_output(answer, {"setup_code": setup, "timeout": 10, "score_prefix": "SCORE:"})
    assert r.error is None
    assert r.score < 0  # negative size


@pytest.mark.asyncio
async def test_code_output_timeout():
    answer = "import time\ndef solve():\n    time.sleep(100)\n    return 1"
    setup = 'result = solve()\nprint(f"SCORE:{result}")'
    r = await eval_code_output(answer, {"setup_code": setup, "timeout": 2, "score_prefix": "SCORE:"})
    assert r.score == 0.0
    assert "timed out" in r.error.lower()
