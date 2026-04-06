# CLAUDE.md — Axon Backend

## Overview

FastAPI backend for the Axon Proof of Useful Work bounty platform. Handles auth, task management, submission evaluation, and tokenomics.

## Structure

```
axon-server/
├── axon_server/
│   ├── main.py         # FastAPI app with lifespan
│   ├── config.py       # pydantic-settings, env prefix AXON_
│   ├── database.py     # async engine + session
│   ├── models.py       # ORM: User, Task, Submission, MintState, Transaction
│   ├── schemas.py      # Pydantic request/response models
│   ├── auth.py         # JWT + bcrypt (not passlib — incompatible with bcrypt 5.x)
│   ├── rewards.py      # PoUW tokenomics engine (THE CORE)
│   ├── routers/
│   │   ├── users.py        # /api/auth/* + /api/transactions
│   │   ├── tasks.py        # /api/tasks/* + /api/mint
│   │   └── submissions.py  # /api/tasks/{id}/submissions/* + leaderboard
│   └── eval/
│       ├── result.py       # EvalResult dataclass (avoid circular imports)
│       ├── engine.py       # Dispatcher by eval_type
│       ├── exact_match.py  # String comparison
│       ├── numeric.py      # Number extraction + abs_error
│       ├── pattern.py      # contains (keyword check) + regex
│       ├── code_output.py  # Subprocess sandbox runner
│       └── llm_judge.py    # Server-side LLM scoring
├── alembic/                # Database migrations
├── alembic.ini
├── tokenomics.md           # Full tokenomics specification
├── Dockerfile
└── pyproject.toml
```

## Tech stack

- Python 3.11+ / FastAPI / SQLAlchemy 2.0 async / asyncpg / PostgreSQL / Alembic
- Auth: JWT via python-jose, passwords via bcrypt
- Eval: subprocess sandbox for code_output, httpx for llm_judge

## Commands

```bash
# Install
uv pip install -e .

# Start server
uvicorn axon_server.main:app --host 127.0.0.1 --port 8000

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Recreate DB (dev only)
dropdb -U kawl --if-exists axon && createdb -U kawl axon
```

## Environment variables

- `AXON_DATABASE_URL` — PostgreSQL connection (default: `postgresql+asyncpg://kawl@localhost:5432/axon`)
- `AXON_JWT_SECRET` — JWT signing secret (change in production)
- `AXON_JUDGE_API_KEY` — API key for llm_judge eval type

## API endpoints

### Auth
- `POST /api/auth/register` — create account (grants starter coins)
- `POST /api/auth/login` — returns JWT
- `GET /api/auth/me` — profile + balance

### Tasks
- `POST /api/tasks` — create task + burn $AXN
- `GET /api/tasks` — list (filterable by status)
- `GET /api/tasks/{id}` — detail
- `PATCH /api/tasks/{id}` — close task

### Submissions
- `POST /api/tasks/{id}/submissions` — submit answer → eval → reward
- `GET /api/tasks/{id}/submissions` — list
- `GET /api/tasks/{id}/submissions/best` — current best score
- `GET /api/tasks/{id}/leaderboard` — top scores

### Other
- `GET /api/mint` — global mint state
- `GET /api/transactions` — user transaction history
- `GET /health` — health check

## Tokenomics

```
reward = pool_payout + mint_payout
pool_payout  = pool_balance × improvement_ratio
mint_payout  = base_reward × improvement_ratio × match_multiplier
improvement_ratio = (|delta| / |threshold - baseline|) × difficulty_bonus
difficulty_bonus  = 1 / (1 - progress)
```

Total supply: 1B $AXN, halving every 50M minted. Constants in `axon_server/rewards.py`.

## Eval types

| Type | Score |
|------|-------|
| `exact_match` | 1.0 or 0.0 |
| `numeric` | -\|answer - expected\| |
| `contains` | fraction of keywords matched |
| `regex` | 1.0 or 0.0 |
| `code_output` | parsed from subprocess stdout |
| `llm_judge` | 0-100 from LLM |

## Database

5 tables: `users`, `tasks`, `submissions`, `mint_state`, `transactions`.

## Coding conventions

- Async everywhere (async def, AsyncSession)
- Reward logic inside DB transaction with task row locked (`with_for_update()`)
- Eval runs OUTSIDE lock (may be slow); lock only for score compare + reward (fast)
- Eval modules import `EvalResult` from `axon_server.eval.result` (not engine — circular import)
