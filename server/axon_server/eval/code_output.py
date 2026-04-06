"""code_output evaluator — calls sandbox service or falls back to local subprocess."""
import os
import subprocess
import tempfile

import httpx

from axon_server.eval.result import EvalResult

# Sandbox service URL. If set, calls sandbox via HTTP. Otherwise local subprocess.
SANDBOX_URL = os.environ.get("AXON_SANDBOX_URL", "")


async def eval_code_output(answer: str, config: dict) -> EvalResult:
    """Run miner's code and parse output for score."""
    if SANDBOX_URL:
        return await _eval_via_sandbox(answer, config)
    return await _eval_subprocess(answer, config)


async def _eval_via_sandbox(answer: str, config: dict) -> EvalResult:
    """Call sandbox service via HTTP."""
    try:
        transport = httpx.AsyncHTTPTransport(proxy=None)
        async with httpx.AsyncClient(timeout=config.get("timeout", 30) + 30, transport=transport) as client:
            resp = await client.post(f"{SANDBOX_URL}/run", json={
                "code": answer,
                "setup_code": config["setup_code"],
                "timeout": config.get("timeout", 30),
                "score_prefix": config.get("score_prefix", "SCORE:"),
            })
            resp.raise_for_status()
            data = resp.json()

        if data.get("error"):
            return EvalResult(
                score=0.0,
                details={"stdout": data.get("stdout", ""), "stderr": data.get("stderr", "")},
                error=data["error"],
            )

        score = data.get("score")
        if score is None:
            return EvalResult(score=0.0, details={"stdout": data.get("stdout", "")}, error="No score returned")

        return EvalResult(score=score, details={"stdout": data.get("stdout", "")})

    except httpx.HTTPStatusError as e:
        return EvalResult(score=0.0, details={}, error=f"Sandbox HTTP error: {e.response.status_code}")
    except Exception as e:
        return EvalResult(score=0.0, details={}, error=f"Sandbox error: {e}")


async def _eval_subprocess(answer: str, config: dict) -> EvalResult:
    """Run in local subprocess — dev fallback, no isolation."""
    setup_code = config["setup_code"]
    timeout = config.get("timeout", 30)
    score_prefix = config.get("score_prefix", "SCORE:")

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "solution.py"), "w") as f:
            f.write(answer)
        harness_path = os.path.join(tmpdir, "run.py")
        with open(harness_path, "w") as f:
            f.write(f"from solution import *\n\n{setup_code}")

        try:
            result = subprocess.run(
                ["python3", harness_path],
                capture_output=True, text=True, timeout=timeout, cwd=tmpdir,
                env={"PATH": os.environ.get("PATH", ""), "HOME": tmpdir, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return EvalResult(score=0.0, details={"error": "timeout"}, error=f"Code timed out after {timeout}s")

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            error_msg = stderr[-500:] if len(stderr) > 500 else stderr
            return EvalResult(score=0.0, details={"stderr": error_msg}, error=f"Code crashed: {error_msg}")

        for line in stdout.split("\n"):
            if line.startswith(score_prefix):
                try:
                    score = float(line[len(score_prefix):].strip())
                    return EvalResult(score=score, details={"stdout": stdout[-500:]})
                except ValueError:
                    pass

        return EvalResult(
            score=0.0,
            details={"stdout": stdout[-500:], "stderr": stderr[-200:]},
            error=f"No {score_prefix} found in output",
        )
