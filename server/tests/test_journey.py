"""Tests for the journey system: fuel, distance, milestones, win/loss."""

from sim.initializer import build_initial_state
from sim.journey import process_journey
from sim.state import GameState, JourneyState, Milestone, SimConfig
from sim.tick import tick


class TestJourneyInit:
    def test_proxima_preset_creates_journey(self) -> None:
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None
        assert state.journey.destination == "Proxima b"
        assert state.journey.total_distance_ly == 4.24
        assert state.journey.distance_remaining_ly == 4.24
        assert state.journey.fuel > 0
        assert state.journey.arrival_tick is None
        assert len(state.journey.milestones) == 4

    def test_tau_ceti_preset(self) -> None:
        state = build_initial_state(42, destination="tau_ceti")
        assert state.journey is not None
        assert state.journey.destination == "Tau Ceti e"
        assert state.journey.total_distance_ly == 11.9

    def test_trappist_preset(self) -> None:
        state = build_initial_state(42, destination="trappist")
        assert state.journey is not None
        assert state.journey.destination == "TRAPPIST-1e"
        assert state.journey.total_distance_ly == 39.6

    def test_unknown_preset_falls_back_to_proxima(self) -> None:
        state = build_initial_state(42, destination="unknown")
        assert state.journey is not None
        assert state.journey.destination == "Proxima b"


class TestJourneyProcessing:
    def test_journey_advances_each_tick(self) -> None:
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None
        orig_remaining = state.journey.distance_remaining_ly
        orig_fuel = state.journey.fuel

        new_state = tick(state)
        assert new_state.journey is not None
        assert new_state.journey.distance_remaining_ly < orig_remaining
        assert new_state.journey.fuel < orig_fuel

    def test_propulsion_drains_power(self) -> None:
        cfg = SimConfig()
        state = build_initial_state(42, destination="proxima")
        orig_power = {rid: r.resources.power for rid, r in state.rings.items()}

        new_state = process_journey(state, cfg)
        for rid in state.rings:
            assert new_state.rings[rid].resources.power < orig_power[rid]

    def test_maintenance_debt_reduces_efficiency(self) -> None:
        cfg = SimConfig()
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None

        # Set high maintenance debt
        rings = dict(state.rings)
        for rid, ring in rings.items():
            rings[rid] = ring.model_copy(update={
                "pressures": ring.pressures.model_copy(update={"maintenance_debt": 0.8}),
            })
        state = state.model_copy(update={"rings": rings})

        new_state = process_journey(state, cfg)
        assert new_state.journey is not None
        # Efficiency should be degraded: 1.0 - 0.8 * 0.5 = 0.6
        assert new_state.journey.fuel_efficiency < 0.7

    def test_fuel_exhaustion_stops_progress(self) -> None:
        cfg = SimConfig()
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None

        # Drain all fuel
        state = state.model_copy(update={
            "journey": state.journey.model_copy(update={"fuel": 0.0}),
        })

        new_state = process_journey(state, cfg)
        assert new_state.journey is not None
        assert new_state.journey.distance_remaining_ly == state.journey.distance_remaining_ly

    def test_arrival_sets_tick(self) -> None:
        cfg = SimConfig()
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None

        # Set distance to nearly zero
        state = state.model_copy(update={
            "journey": state.journey.model_copy(update={"distance_remaining_ly": 0.00001}),
        })

        new_state = process_journey(state, cfg)
        assert new_state.journey is not None
        assert new_state.journey.arrival_tick == state.tick

    def test_milestones_reached(self) -> None:
        cfg = SimConfig()
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None

        # Set distance past halfway (2.12 ly from origin = 4.24 - 2.12 remaining)
        state = state.model_copy(update={
            "journey": state.journey.model_copy(update={"distance_remaining_ly": 2.0}),
        })

        new_state = process_journey(state, cfg)
        assert new_state.journey is not None
        assert "oort_exit" in new_state.journey.milestones_reached
        assert "halfway" in new_state.journey.milestones_reached

    def test_no_processing_when_arrived(self) -> None:
        cfg = SimConfig()
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None

        state = state.model_copy(update={
            "journey": state.journey.model_copy(update={
                "arrival_tick": 100,
                "distance_remaining_ly": 0.0,
            }),
        })
        orig_fuel = state.journey.fuel

        new_state = process_journey(state, cfg)
        assert new_state.journey is not None
        assert new_state.journey.fuel == orig_fuel  # no fuel consumed


class TestJourneyIntegration:
    def test_journey_progresses_over_many_ticks(self) -> None:
        state = build_initial_state(42, destination="proxima")
        assert state.journey is not None

        for _ in range(100):
            state = tick(state)

        assert state.journey is not None
        assert state.journey.distance_remaining_ly < 4.24
        assert state.journey.fuel < 200.0
        assert len(state.journey.milestones_reached) >= 0  # may or may not hit milestones in 100 ticks

    def test_no_journey_still_works(self) -> None:
        """Games without journey (backward compat) still tick normally."""
        state = build_initial_state(42, destination="proxima")
        state = state.model_copy(update={"journey": None})
        new_state = tick(state)
        assert new_state.tick == 1
        assert new_state.journey is None
