"""
Entropy Garden — FastAPI application entry point.

Run from the server/ directory:
    uvicorn api.main:app --reload

Or from the repo root:
    uvicorn server.api.main:app --reload --app-dir server
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sim.events import load_events
from sim.state import SimConfig

from .routes import games, windows, ws
from .store import GameStore

log = logging.getLogger(__name__)

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

    # Start agent runner if AGENT_GAME_ID and AGENT_ROLE are set.
    # The game must already exist in the DB (restored at startup) or be created before
    # the runner's first decision window fires.
    agent_task: asyncio.Task[None] | None = None
    agent_game_id = os.environ.get("AGENT_GAME_ID", "").strip()
    agent_role = os.environ.get("AGENT_ROLE", "").strip()
    if agent_game_id and agent_role:
        from agents.agent import AgentService
        from agents.llm import get_llm_client
        from agents.runner import AgentRunner

        llm_client = get_llm_client(agent_role)
        agent_service = AgentService(role=agent_role, llm_client=llm_client)
        runner = AgentRunner(
            game_id=agent_game_id,
            role=agent_role,
            agent_service=agent_service,
            store=store,
        )
        store.register_agent_runner(agent_game_id, agent_role, runner)
        agent_task = asyncio.create_task(runner.run())
        log.info(
            "Agent runner started: game=%s role=%s provider=%s model=%s",
            agent_game_id, agent_role, llm_client.provider, llm_client.model,
        )

    yield

    if agent_task is not None:
        agent_task.cancel()
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

_cors_raw = os.environ.get("CORS_ORIGINS", "*")
_cors_origins = [o.strip() for o in _cors_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router)
app.include_router(windows.router)
app.include_router(ws.router)
