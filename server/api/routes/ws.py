"""
WebSocket endpoint for real-time state streaming.

WS /games/{game_id}/ws

- On connect: immediately sends current state summary.
- On each background tick: pushes updated state summary.
- Client may send {"type": "ping"} to receive {"type": "pong"}.
- Closes with 4004 if the game does not exist.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ..store import GameStore

router = APIRouter(tags=["ws"])


def _get_store(request: Request) -> GameStore:
    return request.app.state.store  # type: ignore[no-any-return]


@router.websocket("/games/{game_id}/ws")
async def game_websocket(websocket: WebSocket, game_id: str) -> None:
    store: GameStore = websocket.app.state.store  # type: ignore[assignment]

    state = store.get(game_id)
    if state is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    queue = store.subscribe(game_id)
    if queue is None:
        await websocket.close(code=4004)
        return

    # Send current state immediately on connect
    summary = store.get_summary(game_id)
    if summary:
        await websocket.send_json({"type": "state", "data": summary.model_dump()})

    try:
        while True:
            # Wait for either a tick update or a client message
            recv_task = asyncio.create_task(websocket.receive_text())
            queue_task = asyncio.create_task(queue.get())

            done, pending = await asyncio.wait(
                {recv_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            for task in done:
                if task is queue_task:
                    msg = task.result()
                    await websocket.send_json(msg)
                elif task is recv_task:
                    try:
                        text = task.result()
                        data = json.loads(text)
                        if data.get("type") == "ping":
                            await websocket.send_json({"type": "pong"})
                    except (json.JSONDecodeError, KeyError):
                        pass

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        store.unsubscribe(game_id, queue)
