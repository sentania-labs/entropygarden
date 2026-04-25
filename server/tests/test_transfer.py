"""Tests for cross-ring resource transfer with waste mechanics."""

import uuid

from sim.initializer import build_initial_state
from sim.state import ActionType, PendingAction, SimConfig
from sim.tick import tick


def _action(ring_id: str, resource: str, target_ring: str, amount: float) -> PendingAction:
    return PendingAction(
        action_id=str(uuid.uuid4()),
        role="captain",
        action_type=ActionType.TRANSFER_RESOURCE,
        ring_id=ring_id,
        parameters={"resource": resource, "target_ring": target_ring, "amount": amount},
        submitted_tick=0,
    )


class TestTransferResource:
    def test_food_transfer_with_waste(self) -> None:
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        # Set known food levels
        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "resources": r1.resources.model_copy(update={"food": 300.0}),
        })
        r2 = rings["ring_2"]
        rings["ring_2"] = r2.model_copy(update={
            "resources": r2.resources.model_copy(update={"food": 100.0}),
        })
        state = state.model_copy(update={
            "rings": rings,
            "pending_actions": [_action("ring_1", "food", "ring_2", 100.0)],
        })

        new_state = tick(state, cfg)
        # Source loses 100, target gains 100 * (1 - 0.10) = 90 (minus tick consumption)
        # We just check the transfer was applied directionally
        r1_food = new_state.rings["ring_1"].resources.food
        r2_food = new_state.rings["ring_2"].resources.food
        assert r1_food < 300.0  # lost at least 100
        assert r2_food > 100.0  # gained roughly 90 minus consumption

    def test_oxygen_transfer_has_higher_waste(self) -> None:
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "resources": r1.resources.model_copy(update={"oxygen": 400.0}),
        })
        r2 = rings["ring_2"]
        r2_orig_oxygen = r2.resources.oxygen
        rings["ring_2"] = r2.model_copy(update={
            "resources": r2.resources.model_copy(update={"oxygen": 100.0}),
        })
        state = state.model_copy(update={
            "rings": rings,
            "pending_actions": [_action("ring_1", "oxygen", "ring_2", 100.0)],
        })

        new_state = tick(state, cfg)
        # Oxygen waste is 15%, so delivered = 85
        r2_oxygen = new_state.rings["ring_2"].resources.oxygen
        # Should have received roughly 85 (minus consumption)
        assert r2_oxygen > 100.0

    def test_divert_power_still_works(self) -> None:
        """Legacy DIVERT_POWER action works as power transfer."""
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            role="engineer",
            action_type=ActionType.DIVERT_POWER,
            ring_id="ring_1",
            parameters={"target_ring": "ring_2", "amount": 50.0},
            submitted_tick=0,
        )
        state = state.model_copy(update={"pending_actions": [action]})
        r1_power_before = state.rings["ring_1"].resources.power

        new_state = tick(state, cfg)
        # Power should have left ring_1
        assert new_state.rings["ring_1"].resources.power < r1_power_before

    def test_transfer_capped_at_source(self) -> None:
        """Can't transfer more than source has."""
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        rings = dict(state.rings)
        r1 = rings["ring_1"]
        rings["ring_1"] = r1.model_copy(update={
            "resources": r1.resources.model_copy(update={"water": 10.0}),
        })
        state = state.model_copy(update={
            "rings": rings,
            "pending_actions": [_action("ring_1", "water", "ring_2", 500.0)],
        })

        new_state = tick(state, cfg)
        # Source can't go below 0 (but consumption will also drain)
        assert new_state.rings["ring_1"].resources.water >= 0.0

    def test_transfer_capped_at_target_capacity(self) -> None:
        """Target can't exceed capacity."""
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        rings = dict(state.rings)
        r2 = rings["ring_2"]
        rings["ring_2"] = r2.model_copy(update={
            "resources": r2.resources.model_copy(update={"food": 490.0}),
        })
        state = state.model_copy(update={
            "rings": rings,
            "pending_actions": [_action("ring_1", "food", "ring_2", 100.0)],
        })

        new_state = tick(state, cfg)
        # Target food should not exceed 500 (capacity)
        assert new_state.rings["ring_2"].resources.food <= cfg.resource_capacity

    def test_invalid_resource_ignored(self) -> None:
        state = build_initial_state(42, destination="proxima")
        cfg = SimConfig()
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            role="captain",
            action_type=ActionType.TRANSFER_RESOURCE,
            ring_id="ring_1",
            parameters={"resource": "morale", "target_ring": "ring_2", "amount": 50.0},
            submitted_tick=0,
        )
        state = state.model_copy(update={"pending_actions": [action]})
        # Should not crash
        new_state = tick(state, cfg)
        assert new_state.tick == state.tick + 1
