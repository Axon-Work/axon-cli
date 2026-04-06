"""Code execution: Modal sandbox (production) or subprocess (dev fallback).

Modal handles both CPU and GPU tasks — gpu parameter selects the resource.
"""
import os
import subprocess
import tempfile
from dataclasses import dataclass

MODAL_TOKEN_ID = os.environ.get("MODAL_TOKEN_ID", "")
MODAL_TOKEN_SECRET = os.environ.get("MODAL_TOKEN_SECRET", "")


@dataclass
class ExecResult:
    score: float | None
    stdout: str
    stderr: str
    error: str | None
    runtime_seconds: float = 0.0
    gpu_used: str | None = None


def run_code(
    code: str,
    setup_code: str,
    timeout: int = 30,
    score_prefix: str = "SCORE:",
    gpu: str | None = None,
    image_deps: list[str] | None = None,
) -> ExecResult:
    """Execute code and return result.

    Modal if credentials set, else local subprocess.
    gpu: None=CPU, "T4", "A100", "H100"
    image_deps: pip packages to install (e.g. ["torch", "numpy"])
    """
    if MODAL_TOKEN_ID and MODAL_TOKEN_SECRET:
        return _run_modal(code, setup_code, timeout, score_prefix, gpu, image_deps)
    if gpu:
        return ExecResult(score=None, stdout="", stderr="", error="GPU tasks require Modal (MODAL_TOKEN_ID not set)")
    return _run_subprocess(code, setup_code, timeout, score_prefix)


def _parse_score(stdout: str, score_prefix: str) -> float | None:
    for line in stdout.split("\n"):
        if line.startswith(score_prefix):
            try:
                return float(line[len(score_prefix):].strip())
            except ValueError:
                pass
    return None


def _run_modal(
    code: str,
    setup_code: str,
    timeout: int,
    score_prefix: str,
    gpu: str | None,
    image_deps: list[str] | None,
) -> ExecResult:
    import modal
    import time

    try:
        app = modal.App.lookup("axon-sandbox", create_if_missing=True)

        # Build image with dependencies
        image = modal.Image.debian_slim(python_version="3.12")
        if image_deps:
            image = image.pip_install(*image_deps)

        # Configure GPU
        gpu_config = None
        if gpu:
            gpu_map = {"T4": modal.gpu.T4(), "A100": modal.gpu.A100(), "H100": modal.gpu.H100()}
            gpu_config = gpu_map.get(gpu.upper())
            if gpu_config is None:
                return ExecResult(score=None, stdout="", stderr="", error=f"Unknown GPU type: {gpu}. Use T4, A100, or H100")

        # Define and run the sandbox function
        sandbox = modal.Sandbox.create(
            app=app,
            image=image,
            gpu=gpu_config,
            timeout=timeout + 30,
        )

        try:
            t0 = time.time()

            # Write files into sandbox
            sandbox.exec("bash", "-c", f"cat > /root/solution.py << 'SOLUTION_EOF'\n{code}\nSOLUTION_EOF")
            harness = f"from solution import *\n\n{setup_code}"
            sandbox.exec("bash", "-c", f"cat > /root/run.py << 'HARNESS_EOF'\n{harness}\nHARNESS_EOF")

            # Execute
            process = sandbox.exec("python3", "/root/run.py")
            process.wait()

            runtime = time.time() - t0
            stdout = process.stdout.read().strip()
            stderr = process.stderr.read().strip()
            returncode = process.returncode

            if returncode != 0:
                error_msg = stderr[-500:] if len(stderr) > 500 else stderr
                return ExecResult(
                    score=None, stdout=stdout[-200:], stderr=error_msg,
                    error=f"Code crashed: {error_msg}",
                    runtime_seconds=runtime, gpu_used=gpu,
                )

            score = _parse_score(stdout, score_prefix)
            if score is None:
                return ExecResult(
                    score=None, stdout=stdout[-500:], stderr=stderr[-200:],
                    error=f"No {score_prefix} found in output",
                    runtime_seconds=runtime, gpu_used=gpu,
                )

            return ExecResult(score=score, stdout=stdout[-500:], stderr="", error=None,
                              runtime_seconds=runtime, gpu_used=gpu)
        finally:
            sandbox.terminate()

    except Exception as e:
        return ExecResult(score=None, stdout="", stderr="", error=f"Modal sandbox error: {e}")


def _run_subprocess(code: str, setup_code: str, timeout: int, score_prefix: str) -> ExecResult:
    """Local subprocess — dev fallback, no isolation."""
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "solution.py"), "w") as f:
            f.write(code)
        harness_path = os.path.join(tmpdir, "run.py")
        with open(harness_path, "w") as f:
            f.write(f"from solution import *\n\n{setup_code}")

        t0 = time.time()
        try:
            result = subprocess.run(
                ["python3", harness_path],
                capture_output=True, text=True, timeout=timeout, cwd=tmpdir,
                env={"PATH": os.environ.get("PATH", ""), "HOME": tmpdir, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return ExecResult(score=None, stdout="", stderr="", error=f"Code timed out after {timeout}s",
                              runtime_seconds=time.time() - t0)

        runtime = time.time() - t0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            error_msg = stderr[-500:] if len(stderr) > 500 else stderr
            return ExecResult(score=None, stdout=stdout[-200:], stderr=error_msg,
                              error=f"Code crashed: {error_msg}", runtime_seconds=runtime)

        score = _parse_score(stdout, score_prefix)
        if score is None:
            return ExecResult(score=None, stdout=stdout[-500:], stderr=stderr[-200:],
                              error=f"No {score_prefix} found in output", runtime_seconds=runtime)

        return ExecResult(score=score, stdout=stdout[-500:], stderr="", error=None, runtime_seconds=runtime)
