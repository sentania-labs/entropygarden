"""
Tests for the Entropy Garden REST API and WebSocket endpoint.

Games are created with paused=True by default so the background tick loop
doesn't interfere with assertions. Use the /advance endpoint for controlled
state progression.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Test client with an isolated SQLite database."""
    import os
    monkeypatch.setenv("ENTROPY_GARDEN_DB", str(tmp_path / "test.db"))  # type: ignore[arg-type]
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c  # type: ignore[misc]


def _create_game(client: TestClient, seed: int = 42, paused: bool = True) -> str:
    resp = client.post("/games", json={"seed": seed, "paused": paused})
    assert resp.status_code == 201
    return resp.json()["game_id"]


# ---------------------------------------------------------------------------
# Game creation
# ---------------------------------------------------------------------------


class TestCreateGame:
    def test_creates_game_returns_summary(self, client: TestClient) -> None:
        resp = client.post("/games", json={"seed": 42})
        assert resp.status_code == 201
        data = resp.json()
        assert data["game_id"]
        assert data["seed"] == 42
        assert data["tick"] == 0
        assert data["year"] == 0.0
        assert data["total_population"] > 0
        assert "rings" in data

    def test_rings_have_expected_keys(self, client: TestClient) -> None:
        resp = client.post("/games", json={"seed": 42, "paused": True})
        data = resp.json()
        assert set(data["rings"].keys()) == {"ring_1", "ring_2", "ring_3"}
        ring = data["rings"]["ring_1"]
        assert "population" in ring
        assert "mean_health" in ring
        assert "mean_morale" in ring
        assert "resources" in ring
        assert "pressures" in ring

    def test_different_seeds_different_game_ids(self, client: TestClient) -> None:
        id1 = _create_game(client, seed=42)
        id2 = _create_game(client, seed=99)
        assert id1 != id2

    def test_same_seed_same_game_id(self, client: TestClient) -> None:
        id1 = _create_game(client, seed=42)
        # Delete and recreate with same seed
        client.delete(f"/games/{id1}")
        id2 = _create_game(client, seed=42)
        assert id1 == id2

    def test_created_game_is_paused_when_requested(self, client: TestClient) -> None:
        resp = client.post("/games", json={"seed": 42, "paused": True})
        assert resp.json()["paused"] is True

    def test_tick_rate_reflected_in_response(self, client: TestClient) -> None:
        resp = client.post("/games", json={"seed": 42, "tick_rate": 5.0, "paused": True})
        assert resp.json()["tick_rate"] == 5.0


# ---------------------------------------------------------------------------
# List + Get
# ---------------------------------------------------------------------------


