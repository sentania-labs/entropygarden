"""
Tests for the agent service, LLM client factory, role view endpoint, and action submission.

No live LLM calls are made — all LLM responses are provided via mocks.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from agents.agent import AgentDecision, AgentService, _parse_decision


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import os
    monkeypatch.setenv("ENTROPY_GARDEN_DB", str(tmp_path / "test.db"))  # type: ignore[arg-type]
    # Ensure no agent runner starts during tests
    monkeypatch.delenv("AGENT_GAME_ID", raising=False)
    monkeypatch.delenv("AGENT_ROLE", raising=False)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c  # type: ignore[misc]


def _create_game(client: TestClient, seed: int = 42, paused: bool = True) -> str:
    resp = client.post("/games", json={"seed": seed, "paused": paused})
    assert resp.status_code == 201
    return resp.json()["game_id"]


def _make_llm_mock(response_text: str) -> MagicMock:
    """Return a mock LLMClient whose complete() returns response_text."""
    mock = MagicMock()
    mock.provider = "mock"
    mock.model = "mock-model"
    mock.complete = AsyncMock(return_value=response_text)
    return mock


# ---------------------------------------------------------------------------
# AgentService unit tests
# ---------------------------------------------------------------------------


class TestAgentService:
    def test_decide_returns_valid_action(self) -> None:
        response_json = json.dumps({
            "action_type": "emergency_repair",
            "ring_id": "ring_2",
            "parameters": {},
            "reasoning": "ring_2 maintenance debt is 0.71 and power is at 45%.",
        })
        llm = _make_llm_mock(response_json)
        svc = AgentService(role="engineer", llm_client=llm)

        role_view: dict[str, Any] = {
            "game_id": "g1", "tick": 100, "year": 0.27, "role": "engineer",
            "rings": {
                "ring_2": {
                    "power": 225.0, "power_fill_pct": 45.0,
                    "maintenance_debt": 0.71, "engineer_count": 50,
                    "engineer_fraction": 0.18, "active_modifiers": [],
                }
            },
            "ship_power_total": 900.0,
            "recent_events": [],
            "available_actions": ["prioritize_maintenance", "emergency_repair", "divert_power"],
        }

        decision = asyncio.get_event_loop().run_until_complete(
            svc.decide(role_view=role_view)
        )

        assert isinstance(decision, AgentDecision)
        assert decision.action_type == "emergency_repair"
        assert decision.ring_id == "ring_2"
        assert "0.71" in decision.reasoning or "maintenance" in decision.reasoning

    def test_decide_handles_malformed_json(self) -> None:
        llm = _make_llm_mock("Sorry I cannot help with that today.")
        svc = AgentService(role="engineer", llm_client=llm)

        role_view: dict[str, Any] = {
            "game_id": "g1", "tick": 50, "year": 0.1, "role": "engineer",
            "rings": {}, "ship_power_total": 0.0,
            "recent_events": [], "available_actions": ["prioritize_maintenance"],
        }

        decision = asyncio.get_event_loop().run_until_complete(
            svc.decide(role_view=role_view)
        )

        # Should not raise; should return a safe default
        assert isinstance(decision, AgentDecision)
        assert decision.action_type == "prioritize_maintenance"
        assert decision.ring_id == "ring_1"
        assert "Safe default" in decision.reasoning

    def test_decide_uses_engineer_system_prompt(self) -> None:
        from agents.prompts import ROLE_PROMPTS
        llm = _make_llm_mock('{"action_type": "prioritize_maintenance", "ring_id": "ring_1", "parameters": {}, "reasoning": "test"}')
        svc = AgentService(role="engineer", llm_client=llm)

        role_view: dict[str, Any] = {
            "game_id": "g1", "tick": 0, "year": 0.0, "role": "engineer",
            "rings": {}, "ship_power_total": 0.0,
            "recent_events": [], "available_actions": ["prioritize_maintenance"],
        }

        asyncio.get_event_loop().run_until_complete(svc.decide(role_view=role_view))

        # LLM must have been called with the engineer system prompt
        call_kwargs = llm.complete.call_args
        system_arg = call_kwargs.kwargs.get("system") or call_kwargs.args[0]
        assert "Chief Engineer" in system_arg
        assert ROLE_PROMPTS["engineer"] == system_arg

    def test_decide_strips_markdown_code_fences(self) -> None:
        response = "```json\n{\"action_type\": \"ration_resource\", \"ring_id\": \"ring_3\", \"parameters\": {}, \"reasoning\": \"low food\"}\n```"
        llm = _make_llm_mock(response)
        svc = AgentService(role="captain", llm_client=llm)

        role_view: dict[str, Any] = {
            "game_id": "g1", "tick": 10, "year": 0.03, "role": "captain",
            "rings": {}, "ship_summary": {}, "recent_events": [],
            "available_actions": ["ration_resource", "boost_production", "divert_power"],
        }

        decision = asyncio.get_event_loop().run_until_complete(svc.decide(role_view=role_view))
        assert decision.action_type == "ration_resource"


# ---------------------------------------------------------------------------
# _parse_decision unit tests (no LLM involved)
# ---------------------------------------------------------------------------


class TestParseDecision:
    def test_valid_json_parsed_correctly(self) -> None:
        raw = '{"action_type": "boost_production", "ring_id": "ring_1", "parameters": {}, "reasoning": "food low"}'
        d = _parse_decision(raw, ["boost_production"])
        assert d.action_type == "boost_production"
        assert d.ring_id == "ring_1"

    def test_extra_text_before_json_ignored(self) -> None:
        raw = "Here is my decision:\n\n{\"action_type\": \"emergency_repair\", \"ring_id\": \"ring_2\", \"parameters\": {}, \"reasoning\": \"debt high\"}"
        d = _parse_decision(raw)
        assert d.action_type == "emergency_repair"

    def test_unavailable_action_falls_back_to_default(self) -> None:
        raw = '{"action_type": "launch_torpedoes", "ring_id": "ring_1", "parameters": {}, "reasoning": "why not"}'
        d = _parse_decision(raw, available_actions=["prioritize_maintenance"])
        assert d.action_type == "prioritize_maintenance"

    def test_empty_string_returns_safe_default(self) -> None:
        d = _parse_decision("", available_actions=["boost_production"])
        assert d.action_type == "boost_production"
        assert "Safe default" in d.reasoning


# ---------------------------------------------------------------------------
# LLM client factory tests
# ---------------------------------------------------------------------------


class TestLLMClientFactory:
    def test_default_provider_is_openrouter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("ENGINEER_LLM_PROVIDER", raising=False)
        from agents.llm import get_llm_client, OpenAICompatibleClient
        c = get_llm_client("engineer")
        assert isinstance(c, OpenAICompatibleClient)
        assert c.provider == "openrouter"

    def test_role_override_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENGINEER_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from agents.llm import get_llm_client, AnthropicClient
        c = get_llm_client("engineer")
        assert isinstance(c, AnthropicClient)
        assert c.provider == "anthropic"

    def test_local_provider_uses_local_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "local")
        monkeypatch.setenv("LOCAL_LLM_URL", "http://my-gpu-box:11434/v1")
        from agents.llm import get_llm_client, OpenAICompatibleClient
        c = get_llm_client(None)
        assert isinstance(c, OpenAICompatibleClient)
        assert c.provider == "local"
        assert c._base_url == "http://my-gpu-box:11434/v1"

    def test_model_override_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("CAPTAIN_LLM_MODEL", "anthropic/claude-3-haiku")
        from agents.llm import get_llm_client, OpenAICompatibleClient
        c = get_llm_client("captain")
        assert isinstance(c, OpenAICompatibleClient)
        assert c.model == "anthropic/claude-3-haiku"

    def test_invalid_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "groq_v99")
        from agents.llm import get_llm_client
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_client(None)


# ---------------------------------------------------------------------------
# Role view endpoint tests
# ---------------------------------------------------------------------------


class TestRoleViewEndpoint:
    def test_engineer_view_has_expected_fields(self, client: TestClient) -> None:
        gid = _create_game(client)
        resp = client.get(f"/games/{gid}/roles/engineer/view")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "engineer"
        assert "rings" in data
        assert "ship_power_total" in data
        assert "available_actions" in data
        # Check ring structure
        for ring_data in data["rings"].values():
            assert "power" in ring_data
            assert "maintenance_debt" in ring_data
            assert "engineer_count" in ring_data
            assert "engineer_fraction" in ring_data
            assert "active_modifiers" in ring_data

    def test_captain_view_has_expected_fields(self, client: TestClient) -> None:
        gid = _create_game(client)
        resp = client.get(f"/games/{gid}/roles/captain/view")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "captain"
        assert "rings" in data
        assert "ship_summary" in data
        assert "available_actions" in data
        for ring_data in data["rings"].values():
            assert "population" in ring_data
            assert "mean_health" in ring_data
            assert "mean_morale" in ring_data
            assert "risk_flags" in ring_data

    def test_engineer_view_values_match_actual_state(self, client: TestClient) -> None:
        gid = _create_game(client)
        full = client.get(f"/games/{gid}/state").json()
        eng_view = client.get(f"/games/{gid}/roles/engineer/view").json()

        for ring_id in ["ring_1", "ring_2", "ring_3"]:
            actual_power = full["rings"][ring_id]["resources"]["power"]
            view_power = eng_view["rings"][ring_id]["power"]
            assert abs(actual_power - view_power) < 0.2, (
                f"Engineer power view {view_power} does not match full state {actual_power}"
            )

    def test_captain_view_does_not_expose_raw_maintenance_debt(self, client: TestClient) -> None:
        gid = _create_game(client)
        data = client.get(f"/games/{gid}/roles/captain/view").json()
        for ring_data in data["rings"].values():
            # Captain sees risk_flags, not raw maintenance_debt numbers
            assert "maintenance_debt" not in ring_data

    def test_unknown_role_returns_404(self, client: TestClient) -> None:
        gid = _create_game(client)
        resp = client.get(f"/games/{gid}/roles/navigator/view")
        assert resp.status_code == 404

    def test_unknown_game_returns_404(self, client: TestClient) -> None:
        resp = client.get("/games/no-such-game/roles/engineer/view")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Action submission tests
# ---------------------------------------------------------------------------


class TestActionSubmission:
    def test_submit_valid_action_accepted(self, client: TestClient) -> None:
        gid = _create_game(client)
        resp = client.post(f"/games/{gid}/actions", json={
            "role": "engineer",
            "action_type": "emergency_repair",
            "ring_id": "ring_1",
            "parameters": {},
            "reasoning": "ring_1 maintenance debt is high",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["action_id"]
        assert data["applied_tick"] >= 1

    def test_submit_invalid_action_type_rejected(self, client: TestClient) -> None:
        gid = _create_game(client)
        resp = client.post(f"/games/{gid}/actions", json={
            "role": "engineer",
            "action_type": "launch_escape_pod",
            "ring_id": "ring_1",
            "parameters": {},
        })
        assert resp.status_code == 422

    def test_submit_invalid_ring_id_rejected(self, client: TestClient) -> None:
        gid = _create_game(client)
        resp = client.post(f"/games/{gid}/actions", json={
            "role": "engineer",
            "action_type": "emergency_repair",
            "ring_id": "ring_99",
            "parameters": {},
        })
        assert resp.status_code == 422

    def test_unknown_game_returns_404(self, client: TestClient) -> None:
        resp = client.post("/games/no-such-game/actions", json={
            "role": "engineer",
            "action_type": "emergency_repair",
            "ring_id": "ring_1",
            "parameters": {},
        })
        assert resp.status_code == 404

    def test_emergency_repair_reduces_debt_after_tick(self, client: TestClient) -> None:
        gid = _create_game(client)

        # Record initial maintenance debt
        state_before = client.get(f"/games/{gid}/state").json()
        debt_before = state_before["rings"]["ring_1"]["pressures"]["maintenance_debt"]

        # Submit emergency repair
        resp = client.post(f"/games/{gid}/actions", json={
            "role": "engineer",
            "action_type": "emergency_repair",
            "ring_id": "ring_1",
            "parameters": {},
        })
        assert resp.status_code == 200

        # Advance 1 tick so action is applied
        client.post(f"/games/{gid}/advance", json={"ticks": 1})

        state_after = client.get(f"/games/{gid}/state").json()
        debt_after = state_after["rings"]["ring_1"]["pressures"]["maintenance_debt"]

        # Debt should be lower (emergency repair applied -0.05, plus the small tick accumulation)
        assert debt_after < debt_before, (
            f"Expected debt to decrease after emergency repair, "
            f"but before={debt_before:.4f} after={debt_after:.4f}"
        )

    def test_ration_resource_reduces_consumption_over_ticks(self, client: TestClient) -> None:
        gid = _create_game(client)

        # Advance without ration to get baseline food delta
        client.post(f"/games/{gid}/advance", json={"ticks": 5})
        food_at_5 = client.get(f"/games/{gid}/state").json()["rings"]["ring_1"]["resources"]["food"]

        # Create second game with ration applied
        gid2 = _create_game(client, seed=42, paused=True)
        client.post(f"/games/{gid2}/actions", json={
            "role": "captain", "action_type": "ration_resource",
            "ring_id": "ring_1", "parameters": {},
        })
        client.post(f"/games/{gid2}/advance", json={"ticks": 5})
        food_at_5_rationed = client.get(f"/games/{gid2}/state").json()["rings"]["ring_1"]["resources"]["food"]

        # Rationed game should have more food remaining (less consumed)
        assert food_at_5_rationed >= food_at_5, (
            f"Expected rationed food {food_at_5_rationed:.1f} >= unrationed {food_at_5:.1f}"
        )
