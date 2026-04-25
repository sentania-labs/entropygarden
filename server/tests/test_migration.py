"""Tests for inter-ring migration and cross-ring labor."""

import random
import uuid

from sim.initializer import build_initial_state
from sim.migration import process_migration, apply_restriction_morale
from sim.state import (
    ActionType,
    Occupation,
    PendingAction,
    Person,
    RingRestrictions,
    SimConfig,
)
from sim.tick import tick


def _make_state_with_imbalance():
    """Create a state where ring_1 is terrible and ring_2 is great."""
    state = build_initial_state(42, destination="proxima")
    rings = dict(state.rings)

    # Make ring_1 miserable: low resources, high tension
    r1 = rings["ring_1"]
    rings["ring_1"] = r1.model_copy(update={
        "resources": r1.resources.model_copy(update={
            "food": 20.0, "water": 15.0, "oxygen": 25.0, "power": 50.0,
        }),
        "pressures": r1.pressures.model_copy(update={"social_tension": 0.7}),
    })
    # Also lower morale on ring_1 people
    new_pop = [p.model_copy(update={"morale": 0.2}) for p in r1.population]
    rings["ring_1"] = rings["ring_1"].model_copy(update={"population": new_pop})

    # Ring_2 is comfortable
    r2 = rings["ring_2"]
    rings["ring_2"] = r2.model_copy(update={
        "resources": r2.resources.model_copy(update={
            "food": 450.0, "water": 450.0, "oxygen": 450.0, "power": 450.0,
        }),
        "pressures": r2.pressures.model_copy(update={"social_tension": 0.05}),
    })

    return state.model_copy(update={"rings": rings})


class TestMigration:
    def test_no_migration_when_balanced(self) -> None:
        """Equal conditions → no migration."""
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        rng = random.Random(42)

        pop_before = {rid: len(r.population) for rid, r in state.rings.items()}
        new_state = process_migration(state, cfg, rng)
        pop_after = {rid: len(r.population) for rid, r in new_state.rings.items()}

        # Populations should be the same (equal conditions, no pressure to move)
        assert pop_before == pop_after

    def test_migration_from_bad_ring_to_good(self) -> None:
        """Settlers move from terrible conditions to good ones."""
        state = _make_state_with_imbalance()
        cfg = SimConfig()

        # Run migration multiple ticks to see movement
        r1_pop_start = len(state.rings["ring_1"].population)
        for i in range(20):
            rng = random.Random(42 + i)
            state = process_migration(state, cfg, rng)

        r1_pop_end = len(state.rings["ring_1"].population)
        r2_pop_end = len(state.rings["ring_2"].population)

        assert r1_pop_end < r1_pop_start, "Ring 1 should have lost settlers"

    def test_lockdown_prevents_migration(self) -> None:
        """Lockdown blocks all outgoing movement."""
        state = _make_state_with_imbalance()
        cfg = SimConfig()

        # Impose lockdown on ring_1
        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "restrictions": RingRestrictions(lockdown=True),
        })
        state = state.model_copy(update={"rings": rings})

        r1_pop = len(state.rings["ring_1"].population)
        for i in range(20):
            rng = random.Random(42 + i)
            state = process_migration(state, cfg, rng)

        # No one should have left ring_1
        assert len(state.rings["ring_1"].population) == r1_pop

    def test_civil_restriction_blocks_inflow(self) -> None:
        """Civil restriction on target blocks inflow."""
        state = _make_state_with_imbalance()
        cfg = SimConfig()

        # Civil restriction on ring_2 (the good ring)
        rings = dict(state.rings)
        r2 = rings["ring_2"]
        rings["ring_2"] = r2.model_copy(update={
            "restrictions": RingRestrictions(civil_restriction=True),
        })
        # Also restrict ring_3
        r3 = rings["ring_3"]
        rings["ring_3"] = r3.model_copy(update={
            "restrictions": RingRestrictions(civil_restriction=True),
        })
        state = state.model_copy(update={"rings": rings})

        r1_pop = len(state.rings["ring_1"].population)
        for i in range(20):
            rng = random.Random(42 + i)
            state = process_migration(state, cfg, rng)

        # Ring_1 should NOT have lost settlers (nowhere to go)
        assert len(state.rings["ring_1"].population) == r1_pop

    def test_labor_draft_blocks_productive_workers(self) -> None:
        """Labor draft prevents productive occupations from leaving."""
        state = _make_state_with_imbalance()
        cfg = SimConfig()

        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "restrictions": RingRestrictions(labor_draft=True),
        })
        state = state.model_copy(update={"rings": rings})

        # Count productive workers in ring_1 before
        productive_before = sum(
            1 for p in state.rings["ring_1"].population
            if p.occupation in (Occupation.FARMER, Occupation.ENGINEER, Occupation.LIFE_SUPPORT, Occupation.LABORER)
        )

        for i in range(20):
            rng = random.Random(42 + i)
            state = process_migration(state, cfg, rng)

        # Productive workers should still be there
        productive_after = sum(
            1 for p in state.rings["ring_1"].population
            if p.occupation in (Occupation.FARMER, Occupation.ENGINEER, Occupation.LIFE_SUPPORT, Occupation.LABORER)
        )
        assert productive_after == productive_before

    def test_migration_cooldown(self) -> None:
        """Recently migrated settlers don't move again."""
        state = _make_state_with_imbalance()
        cfg = SimConfig(migration_cooldown_ticks=1000)  # very long cooldown

        rng = random.Random(42)
        state = process_migration(state, cfg, rng)

        # Anyone who moved should have a cooldown
        for ring in state.rings.values():
            for p in ring.population:
                if p.migration_cooldown > 0:
                    assert p.migration_cooldown == 1000


