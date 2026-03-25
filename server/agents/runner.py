"""
AgentRunner: wakes on each decision window, fetches the role view, calls the agent,
and submits the resulting action through the store.

Wired into the FastAPI lifespan when AGENT_GAME_ID and AGENT_ROLE env vars are set.
The runner subscribes to the game's internal queue (same mechanism as WebSocket
clients) and reacts to "decision_window" messages — no polling required.
"""

from __future__ import annotations

import asyncio
import logging

from api.models import ActionRequest
from api.store import GameStore

from .agent import AgentService

log = logging.getLogger(__name__)


class AgentRunner:
    def __init__(
        self,
        game_id: str,
        role: str,
        agent_service: AgentService,
        store: GameStore,
    ) -> None:
        self._game_id = game_id
        self._role = role
        self._agent = agent_service
        self._store = store

    async def run(self) -> None:
        """
        Subscribe to the game queue and act on each decision_window message.
        Exits cleanly when the game is deleted or the queue is unset.
        """
        queue = self._store.subscribe(self._game_id)
        if queue is None:
            log.error("AgentRunner: game %s not found, cannot subscribe", self._game_id)
            return

        log.info(
            "AgentRunner started: game=%s role=%s provider=%s model=%s",
            self._game_id,
            self._role,
            self._agent._llm.provider,
            self._agent._llm.model,
        )

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Check the game still exists
                    if self._store.get(self._game_id) is None:
                        log.info("AgentRunner: game %s gone, stopping", self._game_id)
                        break
                    continue

                if msg.get("type") != "decision_window":
                    continue

                tick = msg.get("tick", 0)
                year = msg.get("year", 0.0)
                log.info(
                    "decision_window opened game=%s tick=%d year=%.1f — agent acting",
                    self._game_id, tick, year,
                )

                await self._act(tick)

        finally:
            self._store.unsubscribe(self._game_id, queue)
            log.info("AgentRunner stopped: game=%s role=%s", self._game_id, self._role)

    async def _act(self, window_tick: int) -> None:
        """Fetch role view, call agent, submit action, log decision."""
        view = self._store.get_role_view(self._game_id, self._role)
        if view is None or isinstance(view, str):
            log.warning("AgentRunner: could not get role view (game=%s role=%s)", self._game_id, self._role)
            return

        role_view_dict = view.model_dump()

        try:
            decision = await self._agent.decide(
                role_view=role_view_dict,
                recent_events=role_view_dict.get("recent_events", []),
                available_actions=role_view_dict.get("available_actions", []),
            )
        except Exception:
            log.exception("AgentRunner: LLM call failed game=%s role=%s", self._game_id, self._role)
            return

        request = ActionRequest(
            role=self._role,
            action_type=decision.action_type,
            ring_id=decision.ring_id,
            parameters=decision.parameters,
            reasoning=decision.reasoning,
        )

        result = await self._store.submit_action(self._game_id, request)
        if result is None or result.status == "rejected":
            log.warning(
                "AgentRunner: action rejected game=%s role=%s action=%s detail=%s",
                self._game_id, self._role, decision.action_type,
                result.detail if result else "game gone",
            )
            return

        log.info(
            "AgentRunner: action accepted game=%s role=%s action=%s ring=%s",
            self._game_id, self._role, decision.action_type, decision.ring_id,
        )

        # Persist decision to DB (sync call via executor)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._store.log_agent_decision,
            self._game_id,
            window_tick,
            self._role,
            decision.action_type,
            decision.ring_id,
            decision.reasoning,
            self._agent._llm.provider,
            self._agent._llm.model,
        )
