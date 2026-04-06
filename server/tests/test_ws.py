"""Tests for WebSocket broadcast."""
import pytest
from axon_server.ws import broadcast_improvement, _subscribers


@pytest.mark.asyncio
async def test_broadcast_no_subscribers():
    """Broadcasting with no subscribers should not error."""
    await broadcast_improvement("nonexistent-task", {"event": "test"})


def test_subscribers_dict_empty():
    assert isinstance(_subscribers, dict)
