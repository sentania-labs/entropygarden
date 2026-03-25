"""Tests for the tick engine."""

import pytest

from sim.initializer import build_initial_state
from sim.state import GameState, Occupation, SimConfig


def small_cfg(**kwargs: object) -> SimConfig:
    """SimConfig with tiny population for fast multi-tick tests."""
    return SimConfig(initial_pop_per_ring=30, **kwargs)  # type: ignore[arg-type]


class TestDeterminism:
    def test_same_seed_same_output(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs1 = build_initial_state(seed=42, config=cfg)
        gs2 = build_initial_state(seed=42, config=cfg)
        result1 = tick(gs1, cfg)
        result2 = tick(gs2, cfg)
        assert result1.model_dump() == result2.model_dump()

    def test_different_seed_different_output(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs1 = build_initial_state(seed=42, config=cfg)
        gs2 = build_initial_state(seed=99, config=cfg)
        result1 = tick(gs1, cfg)
        result2 = tick(gs2, cfg)
        assert result1.seed != result2.seed

    def test_multi_tick_determinism(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()

        def advance(seed: int, n: int) -> GameState:
            gs = build_initial_state(seed=seed, config=cfg)
            for _ in range(n):
                gs = tick(gs, cfg)
            return gs

        r1 = advance(42, 10)
        r2 = advance(42, 10)
        assert r1.model_dump() == r2.model_dump()


class TestTickCounter:
    def test_tick_increments_by_one(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs = build_initial_state(seed=42, config=cfg)
        assert gs.tick == 0
        gs2 = tick(gs, cfg)
        assert gs2.tick == 1

    def test_advance_365_ticks(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs = build_initial_state(seed=42, config=cfg)
        for _ in range(365):
            gs = tick(gs, cfg)
        assert gs.tick == 365
        assert gs.year == pytest.approx(1.0)


class TestResourceDepletion:
    def test_food_decreases_each_tick(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs = build_initial_state(seed=42, config=cfg)
        # Remove all farmers to ensure net consumption
        for ring_id, ring in gs.rings.items():
            new_pop = [
                p.model_copy(update={"occupation": Occupation.LABORER})
                if p.occupation == Occupation.FARMER
                else p
                for p in ring.population
            ]
            gs.rings[ring_id] = ring.model_copy(update={"population": new_pop})

        initial_food = sum(r.resources.food for r in gs.rings.values())
        gs2 = tick(gs, cfg)
        final_food = sum(r.resources.food for r in gs2.rings.values())
        assert final_food < initial_food

    def test_starvation_eventually_causes_deaths(self) -> None:
        from sim.tick import tick

        cfg = small_cfg(
            food_per_person=1.0,    # extremely high consumption
            food_per_farmer=0.0,    # no production
        )
        gs = build_initial_state(seed=42, config=cfg)
        initial_pop = sum(len(r.population) for r in gs.rings.values())

        for _ in range(100):
            gs = tick(gs, cfg)

        final_pop = sum(len(r.population) for r in gs.rings.values())
        assert final_pop < initial_pop


class TestPressureTrends:
    def test_maintenance_debt_rises_without_engineers(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs = build_initial_state(seed=42, config=cfg)
        # Remove all engineers
        for ring_id, ring in gs.rings.items():
            new_pop = [
                p.model_copy(update={"occupation": Occupation.LABORER})
                if p.occupation == Occupation.ENGINEER
                else p
                for p in ring.population
            ]
            gs.rings[ring_id] = ring.model_copy(update={"population": new_pop})

        initial_debt = sum(r.pressures.maintenance_debt for r in gs.rings.values())
        for _ in range(30):
            gs = tick(gs, cfg)
        final_debt = sum(r.pressures.maintenance_debt for r in gs.rings.values())
        assert final_debt > initial_debt

    def test_ecological_drift_rises_over_one_year(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs = build_initial_state(seed=42, config=cfg)
        initial_drift = sum(r.pressures.ecological_drift for r in gs.rings.values())
        for _ in range(365):
            gs = tick(gs, cfg)
        final_drift = sum(r.pressures.ecological_drift for r in gs.rings.values())
        assert final_drift > initial_drift


class TestImmutability:
    def test_tick_does_not_mutate_input(self) -> None:
        from sim.tick import tick

        cfg = small_cfg()
        gs = build_initial_state(seed=42, config=cfg)
        original_tick = gs.tick
        original_dump = gs.model_dump()
        tick(gs, cfg)
        assert gs.tick == original_tick
        assert gs.model_dump() == original_dump