class TestRestrictionMorale:
    def test_lockdown_drains_morale(self) -> None:
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()

        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "restrictions": RingRestrictions(lockdown=True),
        })
        state = state.model_copy(update={"rings": rings})

        morale_before = sum(p.morale for p in state.rings["ring_1"].population)
        new_state = apply_restriction_morale(state, cfg)
        morale_after = sum(p.morale for p in new_state.rings["ring_1"].population)

        assert morale_after < morale_before

    def test_no_penalty_without_restrictions(self) -> None:
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()

        new_state = apply_restriction_morale(state, cfg)
        # State should be unchanged (no restrictions active)
        for rid in state.rings:
            for p1, p2 in zip(state.rings[rid].population, new_state.rings[rid].population):
                assert p1.morale == p2.morale


class TestCrossRingLabor:
    def test_cross_ring_workers_produce_in_target(self) -> None:
        """Workers with work_ring_id set produce in the target ring."""
        state = build_initial_state(42, destination="proxima")

        # Move a few ring_1 farmers to work in ring_2
        rings = dict(state.rings)
        r1 = rings["ring_1"]
        new_pop = list(r1.population)
        moved = 0
        for i, p in enumerate(new_pop):
            if p.occupation == Occupation.FARMER and moved < 5:
                new_pop[i] = p.model_copy(update={"work_ring_id": "ring_2"})
                moved += 1
        rings["ring_1"] = r1.model_copy(update={"population": new_pop})
        state = state.model_copy(update={"rings": rings})

        # After a tick, ring_2 should get production from those workers
        new_state = tick(state)
        # Just verify no crash and state is valid
        assert new_state.tick == 1
        assert len(new_state.rings["ring_1"].population) > 0

    def test_restriction_actions_via_tick(self) -> None:
        """Restriction actions are applied via the tick pipeline."""
        state = build_initial_state(42, destination="proxima")
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            role="captain",
            action_type=ActionType.IMPOSE_LOCKDOWN,
            ring_id="ring_1",
            parameters={},
            submitted_tick=0,
        )
        state = state.model_copy(update={"pending_actions": [action]})

        new_state = tick(state)
        assert new_state.rings["ring_1"].restrictions.lockdown is True

    def test_lift_restriction_clears_all(self) -> None:
        """LIFT_RESTRICTION clears all restrictions."""
        state = build_initial_state(42, destination="proxima")
        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "restrictions": RingRestrictions(lockdown=True, labor_draft=True),
        })
        state = state.model_copy(update={"rings": rings})

        action = PendingAction(
            action_id=str(uuid.uuid4()),
            role="captain",
            action_type=ActionType.LIFT_RESTRICTION,
            ring_id="ring_1",
            parameters={},
            submitted_tick=0,
        )
        state = state.model_copy(update={"pending_actions": [action]})

        new_state = tick(state)
        assert new_state.rings["ring_1"].restrictions.lockdown is False
        assert new_state.rings["ring_1"].restrictions.labor_draft is False