class TestListAndGet:
    def test_list_empty_initially(self, client: TestClient) -> None:
        resp = client.get("/games")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_games(self, client: TestClient) -> None:
        _create_game(client, seed=42)
        _create_game(client, seed=99)
        resp = client.get("/games")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_returns_summary(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.get(f"/games/{game_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == game_id
        assert data["tick"] == 0

    def test_get_unknown_game_returns_404(self, client: TestClient) -> None:
        resp = client.get("/games/nonexistent")
        assert resp.status_code == 404

    def test_get_full_state(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.get(f"/games/{game_id}/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == game_id
        assert "rings" in data
        assert "event_log" in data
        assert "event_cooldowns" in data

    def test_get_full_state_unknown_returns_404(self, client: TestClient) -> None:
        resp = client.get("/games/nonexistent/state")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class TestEvents:
    def test_events_empty_at_start(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.get(f"/games/{game_id}/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_events_appear_after_advancing(self, client: TestClient) -> None:
        # Advance enough ticks that random events have a chance to fire
        game_id = _create_game(client)
        client.post(f"/games/{game_id}/advance", json={"ticks": 2000})
        resp = client.get(f"/games/{game_id}/events")
        assert resp.status_code == 200
        # With 2000 ticks × 3 rings × 0.001 prob, expected ~6 equipment_malfunction events
        assert len(resp.json()) > 0

    def test_events_since_filter(self, client: TestClient) -> None:
        game_id = _create_game(client)
        client.post(f"/games/{game_id}/advance", json={"ticks": 2000})
        all_events = client.get(f"/games/{game_id}/events").json()
        if not all_events:
            pytest.skip("No events fired with this seed/tick count")
        mid_tick = all_events[len(all_events) // 2]["tick"]
        recent = client.get(f"/games/{game_id}/events?since={mid_tick}").json()
        assert len(recent) <= len(all_events)
        assert all(e["tick"] >= mid_tick for e in recent)

    def test_events_unknown_game_404(self, client: TestClient) -> None:
        resp = client.get("/games/nonexistent/events")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Advance
# ---------------------------------------------------------------------------


class TestAdvance:
    def test_advance_increments_tick(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        assert resp.status_code == 200
        assert resp.json()["tick"] == 10

    def test_advance_multiple_times_accumulates(self, client: TestClient) -> None:
        game_id = _create_game(client)
        client.post(f"/games/{game_id}/advance", json={"ticks": 5})
        resp = client.post(f"/games/{game_id}/advance", json={"ticks": 5})
        assert resp.json()["tick"] == 10

    def test_advance_unknown_game_404(self, client: TestClient) -> None:
        resp = client.post("/games/nonexistent/advance", json={"ticks": 1})
        assert resp.status_code == 404

    def test_advance_zero_ticks_rejected(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.post(f"/games/{game_id}/advance", json={"ticks": 0})
        assert resp.status_code == 422

    def test_advance_changes_population_resources(self, client: TestClient) -> None:
        game_id = _create_game(client)
        before = client.get(f"/games/{game_id}").json()
        client.post(f"/games/{game_id}/advance", json={"ticks": 365})
        after = client.get(f"/games/{game_id}").json()
        # Resources should have changed after a year of ticks
        assert before["rings"]["ring_1"]["resources"] != after["rings"]["ring_1"]["resources"]


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    def test_pause_sets_paused_flag(self, client: TestClient) -> None:
        game_id = _create_game(client, paused=False)
        resp = client.post(f"/games/{game_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["paused"] is True

    def test_resume_clears_paused_flag(self, client: TestClient) -> None:
        game_id = _create_game(client, paused=True)
        resp = client.post(f"/games/{game_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["paused"] is False

    def test_pause_unknown_game_404(self, client: TestClient) -> None:
        resp = client.post("/games/nonexistent/pause")
        assert resp.status_code == 404

    def test_resume_unknown_game_404(self, client: TestClient) -> None:
        resp = client.post("/games/nonexistent/resume")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteGame:
    def test_delete_returns_204(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.delete(f"/games/{game_id}")
        assert resp.status_code == 204

    def test_get_after_delete_returns_404(self, client: TestClient) -> None:
        game_id = _create_game(client)
        client.delete(f"/games/{game_id}")
        assert client.get(f"/games/{game_id}").status_code == 404

    def test_delete_removes_from_list(self, client: TestClient) -> None:
        game_id = _create_game(client)
        client.delete(f"/games/{game_id}")
        ids = [g["game_id"] for g in client.get("/games").json()]
        assert game_id not in ids

    def test_delete_unknown_game_404(self, client: TestClient) -> None:
        resp = client.delete("/games/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


class TestHistory:
    def test_history_empty_before_ticks(self, client: TestClient) -> None:
        game_id = _create_game(client)
        resp = client.get(f"/games/{game_id}/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_populated_after_advance(self, client: TestClient) -> None:
        game_id = _create_game(client)
        client.post(f"/games/{game_id}/advance", json={"ticks": 10})
        resp = client.get(f"/games/{game_id}/history")
        assert resp.status_code == 200
        pts = resp.json()
        assert len(pts) == 1  # tick 10 is divisible by 10
        pt = pts[0]
        assert pt["tick"] == 10
        assert "rings" in pt
        for ring in pt["rings"].values():
            assert "food" in ring
            assert "population" in ring

    def test_history_unknown_game_404(self, client: TestClient) -> None:
        resp = client.get("/games/nonexistent/history")
        assert resp.status_code == 404


class TestWebSocket:
    def test_ws_receives_initial_state(self, client: TestClient) -> None:
        game_id = _create_game(client)
        with client.websocket_connect(f"/games/{game_id}/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "state"
            assert "data" in msg
            data = msg["data"]
            assert data["game_id"] == game_id
            assert data["tick"] == 0
            assert "rings" in data

    def test_ws_ping_pong(self, client: TestClient) -> None:
        game_id = _create_game(client)
        with client.websocket_connect(f"/games/{game_id}/ws") as ws:
            ws.receive_json()  # discard initial state
            ws.send_json({"type": "ping"})
            msg = ws.receive_json()
            assert msg["type"] == "pong"

    def test_ws_unknown_game_closes(self, client: TestClient) -> None:
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/games/nonexistent/ws") as ws:
                ws.receive_json()

    def test_ws_receives_tick_updates(self, client: TestClient) -> None:
        """After advancing, the WS queue should receive broadcast updates."""
        game_id = _create_game(client)
        with client.websocket_connect(f"/games/{game_id}/ws") as ws:
            ws.receive_json()  # initial state
            # Advance via REST while connected
            client.post(f"/games/{game_id}/advance", json={"ticks": 1})
            msg = ws.receive_json()
            assert msg["type"] == "state"
            assert msg["data"]["tick"] == 1
