"""Tests for eval engine — registry, dispatch, error handling."""
import pytest
from axon_server.eval.engine import evaluate, register_evaluator, list_eval_types
from axon_server.eval.result import EvalResult


@pytest.mark.asyncio
async def test_evaluate_unknown_type():
    r = await evaluate("answer", "nonexistent_type", {})
    assert r.score == 0.0
    assert "Unsupported" in r.error


@pytest.mark.asyncio
async def test_evaluate_exception_handling():
    async def broken_eval(answer, config):
        raise RuntimeError("kaboom")

    register_evaluator("broken_test", broken_eval)
    r = await evaluate("answer", "broken_test", {})
    assert r.score == 0.0
    assert "kaboom" in r.error


def test_list_eval_types():
    types = list_eval_types()
    names = [t["eval_type"] for t in types]
    assert "exact_match" in names
    assert "numeric" in names
    assert "code_output" in names
    assert "contains" in names
    assert "regex" in names
    assert "llm_judge" in names


def test_list_eval_types_have_schemas():
    types = list_eval_types()
    builtin = [t for t in types if t["eval_type"] in ("exact_match", "numeric", "code_output", "contains", "regex", "llm_judge")]
    for t in builtin:
        assert "config_schema" in t
        assert t["config_schema"] is not None


@pytest.mark.asyncio
async def test_register_custom_evaluator():
    async def my_eval(answer, config):
        return EvalResult(score=99.0, details={"custom": True})

    register_evaluator("custom_test", my_eval, config_schema={"answer": "str"})
    r = await evaluate("hello", "custom_test", {})
    assert r.score == 99.0
    assert r.details["custom"] is True
