"""WebSocket hub for real-time task score updates.

Miners can subscribe to a task and receive live notifications when
other miners improve the score.
"""
import asyncio
import json
import uuid
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# task_id -> set of connected WebSockets
_subscribers: dict[str, set[WebSocket]] = defaultdict(set)


@router.websocket("/ws/{task_id}")
async def task_ws(websocket: WebSocket, task_id: str):
    await websocket.accept()
    _subscribers[task_id].add(websocket)
    try:
        # Keep alive — client can send pings, we just wait
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _subscribers[task_id].discard(websocket)
        if not _subscribers[task_id]:
            del _subscribers[task_id]


async def broadcast_improvement(task_id: str, data: dict):
    """Broadcast a score improvement to all subscribers of a task."""
    subs = _subscribers.get(task_id)
    if not subs:
        return
    message = json.dumps(data)
    dead = set()
    for ws in subs:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    subs -= dead
