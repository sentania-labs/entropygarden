"""Tests for the event system."""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.events import EventDef, _apply_effects, _check_threshold, evaluate_events, load_events
from sim.initializer import build_initial_state
from sim.state import GameState, HiddenPressures, SimConfig
from sim.tick import tick

_EVENTS_YAML = Path(__file__).parent.parent.parent / "data" / "events.yaml"


def small_cfg(**kwargs: object) -> SimConfig:
    return SimConfig(initial_pop_per_ring=30, **kwargs)  # type: ignore[arg-type]


def small_state(seed: int = 42, cfg: SimConfig | None = None) -> GameState:
    return build_initial_state(seed=seed, config=cfg or small_cfg())


# ---------------------------------------------------------------------------
# EventDef loading
# ---------------------------------------------------------------------------


class TestLoadEvents:
    def test_loads_all_events(self) -> None:
        events = load_events(_EVENTS_YAML)
        assert len(events) == 12

    def test_event_fields_present(self) -> None:
        events = load_events(_EVENTS_YAML)
        for ev in events:
            assert ev.id
            assert ev.name
            assert ev.description
            assert ev.trigger
            assert ev.scope in ("ring", "ship")
            assert isinstance(ev.effects, dict)

    def test_threshold_events_have_required_trigger_fields(self) -> None:
        events = load_events(_EVENTS_YAML)
        for ev in events:
            if ev.trigger["type"] == "threshold":
                assert "pressure" in ev.trigger
                assert "threshold" in ev.trigger
                assert "cooldown_ticks" in ev.trigger

    def test_random_events_have_probability(self) -> None:
        events = load_events(_EVENTS_YAML)
        for ev in events:
            if ev.trigger["type"] == "random":
                assert "probability_per_tick" in ev.trigger

    def test_ship_scoped_event_exists(self) -> None:
        events = load_events(_EVENTS_YAML)
        ship_events = [e for e in events if e.scope == "ship"]
        assert len(ship_events) >= 1


# ---------------------------------------------------------------------------
# Threshold trigger logic
# ---------------------------------------------------------------------------


class TestCheckThreshold:
    def _make_event(self, pressure: str, threshold: float, cooldown: int = 0) -> EventDef:
        return EventDef(
            id="test_event",
            name="Test",
            description="Test event",
            trigger={"type": "threshold", "pressure": pressure, "threshold": threshold, "cooldown_ticks": cooldown},
            scope="ring",
            effects={},
        )

    def test_fires_when_above_threshold(self) -> None:
        state = small_state()
        ring = list(state.rings.values())[0]
        # Force high maintenance debt
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.8})
        })
        event = self._make_event("maintenance_debt", 0.5)
        assert _check_threshold(event, ring, tick=0, cooldowns={}) is True

    def test_does_not_fire_when_below_threshold(self) -> None:
        state = small_state()
        ring = list(state.rings.values())[0]
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.3})
        })
        event = self._make_event("maintenance_debt", 0.5)
        assert _check_threshold(event, ring, tick=0, cooldowns={}) is False

    def test_fires_at_exact_threshold(self) -> None:
        state = small_state()
        ring = list(state.rings.values())[0]
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.5})
        })
        event = self._make_event("maintenance_debt", 0.5)
        assert _check_threshold(event, ring, tick=0, cooldowns={}) is True

    def test_cooldown_prevents_refiring(self) -> None:
        state = small_state()
        ring = list(state.rings.values())[0]
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.8})
        })
        event = self._make_event("maintenance_debt", 0.5, cooldown=730)
        # Fired on tick 0, check on tick 100 — not enough
        cooldowns = {"test_event:ring_1": 0}
        assert _check_threshold(event, ring, tick=100, cooldowns=cooldowns) is False

    def test_cooldown_allows_firing_after_elapsed(self) -> None:
        state = small_state()
        ring = list(state.rings.values())[0]
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.8})
        })
        event = self._make_event("maintenance_debt", 0.5, cooldown=730)
        # Fired on tick 0, check on tick 730 — exactly at cooldown
        cooldowns = {"test_event:ring_1": 0}
        assert _check_threshold(event, ring, tick=730, cooldowns=cooldowns) is True

    def test_fires_on_first_occurrence_no_cooldown_entry(self) -> None:
        state = small_state()
        ring = list(state.rings.values())[0]
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"ecological_drift": 0.9})
        })
        event = self._make_event("ecological_drift", 0.5, cooldown=730)
        # No entry in cooldowns — should fire
        assert _check_threshold(event, ring, tick=0, cooldowns={}) is True


