"""
REST endpoints for game management.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from sim.state import EventRecord

from ..models import ActionRequest, ActionResponse, CaptainView, EngineerView, GameListItem, GameSummary, HistoryPoint
from ..store import GameStore

router = APIRouter(prefix="/games", tags=["games"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_store(request: Request) -> GameStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[GameStore, Depends(get_store)]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateGameRequest(BaseModel):
    seed: int = 42
    tick_rate: float = 1.0
    paused: bool = False
    decision_window_interval: int = 100


class AdvanceRequest(BaseModel):
    ticks: int = 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, response_model=GameSummary)
async def create_game(body: CreateGameRequest, store: StoreDep) -> GameSummary:
    state = await store.create(
        seed=body.seed,
        tick_rate=body.tick_rate,
        paused=body.paused,
        decision_window_interval=body.decision_window_interval,
    )
    summary = store.get_summary(state.game_id)
    assert summary is not None
    return summary


@router.get("", response_model=list[GameListItem])
def list_games(store: StoreDep) -> list[GameListItem]:
    return store.list_all()


@router.get("/{game_id}", response_model=GameSummary)
def get_game(game_id: str, store: StoreDep) -> GameSummary:
    summary = store.get_summary(game_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return summary


@router.get("/{game_id}/state")
def get_full_state(game_id: str, store: StoreDep) -> dict:  # type: ignore[type-arg]
    state = store.get(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state.model_dump()


@router.get("/{game_id}/events", response_model=list[EventRecord])
def get_events(game_id: str, store: StoreDep, since: int = 0) -> list[EventRecord]:
    state = store.get(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return [e for e in state.event_log if e.tick >= since]


@router.get("/{game_id}/history", response_model=list[HistoryPoint])
def get_history(game_id: str, store: StoreDep, limit: int = 200) -> list[HistoryPoint]:
    if store.get(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return store.get_history(game_id, limit=min(limit, 1000))


@router.post("/{game_id}/pause", response_model=GameSummary)
def pause_game(game_id: str, store: StoreDep) -> GameSummary:
    if not store.pause(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    summary = store.get_summary(game_id)
    assert summary is not None
    return summary


@router.post("/{game_id}/resume", response_model=GameSummary)
async def resume_game(game_id: str, store: StoreDep) -> GameSummary:
    if not await store.resume(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    summary = store.get_summary(game_id)
    assert summary is not None
    return summary


@router.post("/{game_id}/advance", response_model=GameSummary)
async def advance_game(game_id: str, body: AdvanceRequest, store: StoreDep) -> GameSummary:
    """Advance the game by N ticks synchronously. Useful for testing and fast-forward."""
    if body.ticks < 1 or body.ticks > 10_000:
        raise HTTPException(status_code=422, detail="ticks must be between 1 and 10000")
    state = await store.advance(game_id, ticks=body.ticks)
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    summary = store.get_summary(game_id)
    assert summary is not None
    return summary


@router.get("/{game_id}/roles/{role}/view", response_model=EngineerView | CaptainView)
def get_role_view(game_id: str, role: str, store: StoreDep) -> EngineerView | CaptainView:
    """Return a role-filtered view of game state encoding information asymmetry."""
    view = store.get_role_view(game_id, role)
    if view is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if view == "unknown_role":
        raise HTTPException(status_code=404, detail=f"Unknown role: {role}")
    return view  # type: ignore[return-value]


@router.post("/{game_id}/actions", response_model=ActionResponse)
async def submit_action(game_id: str, body: ActionRequest, store: StoreDep) -> ActionResponse:
    """Submit a role action. Engine validates and applies on the next tick."""
    result = await store.submit_action(game_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if result.status == "rejected":
        raise HTTPException(status_code=422, detail=result.detail)
    return result


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(game_id: str, store: StoreDep) -> None:
    if not await store.delete(game_id):
        raise HTTPException(status_code=404, detail="Game not found")
