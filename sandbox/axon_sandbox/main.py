from fastapi import FastAPI
from pydantic import BaseModel

from axon_sandbox.executor import run_code

app = FastAPI(title="Axon Sandbox", version="0.2.0")


class RunRequest(BaseModel):
    code: str
    setup_code: str
    timeout: int = 30
    score_prefix: str = "SCORE:"
    gpu: str | None = None          # None=CPU, "T4", "A100", "H100"
    image_deps: list[str] | None = None  # pip packages: ["torch", "numpy"]


class RunResponse(BaseModel):
    score: float | None
    stdout: str
    stderr: str
    error: str | None
    runtime_seconds: float = 0.0
    gpu_used: str | None = None


@app.post("/run", response_model=RunResponse)
def execute(req: RunRequest):
    result = run_code(
        req.code, req.setup_code, req.timeout, req.score_prefix,
        gpu=req.gpu, image_deps=req.image_deps,
    )
    return RunResponse(
        score=result.score, stdout=result.stdout, stderr=result.stderr,
        error=result.error, runtime_seconds=result.runtime_seconds, gpu_used=result.gpu_used,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
