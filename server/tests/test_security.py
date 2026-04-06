"""Tests for security mechanisms — rate limiting, dedup, GPU stake."""
import pytest
import httpx


@pytest.mark.asyncio
async def test_unauthenticated_submit(client):
    """Submitting without auth should fail."""
    resp = await client.post("/api/tasks/00000000-0000-0000-0000-000000000000/submissions", json={
        "answer": "test", "thinking": "test",
    })
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_nonexistent_task(client, miner_token):
    """Submitting to nonexistent task should 404."""
    resp = await client.post(
        "/api/tasks/00000000-0000-0000-0000-000000000000/submissions",
        json={"answer": "test", "thinking": "test"},
        headers={"Authorization": f"Bearer {miner_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_jwt(client):
    """Invalid JWT should be rejected."""
    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_close_task_wrong_user(client, publisher_token, miner_token):
    """Only publisher can close their own task."""
    # Create task as publisher
    resp = await client.post("/api/tasks", json={
        "title": "Auth test", "description": "t", "eval_type": "exact_match",
        "eval_config": {"expected": "x"}, "direction": "maximize",
        "completion_threshold": 1.0, "task_burn": 50,
    }, headers={"Authorization": f"Bearer {publisher_token}"})
    task_id = resp.json()["id"]

    # Try to close as miner
    resp = await client.patch(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {miner_token}"},
    )
    assert resp.status_code == 403