# ---------------------------------------------------------------------------
# Effect application
# ---------------------------------------------------------------------------


class TestApplyEffects:
    import random as _random_module

    def _dummy_rng(self) -> object:
        import random
        return random.Random(42)

    def test_resource_delta_applied(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        original_food = ring.resources.food

        result = _apply_effects(ring, {"food_delta": -50.0}, self._dummy_rng(), cfg)
        assert result.resources.food == pytest.approx(original_food - 50.0)

    def test_resource_clamped_at_zero(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]

        result = _apply_effects(ring, {"food_delta": -9999.0}, self._dummy_rng(), cfg)
        assert result.resources.food == 0.0

    def test_resource_clamped_at_capacity(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]

        result = _apply_effects(ring, {"food_delta": 9999.0}, self._dummy_rng(), cfg)
        assert result.resources.food == cfg.resource_capacity

    def test_pressure_delta_applied(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        original = ring.pressures.maintenance_debt

        result = _apply_effects(ring, {"maintenance_debt_delta": 0.1}, self._dummy_rng(), cfg)
        assert result.pressures.maintenance_debt == pytest.approx(original + 0.1)

    def test_pressure_clamped_at_one(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        ring = ring.model_copy(update={
            "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.95})
        })
        result = _apply_effects(ring, {"maintenance_debt_delta": 0.5}, self._dummy_rng(), cfg)
        assert result.pressures.maintenance_debt == 1.0

    def test_morale_delta_applied_to_all_people(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        before = [p.morale for p in ring.population]

        result = _apply_effects(ring, {"morale_delta": -0.1}, self._dummy_rng(), cfg)
        after = [p.morale for p in result.population]

        for b, a in zip(before, after):
            assert a == pytest.approx(max(0.0, b - 0.1))

    def test_health_delta_applied_to_all_people(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]

        result = _apply_effects(ring, {"health_delta": -0.05}, self._dummy_rng(), cfg)
        for p in result.population:
            assert p.health >= 0.0

    def test_population_loss_removes_lowest_health(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        original_count = len(ring.population)

        result = _apply_effects(ring, {"population_loss": 3}, self._dummy_rng(), cfg)
        assert len(result.population) == original_count - 3

    def test_population_loss_removes_sickest(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        before_sorted = sorted(ring.population, key=lambda p: p.health)
        removed_ids = {p.person_id for p in before_sorted[:3]}

        result = _apply_effects(ring, {"population_loss": 3}, self._dummy_rng(), cfg)
        result_ids = {p.person_id for p in result.population}
        assert not removed_ids & result_ids  # no overlap

    def test_no_mutation_of_input(self) -> None:
        state = small_state()
        cfg = small_cfg()
        ring = list(state.rings.values())[0]
        original_food = ring.resources.food

        _apply_effects(ring, {"food_delta": -50.0}, self._dummy_rng(), cfg)
        assert ring.resources.food == original_food


# ---------------------------------------------------------------------------
# evaluate_events: integration
# ---------------------------------------------------------------------------


def _make_threshold_event(
    event_id: str,
    pressure: str,
    threshold: float,
    effects: dict[str, float],
    cooldown: int = 0,
    scope: str = "ring",
) -> EventDef:
    return EventDef(
        id=event_id,
        name=event_id,
        description="",
        trigger={"type": "threshold", "pressure": pressure, "threshold": threshold, "cooldown_ticks": cooldown},
        scope=scope,
        effects=effects,
    )


def _make_random_event(
    event_id: str,
    probability: float,
    effects: dict[str, float],
    scope: str = "ring",
) -> EventDef:
    return EventDef(
        id=event_id,
        name=event_id,
        description="",
        trigger={"type": "random", "probability_per_tick": probability},
        scope=scope,
        effects=effects,
    )


class TestEvaluateEvents:
    def test_threshold_event_fires_when_exceeded(self) -> None:
        state = small_state()
        cfg = small_cfg()
        # Force all rings to high maintenance debt
        new_rings = {}
        for ring_id, ring in state.rings.items():
            new_rings[ring_id] = ring.model_copy(update={
                "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.8})
            })
        state = state.model_copy(update={"rings": new_rings})

        event = _make_threshold_event("test_debt", "maintenance_debt", 0.5, {"power_delta": -20.0})
        new_state, fired = evaluate_events(state, [event], cfg)

        assert len(fired) == 3  # one per ring
        assert all(ev.event_id == "test_debt" for ev in fired)

    def test_threshold_event_does_not_fire_below_threshold(self) -> None:
        state = small_state()
        cfg = small_cfg()
        event = _make_threshold_event("test_debt", "maintenance_debt", 0.9, {"power_delta": -20.0})
        _, fired = evaluate_events(state, [event], cfg)
        assert len(fired) == 0

    def test_effects_applied_to_state(self) -> None:
        state = small_state()
        cfg = small_cfg()
        new_rings = {}
        for ring_id, ring in state.rings.items():
            new_rings[ring_id] = ring.model_copy(update={
                "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.9})
            })
        state = state.model_copy(update={"rings": new_rings})

        original_power = {rid: ring.resources.power for rid, ring in state.rings.items()}
        event = _make_threshold_event("test_power", "maintenance_debt", 0.5, {"power_delta": -30.0})
        new_state, fired = evaluate_events(state, [event], cfg)

        for ring_id, ring in new_state.rings.items():
            assert ring.resources.power < original_power[ring_id]

    def test_cooldown_prevents_double_fire(self) -> None:
        state = small_state()
        cfg = small_cfg()
        # Force high pressure
        new_rings = {}
        for ring_id, ring in state.rings.items():
            new_rings[ring_id] = ring.model_copy(update={
                "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.9})
            })
        state = state.model_copy(update={"rings": new_rings})

        event = _make_threshold_event("test_cd", "maintenance_debt", 0.5, {}, cooldown=365)
        # First evaluation — should fire
        state1, fired1 = evaluate_events(state, [event], cfg)
        assert len(fired1) == 3

        # Second evaluation at same tick — cooldowns prevent re-fire
        state2, fired2 = evaluate_events(state1, [event], cfg)
        assert len(fired2) == 0

    def test_event_log_accumulates(self) -> None:
        state = small_state()
        cfg = small_cfg()
        new_rings = {}
        for ring_id, ring in state.rings.items():
            new_rings[ring_id] = ring.model_copy(update={
                "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.9})
            })
        state = state.model_copy(update={"rings": new_rings})

        event = _make_threshold_event("log_test", "maintenance_debt", 0.5, {}, cooldown=0)
        state, _ = evaluate_events(state, [event], cfg)
        assert len(state.event_log) == 3

        # Advance tick so cooldown resets (cooldown=0 means always fires)
        state = state.model_copy(update={"tick": state.tick + 1})
        state, _ = evaluate_events(state, [event], cfg)
        assert len(state.event_log) == 6

    def test_ship_wide_event_fires_once(self) -> None:
        state = small_state()
        cfg = small_cfg()
        event = _make_random_event("stellar", 1.0, {"health_delta": -0.01}, scope="ship")
        _, fired = evaluate_events(state, [event], cfg)
        assert len(fired) == 1
        assert fired[0].ring_id is None

    def test_ship_wide_event_applies_to_all_rings(self) -> None:
        state = small_state()
        cfg = small_cfg()
        original_health = {
            ring_id: sum(p.health for p in ring.population)
            for ring_id, ring in state.rings.items()
        }
        event = _make_random_event("stellar", 1.0, {"health_delta": -0.05}, scope="ship")
        new_state, _ = evaluate_events(state, [event], cfg)

        for ring_id, ring in new_state.rings.items():
            new_health = sum(p.health for p in ring.population)
            assert new_health < original_health[ring_id]

    def test_no_mutation_of_input_state(self) -> None:
        state = small_state()
        cfg = small_cfg()
        original_dump = state.model_dump()
        event = _make_random_event("mutate_test", 1.0, {"morale_delta": -0.1})
        evaluate_events(state, [event], cfg)
        assert state.model_dump() == original_dump

    def test_empty_event_list_returns_unchanged_state(self) -> None:
        state = small_state()
        cfg = small_cfg()
        new_state, fired = evaluate_events(state, [], cfg)
        assert fired == []
        assert new_state.rings == state.rings
        assert new_state.event_log == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestEventDeterminism:
    def test_same_seed_same_events(self) -> None:
        cfg = small_cfg()
        events = load_events(_EVENTS_YAML)

        def run(seed: int, n: int) -> list[str]:
            state = build_initial_state(seed=seed, config=cfg)
            for _ in range(n):
                state = tick(state, cfg, events)
            return [e.event_id for e in state.event_log]

        assert run(42, 100) == run(42, 100)

    def test_different_seed_different_random_events(self) -> None:
        cfg = small_cfg()
        events = [_make_random_event("rand_test", 0.5, {"morale_delta": 0.01})]

        def run(seed: int, n: int) -> list[str]:
            state = build_initial_state(seed=seed, config=cfg)
            for _ in range(n):
                state = tick(state, cfg, events)
            return [f"{e.tick}:{e.ring_id}" for e in state.event_log]

        # Very unlikely to be identical with different seeds
        result_42 = run(42, 50)
        result_99 = run(99, 50)
        assert result_42 != result_99


# ---------------------------------------------------------------------------
# Tick integration
# ---------------------------------------------------------------------------


class TestTickIntegration:
    def test_tick_with_events_increments_normally(self) -> None:
        cfg = small_cfg()
        state = build_initial_state(seed=42, config=cfg)
        events = load_events(_EVENTS_YAML)
        new_state = tick(state, cfg, events)
        assert new_state.tick == 1

    def test_tick_without_events_unchanged_interface(self) -> None:
        cfg = small_cfg()
        state = build_initial_state(seed=42, config=cfg)
        new_state = tick(state, cfg)
        assert new_state.tick == 1
        assert new_state.event_log == []

    def test_events_fire_after_many_ticks_under_pressure(self) -> None:
        """Threshold events should fire as pressures build over time."""
        cfg = small_cfg(
            maintenance_debt_rate=0.005,       # accelerate debt for test
            initial_maintenance_debt=0.45,     # start close to threshold
        )
        state = build_initial_state(seed=42, config=cfg)
        events = [_make_threshold_event("fast_debt", "maintenance_debt", 0.5, {}, cooldown=0)]

        for _ in range(20):
            state = tick(state, cfg, events)

        assert len(state.event_log) > 0

    def test_full_events_yaml_runs_without_error(self) -> None:
        cfg = small_cfg()
        state = build_initial_state(seed=42, config=cfg)
        events = load_events(_EVENTS_YAML)
        for _ in range(50):
            state = tick(state, cfg, events)
        # Just verify it runs cleanly
        assert state.tick == 50
