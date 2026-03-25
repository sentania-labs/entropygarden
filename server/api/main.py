"""
Entropy Garden — FastAPI application entry point.

Run from the server/ directory:
    uvicorn api.main:app --reload

Or from the repo root:
    uvicorn server.api.main:app --reload --app-dir server
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sim.events import load_events
from sim.state import SimConfig

from .routes import games, ws
from .store import GameStore

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

_DEFAULT_DB = Path(__file__).parent.parent / "entropy_garden.db"
_EVENTS_YAML = Path(__file__).parent.parent.parent / "data" / "events.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    cfg = SimConfig()
    event_defs = load_events(_EVENTS_YAML) if _EVENTS_YAML.exists() else []

    db_path = Path(os.environ.get("ENTROPY_GARDEN_DB", str(_DEFAULT_DB)))
    store = GameStore(cfg=cfg, event_defs=event_defs, db_path=db_path)
    await store.startup()
    app.state.store = store

    yield

    await store.shutdown()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Entropy Garden",
    description="Generation ship simulation API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router)
app.include_router(ws.router)
