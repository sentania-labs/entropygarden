"""
Decision window REST endpoints.

All routes are prefixed with /games/{game_id}/window.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from sim.state import DecisionWindow, Policy, WindowStatus

from ..models import ActionRequest, ActionResponse
from ..store import GameStore

router = APIRouter(prefix="/games/{game_id}/window", tags=["windows"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_store(request: Request) -> GameStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[GameStore, Depends(get_store)]


# ---------------------------------------------------------------------------
# Window state
# ---------------------------------------------------------------------------


@router.get("/current", response_model=DecisionWindow | None)
def get_current_window(game_id: str, store: StoreDep) -> DecisionWindow | None:
    """Return the currently open window, or null if no window is open."""
    if store.get(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return store.get_current_window(game_id)


@router.get("/history", response_model=list[DecisionWindow])
def get_window_history(
    game_id: str,
    store: StoreDep,
    limit: int = 50,
) -> list[DecisionWindow]:
    """Return closed windows, most recent first."""
    if store.get(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return store.get_window_history(game_id, limit=min(limit, 200))


# ---------------------------------------------------------------------------
# Window-aware action submission
# ---------------------------------------------------------------------------


@router.post("/action", response_model=ActionResponse)
async def submit_window_action(
    game_id: str,
    body: ActionRequest,
    store: StoreDep,
) -> ActionResponse:
    """
    Submit an action during the current open window.

    Returns HTTP 409 if no window is currently open — use POST /games/{id}/actions
    to queue an action outside a window.
    """
    window = store.get_current_window(game_id)
    if window is None or window.status != WindowStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No open decision window. Submit via /actions to queue for next window.",
        )
    result = await store.submit_action(game_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if result.status == "rejected":
        raise HTTPException(status_code=422, detail=result.detail or "Action rejected")
    return result


# ---------------------------------------------------------------------------
# Policy management
# ---------------------------------------------------------------------------


@router.get("/policy/{role}", response_model=Policy | None)
def get_policy(game_id: str, role: str, store: StoreDep) -> Policy | None:
    """Return the standing orders for a role, or null if none set."""
    if store.get(game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return store.get_policy(game_id, role)


@router.put("/policy/{role}", response_model=Policy)
def set_policy(game_id: str, role: str, body: Policy, store: StoreDep) -> Policy:
    """Upsert a role's standing orders."""
    if not store.set_policy(game_id, role, body):
        raise HTTPException(status_code=404, detail="Game not found")
    return body
