"""Eval Plugin Engine — pluggable evaluation system.

Built-in eval types are registered at import time.
Third-party eval types can be registered via `register_evaluator()`.

Usage:
    from axon_server.eval.engine import evaluate, register_evaluator

    # Use built-in
    result = await evaluate("42", "exact_match", {"expected": "42"})

    # Register custom eval type
    async def my_eval(answer: str, config: dict) -> EvalResult:
        ...
    register_evaluator("my_custom", my_eval, config_schema={...})
"""
from typing import Any, Callable, Awaitable

from axon_server.eval.result import EvalResult

# Type for eval functions: async (answer, config) -> EvalResult
EvalFunc = Callable[[str, dict[str, Any]], Awaitable[EvalResult]]

# Registry: eval_type -> (eval_func, config_schema)
_registry: dict[str, tuple[EvalFunc, dict | None]] = {}


def register_evaluator(
    eval_type: str,
    func: EvalFunc,
    config_schema: dict | None = None,
):
    """Register an eval type. Overwrites if already registered."""
    _registry[eval_type] = (func, config_schema)


def list_eval_types() -> list[dict]:
    """List all registered eval types with their schemas."""
    return [
        {"eval_type": k, "config_schema": v[1]}
        for k, v in sorted(_registry.items())
    ]


async def evaluate(answer: str, eval_type: str, eval_config: dict) -> EvalResult:
    """Evaluate an answer using the registered eval type."""
    entry = _registry.get(eval_type)
    if entry is None:
        return EvalResult(score=0.0, details={}, error=f"Unsupported eval type: {eval_type}")
    func, _ = entry
    try:
        return await func(answer, eval_config)
    except Exception as e:
        return EvalResult(score=0.0, details={}, error=str(e))


# --- Register built-in eval types ---

from axon_server.eval.exact_match import eval_exact_match
from axon_server.eval.numeric import eval_numeric
from axon_server.eval.code_output import eval_code_output
from axon_server.eval.pattern import eval_contains, eval_regex
from axon_server.eval.llm_judge import eval_llm_judge

register_evaluator("exact_match", eval_exact_match, config_schema={
    "expected": "str (required)", "case_sensitive": "bool (default false)", "strip_whitespace": "bool (default true)",
})
register_evaluator("numeric", eval_numeric, config_schema={
    "expected": "float (required)", "tolerance": "float (default 0)", "scoring": "abs_error | within_tolerance",
})
register_evaluator("code_output", eval_code_output, config_schema={
    "setup_code": "str (required)", "timeout": "int (default 30)", "score_prefix": "str (default SCORE:)",
})
register_evaluator("contains", eval_contains, config_schema={
    "must_contain": "list[str] (required)", "case_sensitive": "bool (default false)",
})
register_evaluator("regex", eval_regex, config_schema={
    "pattern": "str (required)", "case_sensitive": "bool (default false)",
})
register_evaluator("llm_judge", eval_llm_judge, config_schema={
    "rubric": "str (required)", "model": "str (default claude-sonnet-4-20250514)", "max_score": "float (default 100)",
})
