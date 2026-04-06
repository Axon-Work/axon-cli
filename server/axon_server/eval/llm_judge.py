import json
import os

import httpx

from axon_server.eval.result import EvalResult

# Server-side API key for LLM judge calls
JUDGE_API_KEY = os.environ.get("AXON_JUDGE_API_KEY", "")
JUDGE_API_BASE = os.environ.get("AXON_JUDGE_API_BASE", "https://api.anthropic.com")


async def eval_llm_judge(answer: str, config: dict) -> EvalResult:
    """Use an LLM to score the answer based on a rubric.

    eval_config:
        rubric: str — scoring criteria
        model: str — model to use (default: claude-sonnet-4-20250514)
        max_score: float — max possible score (default: 100)
    """
    rubric = config["rubric"]
    model = config.get("model", "claude-sonnet-4-20250514")
    max_score = config.get("max_score", 100.0)

    if not JUDGE_API_KEY:
        return EvalResult(score=0.0, details={}, error="Server LLM judge API key not configured (AXON_JUDGE_API_KEY)")

    prompt = f"""You are an expert evaluator. Score the following answer based on the rubric below.

## Rubric
{rubric}

## Answer to evaluate
{answer}

## Instructions
Return ONLY a JSON object with exactly these fields:
{{"score": <number from 0 to {max_score}>, "explanation": "<brief explanation>"}}

Return nothing else, just the JSON."""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{JUDGE_API_BASE}/v1/messages",
                headers={
                    "x-api-key": JUDGE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 256,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"].strip()

            # Parse JSON response
            result = json.loads(text)
            score = float(result["score"])
            explanation = result.get("explanation", "")

            return EvalResult(
                score=score,
                details={"explanation": explanation, "raw_response": text[:500]},
            )
    except httpx.HTTPStatusError as e:
        return EvalResult(score=0.0, details={}, error=f"LLM judge API error: {e.response.status_code}")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return EvalResult(score=0.0, details={"raw_response": text[:500] if 'text' in dir() else ""}, error=f"Failed to parse judge response: {e}")
    except Exception as e:
        return EvalResult(score=0.0, details={}, error=f"LLM judge error: {e}")
