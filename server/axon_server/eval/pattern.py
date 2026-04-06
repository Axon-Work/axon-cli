import re

from axon_server.eval.result import EvalResult


async def eval_contains(answer: str, config: dict) -> EvalResult:
    """Check if answer contains required keywords. Score = fraction matched."""
    must_contain = config["must_contain"]  # list of strings
    case_sensitive = config.get("case_sensitive", False)

    check_answer = answer if case_sensitive else answer.lower()
    matched = []
    missed = []
    for keyword in must_contain:
        check_keyword = keyword if case_sensitive else keyword.lower()
        if check_keyword in check_answer:
            matched.append(keyword)
        else:
            missed.append(keyword)

    score = len(matched) / len(must_contain) if must_contain else 0.0
    return EvalResult(
        score=score,
        details={"matched": matched, "missed": missed, "total": len(must_contain)},
    )


async def eval_regex(answer: str, config: dict) -> EvalResult:
    """Match answer against regex pattern. Score = 1.0 if match, 0.0 otherwise."""
    pattern = config["pattern"]
    flags = re.IGNORECASE if not config.get("case_sensitive", False) else 0

    match = re.search(pattern, answer, flags)
    score = 1.0 if match else 0.0
    return EvalResult(
        score=score,
        details={"matched": bool(match), "pattern": pattern},
    )
