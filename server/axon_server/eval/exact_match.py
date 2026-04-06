from axon_server.eval.result import EvalResult


async def eval_exact_match(answer: str, config: dict) -> EvalResult:
    expected = config["expected"]
    case_sensitive = config.get("case_sensitive", False)
    strip_ws = config.get("strip_whitespace", True)

    a = answer.strip() if strip_ws else answer
    e = expected.strip() if strip_ws else expected

    if not case_sensitive:
        a = a.lower()
        e = e.lower()

    matched = a == e
    return EvalResult(
        score=1.0 if matched else 0.0,
        details={"matched": matched},
    )
