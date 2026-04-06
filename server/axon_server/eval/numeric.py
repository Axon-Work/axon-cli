import re

from axon_server.eval.result import EvalResult


def _extract_number(text: str) -> float | None:
    """Extract the last number from text."""
    matches = re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text)
    if not matches:
        return None
    return float(matches[-1])


async def eval_numeric(answer: str, config: dict) -> EvalResult:
    expected = float(config["expected"])
    tolerance = float(config.get("tolerance", 0.0))

    parsed = _extract_number(answer)
    if parsed is None:
        return EvalResult(score=0.0, details={"error": "No number found in answer"})

    abs_error = abs(parsed - expected)

    scoring = config.get("scoring", "abs_error")
    if scoring == "within_tolerance":
        score = 1.0 if abs_error <= tolerance else 0.0
    else:
        # abs_error: negate so maximize = minimize error
        score = -abs_error

    return EvalResult(
        score=score,
        details={"parsed_value": parsed, "expected": expected, "abs_error": abs_error},
    )
