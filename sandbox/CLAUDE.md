# CLAUDE.md — Axon Sandbox

## Overview

Isolated code execution service for Axon. Receives code via HTTP, runs it in E2B cloud sandbox (or local subprocess fallback), returns score + output.

## Architecture

```
Backend POST /api/tasks/{id}/submissions
  → eval/code_output.py calls sandbox service
    → POST http://sandbox:8001/run {code, setup_code, timeout}
    ← {score, stdout, stderr, error}
```

## API

### POST /run
```json
{
  "code": "def add(a,b): return a+b",
  "setup_code": "print(f'SCORE:{add(1,2)}')",
  "timeout": 30,
  "score_prefix": "SCORE:"
}
```
Response:
```json
{"score": 3.0, "stdout": "SCORE:3", "stderr": "", "error": null}
```

## Commands

```bash
uv venv && uv pip install -e .

# Dev (subprocess fallback)
uvicorn axon_sandbox.main:app --port 8001

# Production (E2B sandbox)
E2B_API_KEY=... uvicorn axon_sandbox.main:app --port 8001
```

## Environment

- `E2B_API_KEY` — E2B sandbox key. Without it, falls back to local subprocess.
