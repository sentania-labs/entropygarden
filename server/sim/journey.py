"""
Journey processing: fuel consumption, distance tracking, milestones, win/loss.

Pure function — no I/O, no mutation.
"""

from __future__ import annotations

from sim.state import GameState, JourneyState, SimConfig


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def process_journey(state: GameState, cfg: SimConfig) -> GameState:
    """Advance the journey by one tick. Returns updated GameState."""
    journey = state.journey
    if journey is None or journey.arrival_tick is not None:
        return state  # no journey or already arrived

    if journey.fuel <= 0:
        return state  # stranded — no fuel, no progress

    # Fuel efficiency degrades with mean maintenance debt across rings
    ring_debts = [r.pressures.maintenance_debt for r in state.rings.values()]
    mean_debt = sum(ring_debts) / len(ring_debts) if ring_debts else 0.0
    fuel_efficiency = _clamp(1.0 - mean_debt * 0.5, 0.3, 1.0)

    # Fuel consumption: worse efficiency = more fuel burned
    fuel_cost = cfg.base_fuel_per_tick / fuel_efficiency
    new_fuel = max(0.0, journey.fuel - fuel_cost)

    # Distance covered this tick
    distance_covered = journey.base_speed * fuel_efficiency
    new_remaining = max(0.0, journey.distance_remaining_ly - distance_covered)

    # Check milestones
    distance_traveled = journey.total_distance_ly - new_remaining
    new_reached = list(journey.milestones_reached)
    for ms in journey.milestones:
        if ms.milestone_id not in new_reached and distance_traveled >= ms.distance_ly:
            new_reached.append(ms.milestone_id)

    # Check arrival
    arrival_tick = journey.arrival_tick
    if new_remaining <= 0:
        arrival_tick = state.tick

    # Propulsion power drain from each ring
    rings = dict(state.rings)
    for ring_id, ring in rings.items():
        r = ring.resources
        new_power = max(0.0, r.power - cfg.propulsion_power_drain)
        rings[ring_id] = ring.model_copy(update={
            "resources": r.model_copy(update={"power": new_power}),
        })

    new_journey = journey.model_copy(update={
        "fuel": new_fuel,
        "fuel_efficiency": fuel_efficiency,
        "distance_remaining_ly": new_remaining,
        "milestones_reached": new_reached,
        "arrival_tick": arrival_tick,
    })

    return state.model_copy(update={
        "journey": new_journey,
        "rings": rings,
    })
