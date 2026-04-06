# Axon Sandbox

Isolated code execution service for the Axon platform.

## Quick Start

```bash
uv venv && uv pip install -e .

# Dev mode (local subprocess, no isolation)
uvicorn axon_sandbox.main:app --port 8001

# Production (E2B cloud sandbox)
E2B_API_KEY=your_key uvicorn axon_sandbox.main:app --port 8001
```

## API

### POST /run

Execute code in sandbox and return score.

```bash
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{"code": "def add(a,b): return a+b", "setup_code": "print(f\"SCORE:{add(1,2)}\")", "timeout": 10}'
```

Response:
```json
{"score": 3.0, "stdout": "SCORE:3", "stderr": "", "error": null}
```

### GET /health

```json
{"status": "ok"}
```

## How it works

1. Receives `code` (miner's solution) + `setup_code` (test harness)
2. Writes to `solution.py` and `run.py` (`from solution import *` + setup)
3. Executes in E2B sandbox or local subprocess
4. Parses `SCORE:` prefix from stdout
5. Returns score, stdout, stderr, error

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `E2B_API_KEY` | No | E2B sandbox key. Without it, uses local subprocess |

## License

MIT
