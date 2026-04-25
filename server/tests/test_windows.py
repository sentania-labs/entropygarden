"""
Tests for the decision window system.

Unit tests cover pure logic in sim/windows.py and sim/policy.py.
API integration tests use a paused game + /advance for controlled state progression.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from sim.policy import ALL_ROLES, compliance_check, get_absent_roles, policy_to_context
from sim.state import (
    ActionType,
    PendingAction,
    Policy,
    PolicyPriority,
    WindowStatus,
)
from sim.windows import ROLE_HIERARCHY, open_window, resolve_window

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ENTROPY_GARDEN_DB", str(tmp_path / "test.db"))  # type: ignore[arg-type]
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c  # type: ignore[misc]


def _create_game(client: TestClient, seed: int = 42, interval: int = 10) -> str:
    resp = client.post("/games", json={"seed": seed, "paused": True, "decision_window_interval": interval})
    assert resp.status_code == 201
    return resp.json()["game_id"]


def _make_action(role: str, ring_id: str = "ring_1", tick: int = 0) -> PendingAction:
    import uuid
    return PendingAction(
        action_id=str(uuid.uuid4()),
        role=role,
        action_type=ActionType.PRIORITIZE_MAINTENANCE,
        ring_id=ring_id,
        submitted_tick=tick,
    )


# ---------------------------------------------------------------------------
# Unit tests — sim/windows.py
# ---------------------------------------------------------------------------


class TestOpenWindow:
    def test_new_window_is_open(self) -> None:
        w = open_window(opened_tick=100, interval=50)
        assert w.status == WindowStatus.OPEN

    def test_closes_tick_equals_opened_plus_interval(self) -> None:
        w = open_window(opened_tick=100, interval=50)
        assert w.closes_tick == 150

    def test_window_id_is_set(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        assert w.window_id  # non-empty string

    def test_submitted_empty_on_open(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        assert w.submitted == []


class TestConflictResolution:
    def test_resolve_window_returns_closed_window(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        closed, _ = resolve_window(w, [])
        assert closed.status == WindowStatus.CLOSED

    def test_resolve_window_no_actions_returns_empty(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        closed, accepted = resolve_window(w, [])
        assert accepted == []
        assert closed.resolution is not None
        assert closed.resolution.accepted_action_ids == []
        assert closed.resolution.rejected == []

    def test_captain_overrides_engineer_same_ring(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        captain_action = _make_action("captain", ring_id="ring_1")
        engineer_action = _make_action("engineer", ring_id="ring_1")

        closed, accepted = resolve_window(w, [captain_action, engineer_action])

        assert len(accepted) == 1
        assert accepted[0].role == "captain"
        assert closed.resolution is not None
        assert len(closed.resolution.rejected) == 1
        assert closed.resolution.rejected[0].role == "engineer"
        assert closed.resolution.rejected[0].overridden_by_role == "captain"

    def test_engineer_overrides_ring_delegate_same_ring(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        engineer_action = _make_action("engineer", ring_id="ring_2")
        delegate_action = _make_action("ring_2_delegate", ring_id="ring_2")

        closed, accepted = resolve_window(w, [engineer_action, delegate_action])

        assert len(accepted) == 1
        assert accepted[0].role == "engineer"
        assert closed.resolution is not None
        assert closed.resolution.rejected[0].overridden_by_role == "engineer"

    def test_actions_on_different_rings_both_accepted(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        captain_action = _make_action("captain", ring_id="ring_1")
        engineer_action = _make_action("engineer", ring_id="ring_2")

        closed, accepted = resolve_window(w, [captain_action, engineer_action])

        assert len(accepted) == 2
        assert closed.resolution is not None
        assert closed.resolution.rejected == []

    def test_unknown_role_treated_as_lowest_authority(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        ring_delegate_action = _make_action("ring_1_delegate", ring_id="ring_1")
        unknown_action = _make_action("unknown_role", ring_id="ring_1")

        closed, accepted = resolve_window(w, [ring_delegate_action, unknown_action])

        assert len(accepted) == 1
        assert accepted[0].role == "ring_1_delegate"

    def test_single_action_not_rejected(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        action = _make_action("engineer", ring_id="ring_1")
        closed, accepted = resolve_window(w, [action])
        assert len(accepted) == 1
        assert closed.resolution is not None
        assert closed.resolution.rejected == []

    def test_resolution_accepted_ids_match_accepted_actions(self) -> None:
        w = open_window(opened_tick=0, interval=10)
        captain_action = _make_action("captain", ring_id="ring_1")
        engineer_action = _make_action("engineer", ring_id="ring_1")

        closed, accepted = resolve_window(w, [captain_action, engineer_action])

        assert closed.resolution is not None
        assert set(closed.resolution.accepted_action_ids) == {a.action_id for a in accepted}


class TestRoleHierarchy:
    def test_hierarchy_order(self) -> None:
        assert ROLE_HIERARCHY[0] == "captain"
        assert ROLE_HIERARCHY[-1] == "ring_3_delegate"

    def test_all_seven_roles_in_hierarchy(self) -> None:
        assert len(ROLE_HIERARCHY) == 7


# ---------------------------------------------------------------------------
# Unit tests — sim/policy.py
# ---------------------------------------------------------------------------


class TestGetAbsentRoles:
    def test_returns_roles_not_in_submitted(self) -> None:
        absent = get_absent_roles(["captain"], ["captain", "engineer"])
        assert absent == ["engineer"]

    def test_empty_when_all_submitted(self) -> None:
        absent = get_absent_roles(["captain", "engineer"], ["captain", "engineer"])
        assert absent == []

    def test_all_absent_when_none_submitted(self) -> None:
        absent = get_absent_roles([], ["captain", "engineer"])
        assert set(absent) == {"captain", "engineer"}

    def test_defaults_to_all_roles(self) -> None:
        absent = get_absent_roles([])
        assert set(absent) == set(ALL_ROLES)

    def test_extra_submitted_roles_ignored(self) -> None:
        # A role submitted but isn't in active_roles — no crash, just ignored
        absent = get_absent_roles(["unknown_role"], ["captain"])
        assert absent == ["captain"]


class TestComplianceCheck:
    def test_full_compliance_always_true(self) -> None:
        p = Policy(role="engineer", compliance=1.0)
        assert compliance_check(p, 0.0) is True
        assert compliance_check(p, 0.99) is True

    def test_zero_compliance_always_false(self) -> None:
        p = Policy(role="engineer", compliance=0.0)
        assert compliance_check(p, 0.0) is False
        assert compliance_check(p, 0.5) is False

    def test_half_compliance_threshold(self) -> None:
        p = Policy(role="engineer", compliance=0.5)
        assert compliance_check(p, 0.49) is True
        assert compliance_check(p, 0.50) is False


class TestPolicyToContext:
    def test_no_priorities_returns_none_set(self) -> None:
        p = Policy(role="engineer")
        result = policy_to_context(p)
        assert "none set" in result
        assert "engineer" in result

    def test_priorities_serialized(self) -> None:
        p = Policy(
            role="engineer",
            priorities=[
                PolicyPriority(action_type="prioritize_maintenance", ring_id="ring_2", note="debt highest"),
                PolicyPriority(action_type="emergency_repair", ring_id="ring_1"),
            ],
        )
        result = policy_to_context(p)
        assert "prioritize_maintenance" in result
        assert "ring_2" in result
        assert "debt highest" in result
        assert "emergency_repair" in result
        assert "ring_1" in result

    def test_note_omitted_when_empty(self) -> None:
        p = Policy(role="captain", priorities=[PolicyPriority(action_type="boost_production", ring_id="ring_3")])
        result = policy_to_context(p)
        assert "()" not in result


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


class TestWindowCreation:
    def test_no_window_at_tick_zero(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.get(f"/games/{game_id}/window/current")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_window_opens_after_interval(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        resp = client.get(f"/games/{game_id}/window/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["status"] == "open"
        assert data["opened_tick"] == 10
        assert data["closes_tick"] == 20

    def test_window_404_unknown_game(self, client: TestClient) -> None:
        resp = client.get("/games/nonexistent/window/current")
        assert resp.status_code == 404


class TestWindowActionSubmission:
    def test_submit_action_during_open_window(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        resp = client.post(
            f"/games/{game_id}/window/action",
            json={"role": "engineer", "action_type": "prioritize_maintenance", "ring_id": "ring_1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_submit_action_rejected_when_no_window(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        # Tick 0 — no window open yet
        resp = client.post(
            f"/games/{game_id}/window/action",
            json={"role": "engineer", "action_type": "prioritize_maintenance", "ring_id": "ring_1"},
        )
        assert resp.status_code == 409

    def test_submit_records_role_in_window_submitted(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        client.post(
            f"/games/{game_id}/window/action",
            json={"role": "captain", "action_type": "prioritize_maintenance", "ring_id": "ring_1"},
        )
        window = client.get(f"/games/{game_id}/window/current").json()
        assert "captain" in window["submitted"]


class TestWindowHistory:
    def test_history_empty_before_first_close(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        resp = client.get(f"/games/{game_id}/window/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_accumulates_after_close(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        # Advance 10 → opens window 1
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        # Advance 10 more → closes window 1, opens window 2
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        history = client.get(f"/games/{game_id}/window/history").json()
        assert len(history) == 1
        assert history[0]["status"] == "closed"

    def test_history_grows_with_each_interval(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        client.post(f"/games/{game_id}/advance", json={"ticks": 30})
        history = client.get(f"/games/{game_id}/window/history").json()
        assert len(history) == 2


class TestPolicyEndpoints:
    def test_get_policy_returns_null_when_not_set(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.get(f"/games/{game_id}/window/policy/engineer")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_set_and_get_policy(self, client: TestClient) -> None:
        game_id = _create_game(client)
        policy_data = {
            "role": "engineer",
            "priorities": [
                {"action_type": "prioritize_maintenance", "ring_id": "ring_2", "parameters": {}, "note": "ring_2 debt highest"},
            ],
            "compliance": 1.0,
        }
        put_resp = client.put(f"/games/{game_id}/window/policy/engineer", json=policy_data)
        assert put_resp.status_code == 200

        get_resp = client.get(f"/games/{game_id}/window/policy/engineer")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["role"] == "engineer"
        assert data["priorities"][0]["action_type"] == "prioritize_maintenance"

    def test_policy_persists_across_advance(self, client: TestClient) -> None:
        game_id = _create_game(client, interval=10)
        policy_data = {
            "role": "engineer",
            "priorities": [{"action_type": "prioritize_maintenance", "ring_id": "ring_1", "parameters": {}, "note": ""}],
            "compliance": 1.0,
        }
        client.put(f"/games/{game_id}/window/policy/engineer", json=policy_data)
        client.post(f"/games/{game_id}/advance", json={"ticks": 5})

        resp = client.get(f"/games/{game_id}/window/policy/engineer")
        assert resp.json() is not None
        assert resp.json()["role"] == "engineer"


class TestPolicyFallback:
    def test_fallback_generates_action_for_absent_role(self, client: TestClient) -> None:
        """Deterministic fallback path (no LLM): absent role with policy should
        get a PendingAction submitted at window close."""
        game_id = _create_game(client, interval=10)
        policy_data = {
            "role": "engineer",
            "priorities": [{"action_type": "prioritize_maintenance", "ring_id": "ring_1", "parameters": {}, "note": ""}],
            "compliance": 1.0,
        }
        client.put(f"/games/{game_id}/window/policy/engineer", json=policy_data)

        # Open first window
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        # Close first window (advance to next interval) — policy fallback should fire
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})

        history = client.get(f"/games/{game_id}/window/history").json()
        assert len(history) == 1
        closed_window = history[0]
        assert "engineer" in closed_window["resolution"]["fallback_roles"]

    def test_no_fallback_when_no_policy_set(self, client: TestClient) -> None:
        """Absent role with no policy → no action, no fallback_roles entry."""
        game_id = _create_game(client, interval=10)
        # Don't set any policy
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})

        history = client.get(f"/games/{game_id}/window/history").json()
        assert len(history) == 1
        # fallback_roles is empty when no policies set
        assert history[0]["resolution"]["fallback_roles"] == []
