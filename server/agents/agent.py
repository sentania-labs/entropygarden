"""
AgentService: receives a role view, calls the LLM, returns a parsed action decision.

LLMs never write state directly — AgentService returns an AgentDecision that the
runner submits to the store via the actions API endpoint.  The engine validates and applies.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from .llm import LLMClient, get_llm_client
from .prompts import ROLE_PROMPTS, build_decision_prompt

log = logging.getLogger(__name__)

_SAFE_DEFAULT_ACTION = "prioritize_maintenance"
_SAFE_DEFAULT_RING = "ring_1"


# ---------------------------------------------------------------------------
# Decision model
# ---------------------------------------------------------------------------


class AgentDecision(BaseModel):
    action_type: str
    ring_id: str
    parameters: dict[str, Any] = {}
    reasoning: str


# ---------------------------------------------------------------------------
# Agent service
# ---------------------------------------------------------------------------


class AgentService:
    def __init__(self, role: str, llm_client: LLMClient | None = None) -> None:
        self.role = role
        self._llm = llm_client if llm_client is not None else get_llm_client(role)

    async def decide(
        self,
        role_view: dict[str, Any],
        recent_events: list[dict[str, Any]] | None = None,
        available_actions: list[str] | None = None,
    ) -> AgentDecision:
        """
        Call the LLM with the current role view and return a parsed AgentDecision.
        On parse failure, logs a warning and returns a safe default action.
        """
        if recent_events is None:
            recent_events = role_view.get("recent_events", [])
        if available_actions is None:
            available_actions = role_view.get("available_actions", [])

        system_prompt = ROLE_PROMPTS.get(self.role, ROLE_PROMPTS.get("captain", ""))
        user_prompt = build_decision_prompt(role_view, recent_events, available_actions)

        log.debug("agent decide role=%s tick=%s", self.role, role_view.get("tick"))

        raw = await self._llm.complete(system=system_prompt, user=user_prompt)

        log.debug("agent raw response role=%s: %s", self.role, raw[:200])

        decision = _parse_decision(raw, available_actions)

        log.debug(
            "agent decision role=%s action=%s ring=%s reasoning=%s",
            self.role,
            decision.action_type,
            decision.ring_id,
            decision.reasoning[:100],
        )
        return decision


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_decision(
    raw: str, available_actions: list[str] | None = None
) -> AgentDecision:
    """
    Extract a JSON object from the LLM response and validate the decision fields.
    On any failure, return a safe default action so the runner never crashes.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Find first JSON object in the text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        log.warning("agent response contained no JSON object, using safe default")
        return _safe_default(available_actions)

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        log.warning("agent response JSON parse error (%s), using safe default", exc)
        return _safe_default(available_actions)

    action_type = str(data.get("action_type", "")).strip()
    ring_id = str(data.get("ring_id", "")).strip()
    parameters = data.get("parameters", {})
    reasoning = str(data.get("reasoning", "")).strip()

    if not action_type or not ring_id:
        log.warning("agent response missing action_type or ring_id, using safe default")
        return _safe_default(available_actions)

    if available_actions and action_type not in available_actions:
        log.warning(
            "agent chose unavailable action %r (available: %s), using safe default",
            action_type,
            available_actions,
        )
        return _safe_default(available_actions)

    return AgentDecision(
        action_type=action_type,
        ring_id=ring_id,
        parameters=parameters if isinstance(parameters, dict) else {},
        reasoning=reasoning,
    )


def _safe_default(available_actions: list[str] | None) -> AgentDecision:
    action = _SAFE_DEFAULT_ACTION
    if available_actions and action not in available_actions:
        action = available_actions[0]
    return AgentDecision(
        action_type=action,
        ring_id=_SAFE_DEFAULT_RING,
        parameters={},
        reasoning="Safe default: LLM response could not be parsed.",
    )
