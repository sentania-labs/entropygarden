"""
GameStore: in-memory game state management with SQLite persistence.

One GameStore instance lives for the lifetime of the FastAPI app (created in lifespan).

- Active states are kept in memory for fast tick access.
- State is checkpointed to SQLite every 100 ticks and on pause/delete.
- At startup, all persisted games are restored and their tick loops restarted.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any

from sim.events import EventDef
from sim.initializer import build_initial_state
from sim.state import GameState, SimConfig
from sim.tick import tick as sim_tick

from .models import GameListItem, GameSummary, summarize_state


class GameStore:
    def __init__(
        self,
        cfg: SimConfig,
        event_defs: list[EventDef],
        db_path: Path,
    ) -> None:
        self._cfg = cfg
        self._event_defs = event_defs
        self._db_path = db_path

        self._states: dict[str, GameState] = {}
        self._tick_rates: dict[str, float] = {}
        self._paused: set[str] = set()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

        self._init_db()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id    TEXT PRIMARY KEY,
                    seed       INTEGER NOT NULL,
                    tick_rate  REAL NOT NULL DEFAULT 1.0,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    async def startup(self) -> None:
        """Restore persisted games and restart their tick loops. Called at app startup."""
        loop = asyncio.get_running_loop()
        rows: list[tuple[str, int, float, str]] = await loop.run_in_executor(
            None, self._load_all_from_db
        )
        for game_id, _seed, tick_rate, state_json in rows:
            state = GameState.model_validate_json(state_json)
            self._states[game_id] = state
            self._tick_rates[game_id] = tick_rate
            self._subscribers[game_id] = set()
            self._tasks[game_id] = asyncio.create_task(self._run_loop(game_id))

    async def shutdown(self) -> None:
        """Save all active games and cancel tick tasks. Called at app shutdown."""
        for task in self._tasks.values():
            task.cancel()
        loop = asyncio.get_running_loop()
        for game_id, state in list(self._states.items()):
            tick_rate = self._tick_rates.get(game_id, 1.0)
            await loop.run_in_executor(
                None, self._write_to_db, game_id, state.seed, tick_rate, state.model_dump_json()
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, seed: int, tick_rate: float = 1.0, paused: bool = False) -> GameState:
        """Build initial state, persist it, and start (or not) the tick loop."""
        loop = asyncio.get_running_loop()
        state: GameState = await loop.run_in_executor(
            None, build_initial_state, seed, self._cfg
        )
        game_id = state.game_id
        self._states[game_id] = state
        self._tick_rates[game_id] = tick_rate
        self._subscribers[game_id] = set()
        if paused:
            self._paused.add(game_id)
        await loop.run_in_executor(
            None, self._write_to_db, game_id, seed, tick_rate, state.model_dump_json()
        )
        self._tasks[game_id] = asyncio.create_task(self._run_loop(game_id))
        return state

    def get(self, game_id: str) -> GameState | None:
        return self._states.get(game_id)

    def list_all(self) -> list[GameListItem]:
        return [
            GameListItem(
                game_id=gid,
                seed=state.seed,
                tick=state.tick,
                year=round(state.tick / 365.0, 2),
                total_population=sum(len(r.population) for r in state.rings.values()),
                tick_rate=self._tick_rates.get(gid, 1.0),
                paused=gid in self._paused,
            )
            for gid, state in self._states.items()
        ]

    async def delete(self, game_id: str) -> bool:
        if game_id not in self._states:
            return False
        task = self._tasks.pop(game_id, None)
        if task:
            task.cancel()
        self._states.pop(game_id)
        self._tick_rates.pop(game_id, None)
        self._paused.discard(game_id)
        self._subscribers.pop(game_id, None)
        await asyncio.get_running_loop().run_in_executor(
            None, self._delete_from_db, game_id
        )
        return True

    # ------------------------------------------------------------------
    # Tick control
    # ------------------------------------------------------------------

    def pause(self, game_id: str) -> bool:
        if game_id not in self._states:
            return False
        self._paused.add(game_id)
        return True

    async def resume(self, game_id: str) -> bool:
        if game_id not in self._states:
            return False
        self._paused.discard(game_id)
        # Restart task if it completed while paused
        task = self._tasks.get(game_id)
        if task is None or task.done():
            self._tasks[game_id] = asyncio.create_task(self._run_loop(game_id))
        return True

    async def advance(self, game_id: str, ticks: int = 1) -> GameState | None:
        """Synchronously advance the game by N ticks (ignores pause state). For testing and fast-forward."""
        if game_id not in self._states:
            return None
        loop = asyncio.get_running_loop()
        state = self._states[game_id]
        cfg = self._cfg
        event_defs = self._event_defs
        for _ in range(ticks):
            state = await loop.run_in_executor(None, sim_tick, state, cfg, event_defs)
        self._states[game_id] = state
        await self.broadcast(game_id, state)
        return state

    def is_paused(self, game_id: str) -> bool:
        return game_id in self._paused

    def get_tick_rate(self, game_id: str) -> float:
        return self._tick_rates.get(game_id, 1.0)

    def get_summary(self, game_id: str) -> GameSummary | None:
        state = self._states.get(game_id)
        if state is None:
            return None
        return summarize_state(state, self._tick_rates.get(game_id, 1.0), game_id in self._paused)

    # ------------------------------------------------------------------
    # WebSocket subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, game_id: str) -> asyncio.Queue[dict[str, Any]] | None:
        if game_id not in self._states:
            return None
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10)
        self._subscribers[game_id].add(q)
        return q

    def unsubscribe(self, game_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(game_id)
        if subs:
            subs.discard(queue)

    async def broadcast(self, game_id: str, state: GameState) -> None:
        subs = self._subscribers.get(game_id)
        if not subs:
            return
        msg: dict[str, Any] = {
            "type": "state",
            "data": summarize_state(
                state, self._tick_rates.get(game_id, 1.0), game_id in self._paused
            ).model_dump(),
        }
        for q in list(subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # slow client — skip this frame

    # ------------------------------------------------------------------
    # Background tick loop
    # ------------------------------------------------------------------

    async def _run_loop(self, game_id: str) -> None:
        loop = asyncio.get_running_loop()
        cfg = self._cfg
        event_defs = self._event_defs

        while game_id in self._states and game_id not in self._paused:
            state = self._states[game_id]
            try:
                new_state: GameState = await loop.run_in_executor(
                    None, sim_tick, state, cfg, event_defs
                )
            except Exception:
                break
            if game_id not in self._states:
                break
            self._states[game_id] = new_state
            await self.broadcast(game_id, new_state)
            if new_state.tick % 100 == 0:
                await loop.run_in_executor(
                    None,
                    self._write_to_db,
                    game_id,
                    new_state.seed,
                    self._tick_rates.get(game_id, 1.0),
                    new_state.model_dump_json(),
                )
            tick_rate = self._tick_rates.get(game_id, 1.0)
            await asyncio.sleep(1.0 / tick_rate)

    # ------------------------------------------------------------------
    # SQLite helpers (sync — run in executor)
    # ------------------------------------------------------------------

    def _load_all_from_db(self) -> list[tuple[str, int, float, str]]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT game_id, seed, tick_rate, state_json FROM games"
            ).fetchall()
        return rows  # type: ignore[return-value]

    def _write_to_db(self, game_id: str, seed: int, tick_rate: float, state_json: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO games (game_id, seed, tick_rate, state_json, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (game_id, seed, tick_rate, state_json, time.time()),
            )
            conn.commit()

    def _delete_from_db(self, game_id: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM games WHERE game_id = ?", (game_id,))
            conn.commit()
