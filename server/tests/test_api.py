"""Integration tests for API endpoints. Requires a running backend on :8000."""
import asyncio
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_nonce_and_verify(client):
    """Wallet auth flow: nonce → sign → verify → JWT."""
    acct = Account.create()
    address = acct.address.lower()

    # Get nonce
    resp = await client.get(f"/api/auth/nonce?address={address}")
    assert resp.status_code == 200
    data = resp.json()
    assert "nonce" in data
    assert "message" in data

    # Sign and verify
    message = encode_defunct(text=f"Sign in to Axon: {data['nonce']}")
    sig = acct.sign_message(message)
    resp = await client.post("/api/auth/verify", json={
        "address": address,
        "signature": sig.signature.hex(),
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_verify_bad_signature(client):
    """Wrong signature should be rejected."""
    acct = Account.create()
    address = acct.address.lower()

    resp = await client.get(f"/api/auth/nonce?address={address}")
    assert resp.status_code == 200

    resp = await client.post("/api/auth/verify", json={
        "address": address,
        "signature": "0x" + "00" * 65,
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me(client, publisher_token):
    """GET /api/auth/me returns user profile."""
    resp = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {publisher_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "address" in data
    assert "balance" in data


@pytest.mark.asyncio
async def test_create_task_and_list(client, publisher_token):
    headers = {"Authorization": f"Bearer {publisher_token}"}

    resp = await client.post("/api/tasks", json={
        "title": "Test exact match",
        "description": "Answer 42",
        "eval_type": "exact_match",
        "eval_config": {"expected": "42"},
        "direction": "maximize",
        "completion_threshold": 1.0,
        "task_burn": 50,
    }, headers=headers)
    assert resp.status_code == 201
    task = resp.json()
    assert task["status"] == "open"
    assert task["task_burn"] == 50
    assert task["pool_balance"] >= 50

    # List tasks
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert any(t["id"] == task["id"] for t in tasks)


@pytest.mark.asyncio
async def test_insufficient_balance(client):
    """User with 0 balance can't create expensive task."""
    from tests.conftest import _wallet_auth
    token, _ = await _wallet_auth(client)

    resp = await client.post("/api/tasks", json={
        "title": "Expensive task",
        "description": "test",
        "eval_type": "exact_match",
        "eval_config": {"expected": "x"},
        "direction": "maximize",
        "completion_threshold": 1.0,
        "task_burn": 9999,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_and_reward(client, publisher_token, miner_token):
    pub_h = {"Authorization": f"Bearer {publisher_token}"}
    miner_h = {"Authorization": f"Bearer {miner_token}"}

    # Create task
    resp = await client.post("/api/tasks", json={
        "title": "Answer 42",
        "description": "Return 42",
        "eval_type": "exact_match",
        "eval_config": {"expected": "42", "case_sensitive": False},
        "direction": "maximize",
        "completion_threshold": 1.0,
        "task_burn": 100,
    }, headers=pub_h)
    task_id = resp.json()["id"]

    # Submit wrong answer (baseline)
    resp = await client.post(f"/api/tasks/{task_id}/submissions", json={
        "answer": "41", "thinking": "guess", "llm_model_used": "test"
    }, headers=miner_h)
    assert resp.status_code == 201
    s1 = resp.json()
    assert s1["score"] == 0.0
    assert s1["is_improvement"] is True  # first submission = baseline
    assert s1["reward_earned"] == 0  # baseline gets no reward

    # Wait for rate limit cooldown then submit correct answer
    await asyncio.sleep(6)
    resp = await client.post(f"/api/tasks/{task_id}/submissions", json={
        "answer": "42", "thinking": "math", "llm_model_used": "test"
    }, headers=miner_h)
    assert resp.status_code == 201
    s2 = resp.json()
    assert s2["score"] == 1.0
    assert s2["is_improvement"] is True
    assert s2["is_completion"] is True
    assert s2["reward_earned"] > 0


@pytest.mark.asyncio
async def test_duplicate_answer_rejected(client, publisher_token, miner_token):
    pub_h = {"Authorization": f"Bearer {publisher_token}"}
    miner_h = {"Authorization": f"Bearer {miner_token}"}

    resp = await client.post("/api/tasks", json={
        "title": "Dedup test",
        "description": "test",
        "eval_type": "exact_match",
        "eval_config": {"expected": "hello"},
        "direction": "maximize",
        "completion_threshold": 1.0,
        "task_burn": 50,
    }, headers=pub_h)
    task_id = resp.json()["id"]

    # First submit
    resp = await client.post(f"/api/tasks/{task_id}/submissions", json={
        "answer": "wrong", "thinking": "try1", "llm_model_used": "test"
    }, headers=miner_h)
    assert resp.status_code == 201

    # Wait for rate limit cooldown
    await asyncio.sleep(6)

    # Same answer again → rejected (dedup)
    resp = await client.post(f"/api/tasks/{task_id}/submissions", json={
        "answer": "wrong", "thinking": "try2", "llm_model_used": "test"
    }, headers=miner_h)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_rate_limit(client, publisher_token, miner_token):
    pub_h = {"Authorization": f"Bearer {publisher_token}"}
    miner_h = {"Authorization": f"Bearer {miner_token}"}

    resp = await client.post("/api/tasks", json={
        "title": "Rate limit test",
        "description": "test",
        "eval_type": "exact_match",
        "eval_config": {"expected": "x"},
        "direction": "maximize",
        "completion_threshold": 1.0,
        "task_burn": 50,
    }, headers=pub_h)
    task_id = resp.json()["id"]

    # First submit
    resp = await client.post(f"/api/tasks/{task_id}/submissions", json={
        "answer": "a", "thinking": "t", "llm_model_used": "test"
    }, headers=miner_h)
    assert resp.status_code == 201

    # Immediate second submit → rate limited
    resp = await client.post(f"/api/tasks/{task_id}/submissions", json={
        "answer": "b", "thinking": "t", "llm_model_used": "test"
    }, headers=miner_h)
    assert resp.status_code == 429
