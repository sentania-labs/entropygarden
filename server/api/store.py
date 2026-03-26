"""
GameStore: in-memory game state management with SQLite persistence.

One GameStore instance lives for the lifetime of the FastAPI app (created in lifespan).

- Active states are kept in memory for fast tick access.
- State is checkpointed to SQLite every 100 ticks and on pause/delete.
- At startup, all persisted games are restored and their tick loops restarted.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from sim.events import EventDef
from sim.initializer import build_initial_state
from sim.policy import compliance_check, get_absent_roles
from sim.state import (
    ActionType,
    DecisionWindow,
    GameState,
    PendingAction,
    Policy,
    SimConfig,
    WindowStatus,
)
from sim.tick import tick as sim_tick
from sim.windows import open_window, resolve_window

from .models import (
    ActionRequest,
    ActionResponse,
    CaptainView,
    EngineerView,
    GameListItem,
    GameSummary,
    HistoryPoint,
    RingHistoryPoint,
    build_captain_view,
    build_engineer_view,
    summarize_state,
)

log = logging.getLogger(__name__)


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
        # role → AgentRunner, keyed by game_id → role → runner
        self._agent_runners: dict[str, dict[str, Any]] = {}
        # fire-and-forget fallback tasks; held to prevent GC before completion
        self._fallback_tasks: set[asyncio.Task[None]] = set()

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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    game_id   TEXT NOT NULL,
                    tick      INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (game_id, tick)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id     TEXT NOT NULL,
                    tick        INTEGER NOT NULL,
                    role        TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    ring_id     TEXT NOT NULL,
                    reasoning   TEXT NOT NULL DEFAULT '',
                    provider    TEXT NOT NULL DEFAULT '',
                    model       TEXT NOT NULL DEFAULT '',
                    created_at  REAL NOT NULL
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

    async def create(
        self,
        seed: int,
        tick_rate: float = 1.0,
        paused: bool = False,
        decision_window_interval: int = 100,
    ) -> GameState:
        """Build initial state, persist it, and start (or not) the tick loop."""
        loop = asyncio.get_running_loop()
        state: GameState = await loop.run_in_executor(
            None, build_initial_state, seed, self._cfg
        )
        if decision_window_interval != 100:
            state = state.model_copy(update={"decision_window_interval": decision_window_interval})
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
            interval = state.decision_window_interval
            if interval > 0 and state.tick > 0 and state.tick % interval == 0:
                state = await self._open_window(game_id, state)
                self._states[game_id] = state
                await self._broadcast_decision_window(game_id, state)
            if state.tick % 10 == 0:
                await loop.run_in_executor(None, self._write_history, game_id, state)
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

    def get_role_view(
        self, game_id: str, role: str
    ) -> EngineerView | CaptainView | None | str:
        """Return a role-filtered state view. Returns None if game not found, 'unknown_role' for bad role."""
        state = self._states.get(game_id)
        if state is None:
            return None
        cap = self._cfg.resource_capacity
        if role == "engineer":
            return build_engineer_view(state, cap)
        if role == "captain":
            return build_captain_view(state, cap)
        return "unknown_role"

    async def submit_action(
        self, game_id: str, request: ActionRequest
    ) -> ActionResponse | None:
        """Validate and enqueue a player/agent action. Applied at the start of the next tick."""
        state = self._states.get(game_id)
        if state is None:
            return None

        # Validate action_type
        try:
            action_type = ActionType(request.action_type)
        except ValueError:
            return ActionResponse(
                action_id="",
                status="rejected",
                detail=f"Unknown action_type: {request.action_type}",
                applied_tick=state.tick,
            )

        # Validate ring_id
        if request.ring_id not in state.rings:
            return ActionResponse(
                action_id="",
                status="rejected",
                detail=f"Unknown ring_id: {request.ring_id}",
                applied_tick=state.tick,
            )

        action_id = str(uuid.uuid4())
        pending = PendingAction(
            action_id=action_id,
            role=request.role,
            action_type=action_type,
            ring_id=request.ring_id,
            parameters=request.parameters,
            submitted_tick=state.tick,
        )
        updates: dict[str, Any] = {
            "pending_actions": list(state.pending_actions) + [pending],
        }
        # Record the role as having submitted during this window
        if (
            state.current_window
            and state.current_window.status == WindowStatus.OPEN
            and request.role not in state.current_window.submitted
        ):
                new_submitted = list(state.current_window.submitted) + [request.role]
                updates["current_window"] = state.current_window.model_copy(
                    update={"submitted": new_submitted}
                )
        new_state = state.model_copy(update=updates)
        self._states[game_id] = new_state
        log.debug(
            "action accepted game=%s tick=%d role=%s type=%s ring=%s",
            game_id, state.tick, request.role, request.action_type, request.ring_id,
        )
        return ActionResponse(
            action_id=action_id,
            status="accepted",
            applied_tick=state.tick + 1,
        )

    def log_agent_decision(
        self,
        game_id: str,
        tick: int,
        role: str,
        action_type: str,
        ring_id: str,
        reasoning: str,
        provider: str,
        model: str,
    ) -> None:
        """Persist an agent decision to the agent_decisions table (sync, call via executor)."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO agent_decisions
                   (game_id, tick, role, action_type, ring_id, reasoning, provider, model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (game_id, tick, role, action_type, ring_id, reasoning, provider, model, time.time()),
            )
            conn.commit()

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

    async def _broadcast_decision_window(self, game_id: str, state: GameState) -> None:
        subs = self._subscribers.get(game_id)
        if not subs:
            return
        window = state.current_window
        msg: dict[str, Any] = {
            "type": "decision_window",
            "game_id": game_id,
            "tick": state.tick,
            "year": round(state.year, 2),
            "window_id": window.window_id if window else None,
            "closes_tick": window.closes_tick if window else None,
        }
        log.debug("decision_window opened game=%s tick=%d", game_id, state.tick)
        for q in list(subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    async def _open_window(self, game_id: str, state: GameState) -> GameState:
        """Close the current window (if open) then open a new one."""
        if state.current_window and state.current_window.status == WindowStatus.OPEN:
            state = await self._close_window(game_id, state)
        new_window = open_window(
            opened_tick=state.tick,
            interval=state.decision_window_interval,
        )
        return state.model_copy(update={"current_window": new_window})

    async def _close_window(self, game_id: str, state: GameState) -> GameState:
        """Resolve the current window: apply conflict resolution and dispatch policy fallbacks."""
        window = state.current_window
        if window is None or window.status != WindowStatus.OPEN:
            return state

        closed_window, accepted_actions = resolve_window(window, list(state.pending_actions))

        # Determine absent roles and populate fallback_roles in resolution
        active_roles = list((self._agent_runners.get(game_id) or {}).keys()) or None
        submitted = list(window.submitted)
        absent = get_absent_roles(submitted, active_roles)

        fallback_roles: list[str] = []
        for role in absent:
            policy = state.policies.get(role)
            if policy is None:
                continue
            # Compliance check using a simple deterministic value for MVP
            # (seeded PRNG integration can be added later)
            if not compliance_check(policy, 0.5):
                continue
            fallback_roles.append(role)
            # Dispatch fallback as a fire-and-forget task
            task = asyncio.create_task(
                self._fallback_for_role(game_id, role, state.tick, policy)
            )
            self._fallback_tasks.add(task)
            task.add_done_callback(self._fallback_tasks.discard)

        # Update resolution with actual fallback_roles
        if closed_window.resolution is not None:
            updated_resolution = closed_window.resolution.model_copy(
                update={"fallback_roles": fallback_roles}
            )
            closed_window = closed_window.model_copy(update={"resolution": updated_resolution})

        # Cap window history at 100 entries
        history = list(state.window_history[-99:]) + [closed_window]

        return state.model_copy(update={
            "pending_actions": accepted_actions,
            "current_window": closed_window,
            "window_history": history,
        })

    async def _fallback_for_role(
        self,
        game_id: str,
        role: str,
        window_tick: int,
        policy: Policy,
    ) -> None:
        """Generate and submit a fallback action for an absent role.

        If an AgentRunner is registered for this role, delegate to it (LLM path).
        Otherwise use the deterministic path: submit the first policy priority directly.
        """
        runners = self._agent_runners.get(game_id, {})
        runner = runners.get(role)
        if runner is not None:
            try:
                await runner.run_fallback(window_tick, policy)
            except Exception:
                log.exception("fallback runner failed game=%s role=%s", game_id, role)
            return

        # Deterministic path: no agent configured — submit first priority directly
        if not policy.priorities:
            return
        priority = policy.priorities[0]
        from .models import ActionRequest
        request = ActionRequest(
            role=role,
            action_type=priority.action_type,
            ring_id=priority.ring_id,
            parameters=priority.parameters,
            reasoning=f"Policy fallback: {priority.note}" if priority.note else "Policy fallback",
        )
        result = await self.submit_action(game_id, request)
        if result is None or result.status == "rejected":
            log.warning(
                "policy fallback action rejected game=%s role=%s action=%s",
                game_id, role, priority.action_type,
            )
        else:
            log.info(
                "policy fallback submitted game=%s role=%s action=%s ring=%s",
                game_id, role, priority.action_type, priority.ring_id,
            )

    # ------------------------------------------------------------------
    # Window queries
    # ------------------------------------------------------------------

    def get_current_window(self, game_id: str) -> DecisionWindow | None:
        state = self._states.get(game_id)
        if state is None:
            return None
        if state.current_window and state.current_window.status == WindowStatus.OPEN:
            return state.current_window
        return None

    def get_window_history(self, game_id: str, limit: int = 50) -> list[DecisionWindow]:
        state = self._states.get(game_id)
        if state is None:
            return []
        history = state.window_history
        return list(reversed(history))[:limit]

    def set_policy(self, game_id: str, role: str, policy: Policy) -> bool:
        state = self._states.get(game_id)
        if state is None:
            return False
        new_policies = dict(state.policies)
        new_policies[role] = policy
        self._states[game_id] = state.model_copy(update={"policies": new_policies})
        return True

    def get_policy(self, game_id: str, role: str) -> Policy | None:
        state = self._states.get(game_id)
        if state is None:
            return None
        return state.policies.get(role)

    def register_agent_runner(self, game_id: str, role: str, runner: Any) -> None:
        if game_id not in self._agent_runners:
            self._agent_runners[game_id] = {}
        self._agent_runners[game_id][role] = runner

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
            # Decision window lifecycle — open new window (closes previous) at interval
            interval = new_state.decision_window_interval
            if interval > 0 and new_state.tick > 0 and new_state.tick % interval == 0:
                new_state = await self._open_window(game_id, new_state)
                self._states[game_id] = new_state
                await self._broadcast_decision_window(game_id, new_state)
            if new_state.tick % 100 == 0:
                await loop.run_in_executor(
                    None,
                    self._write_to_db,
                    game_id,
                    new_state.seed,
                    self._tick_rates.get(game_id, 1.0),
                    new_state.model_dump_json(),
                )
            if new_state.tick % 10 == 0:
                await loop.run_in_executor(None, self._write_history, game_id, new_state)
            tick_rate = self._tick_rates.get(game_id, 1.0)
            await asyncio.sleep(1.0 / tick_rate)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, game_id: str, limit: int = 200) -> list[HistoryPoint]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT data_json FROM history WHERE game_id = ? ORDER BY tick DESC LIMIT ?",
                (game_id, limit),
            ).fetchall()
        points = [HistoryPoint.model_validate_json(r[0]) for r in rows]
        return list(reversed(points))  # chronological order

    # ------------------------------------------------------------------
    # SQLite helpers (sync — run in executor)
    # ------------------------------------------------------------------

    def _write_history(self, game_id: str, state: GameState) -> None:
        rings: dict[str, RingHistoryPoint] = {}
        for ring_id, ring in state.rings.items():
            pop = ring.population
            n = len(pop)
            rings[ring_id] = RingHistoryPoint(
                population=n,
                mean_health=round(sum(p.health for p in pop) / n, 3) if n else 0.0,
                mean_morale=round(sum(p.morale for p in pop) / n, 3) if n else 0.0,
                food=round(ring.resources.food, 1),
                water=round(ring.resources.water, 1),
                oxygen=round(ring.resources.oxygen, 1),
                power=round(ring.resources.power, 1),
            )
        point = HistoryPoint(tick=state.tick, year=round(state.year, 2), rings=rings)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO history (game_id, tick, data_json) VALUES (?, ?, ?)",
                (game_id, state.tick, point.model_dump_json()),
            )
            conn.commit()

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
