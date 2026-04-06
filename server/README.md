# Axon Backend

FastAPI backend for the Axon **Proof of Useful Work** bounty platform. Miners use LLM APIs to iteratively improve solutions to tasks, earning newly minted $AXN coins.

## Quick Start

```bash
# Prerequisites: Python 3.11+, PostgreSQL, uv
createdb -U $USER axon

# Install
uv venv && uv pip install -e ".[test]"

# Start
.venv/bin/uvicorn axon_server.main:app --host 127.0.0.1 --port 8000

# Run tests (server must be running)
NO_PROXY="*" .venv/bin/pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AXON_DATABASE_URL` | `postgresql+asyncpg://...localhost/axon` | PostgreSQL connection |
| `AXON_JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `AXON_JWT_EXPIRE_MINUTES` | `10080` (7 days) | Token expiry |
| `AXON_STARTER_COINS` | `1000` | Welcome bonus for new accounts |
| `AXON_JUDGE_API_KEY` | | API key for `llm_judge` eval type |

## API Endpoints

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | No | Create account `{username, email, password}` |
| POST | `/api/auth/login` | No | Returns `{access_token}` |
| GET | `/api/auth/me` | Yes | Current user profile + balance |

### Tasks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/tasks` | Yes | Create task, burn $AXN `{title, description, eval_type, eval_config, direction, completion_threshold, task_burn}` |
| GET | `/api/tasks?task_status=open` | No | List tasks |
| GET | `/api/tasks/{id}` | No | Task detail |
| PATCH | `/api/tasks/{id}` | Yes | Close task (publisher only) |

### Submissions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/tasks/{id}/submissions` | Yes | Submit `{answer, thinking, llm_model_used}` -> eval -> reward |
| GET | `/api/tasks/{id}/submissions` | No | List submissions |
| GET | `/api/tasks/{id}/submissions/best` | No | Current best score |
| GET | `/api/tasks/{id}/leaderboard` | No | Top scores |

### Other

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mint` | Global mint state (total minted, base reward, halving) |
| GET | `/api/transactions` | User transaction history (auth required) |
| GET | `/health` | Health check |

## Eval Types

### `exact_match`
```json
{"expected": "42", "case_sensitive": false, "strip_whitespace": true}
```
Score: `1.0` if match, `0.0` otherwise.

### `numeric`
```json
{"expected": 3.14159, "tolerance": 0.001, "scoring": "abs_error"}
```
Extracts last number from answer. Score: `-|answer - expected|` (abs_error) or `1.0`/`0.0` (within_tolerance).

### `contains`
```json
{"must_contain": ["neural", "dream", "light"], "case_sensitive": false}
```
Score: fraction of keywords found (0.0 - 1.0).

### `regex`
```json
{"pattern": "\\d{4}-\\d{2}-\\d{2}", "case_sensitive": false}
```
Score: `1.0` if pattern matches, `0.0` otherwise.

### `code_output`
```json
{"setup_code": "result = solve()\nprint(f'SCORE:{result}')", "timeout": 30, "score_prefix": "SCORE:"}
```
Runs miner's Python code + test harness in subprocess. Score parsed from stdout.

### `llm_judge`
```json
{"rubric": "Score 0-100 on clarity and accuracy", "model": "claude-sonnet-4-20250514", "max_score": 100}
```
Server calls LLM to score the answer. Requires `AXON_JUDGE_API_KEY`.

## Tokenomics (Proof of Useful Work)

### Task Creation
Publisher burns $AXN. System matches at `match_multiplier` rate:
```
pool = task_burn + (task_burn x match_multiplier)
```

### Miner Reward Formula
Each improvement earns pool payout + newly minted $AXN:
```
reward = pool_payout + mint_payout

pool_payout  = pool_balance x improvement_ratio
mint_payout  = base_reward x improvement_ratio x match_multiplier
```

### Improvement Ratio with Difficulty Bonus
```
delta             = |new_score - old_score|
range             = |threshold - baseline|
progress          = how far old_score is toward threshold (0.0 - 0.999)
difficulty_bonus  = 1 / (1 - progress)

improvement_ratio = (delta / range) x difficulty_bonus    (capped at 1.0)
```

The closer to the threshold, the higher the bonus:

| Progress | Bonus |
|----------|-------|
| 0% | 1x |
| 50% | 2x |
| 90% | 10x |
| 99% | 100x |

### Completion
When score reaches threshold: remaining pool drained + bonus mint of `base_reward x match_multiplier`.

### Halving
Every 50M $AXN minted: `base_reward` and `match_multiplier` halve. Minimum `base_reward = 1` (tail emission).

| Epoch | Minted | base_reward | match_multiplier |
|-------|--------|-------------|------------------|
| 1 | 0-50M | 1000 | 1.0 |
| 2 | 50M-100M | 500 | 0.5 |
| 3 | 100M-150M | 250 | 0.25 |
| ... | ... | ... | ... |

Total supply: **1,000,000,000 $AXN**.

## Anti-Spam

- **Rate limit**: 5s cooldown between submissions per miner per task
- **Answer dedup**: SHA256 hash, identical answers rejected
- **Min improvement**: ratio < 0.1% ignored
- **Server-side eval**: miners cannot fake scores

## Concurrency

Eval runs **outside** the database lock (may take seconds for code_output). Lock acquired only for score comparison + reward (microseconds). Multiple miners improving simultaneously both get rewarded fairly.

## Database

5 tables: `users`, `tasks`, `submissions`, `mint_state` (singleton), `transactions` (append-only ledger).

```bash
# Migrations
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "description"
```

## Tests

```bash
# Start server first, then:
NO_PROXY="*" .venv/bin/pytest tests/ -v

# 38 tests: eval types, tokenomics math, API integration
```

## License

MIT
