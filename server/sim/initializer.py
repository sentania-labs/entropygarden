"""
Build the initial GameState from a seed and config.

All randomness is seeded — same seed always produces the same starting state.
"""

from __future__ import annotations

import random
import uuid

from sim.prng import init_rng
from sim.population import _generate_name
from sim.state import (
    GameState,
    HiddenPressures,
    JourneyState,
    Milestone,
    Occupation,
    Person,
    ResourcePool,
    RingState,
    SimConfig,
    Trait,
)

RING_IDS = ["ring_1", "ring_2", "ring_3"]


DESTINATION_PRESETS: dict[str, dict[str, object]] = {
    "proxima": {
        "destination": "Proxima b",
        "total_distance_ly": 4.24,
        "fuel_capacity": 200.0,
        "milestones": [
            Milestone(milestone_id="oort_exit", name="Oort Cloud Exit", distance_ly=0.5,
                      description="The ship leaves the solar system's outermost boundary."),
            Milestone(milestone_id="halfway", name="Halfway Point", distance_ly=2.12,
                      description="Half the journey is behind us. The point of no return."),
            Milestone(milestone_id="decel", name="Deceleration Phase", distance_ly=3.4,
                      description="Begin braking. Fuel consumption increases."),
            Milestone(milestone_id="arrival_approach", name="Final Approach", distance_ly=4.0,
                      description="Proxima Centauri visible as a disk. Landfall imminent."),
        ],
    },
    "tau_ceti": {
        "destination": "Tau Ceti e",
        "total_distance_ly": 11.9,
        "fuel_capacity": 500.0,
        "milestones": [
            Milestone(milestone_id="oort_exit", name="Oort Cloud Exit", distance_ly=0.5,
                      description="The ship leaves the solar system's outermost boundary."),
            Milestone(milestone_id="quarter", name="First Quarter", distance_ly=2.975,
                      description="One quarter of the journey complete."),
            Milestone(milestone_id="halfway", name="Halfway Point", distance_ly=5.95,
                      description="The midpoint. Earth and destination equally distant."),
            Milestone(milestone_id="three_quarter", name="Third Quarter", distance_ly=8.925,
                      description="Three quarters done. The destination star brightens."),
            Milestone(milestone_id="decel", name="Deceleration Phase", distance_ly=9.5,
                      description="Begin braking. Fuel burn rate increases sharply."),
            Milestone(milestone_id="arrival_approach", name="Final Approach", distance_ly=11.5,
                      description="Tau Ceti system entry. Orbital insertion begins."),
        ],
    },
    "trappist": {
        "destination": "TRAPPIST-1e",
        "total_distance_ly": 39.6,
        "fuel_capacity": 1500.0,
        "milestones": [
            Milestone(milestone_id="oort_exit", name="Oort Cloud Exit", distance_ly=0.5,
                      description="The ship leaves the solar system's outermost boundary."),
            Milestone(milestone_id="tenth", name="10% Complete", distance_ly=3.96,
                      description="The first tenth. Earth fades to a point of light."),
            Milestone(milestone_id="quarter", name="First Quarter", distance_ly=9.9,
                      description="Generations have been born and died since departure."),
            Milestone(milestone_id="halfway", name="Halfway Point", distance_ly=19.8,
                      description="The midpoint. No living settler remembers Earth."),
            Milestone(milestone_id="three_quarter", name="Third Quarter", distance_ly=29.7,
                      description="The destination is closer than home. Hope rekindled."),
            Milestone(milestone_id="decel", name="Deceleration Phase", distance_ly=31.7,
                      description="Begin braking. The hardest phase begins."),
            Milestone(milestone_id="arrival_approach", name="Final Approach", distance_ly=38.5,
                      description="TRAPPIST-1 system entry. A new world awaits."),
        ],
    },
}


def build_initial_state(
    seed: int,
    config: SimConfig | None = None,
    destination: str = "proxima",
) -> GameState:
    """Generate a starting GameState for the given seed."""
    cfg = config or SimConfig()
    rings: dict[str, RingState] = {}

    for ring_id in RING_IDS:
        rings[ring_id] = _build_ring(ring_id, seed, cfg)

    journey = _build_journey(destination, cfg)

    return GameState(
        game_id=str(uuid.UUID(int=seed)),
        tick=0,
        seed=seed,
        rings=rings,
        journey=journey,
    )


def _build_journey(destination: str, cfg: SimConfig) -> JourneyState:
    preset = DESTINATION_PRESETS.get(destination, DESTINATION_PRESETS["proxima"])
    total = float(preset["total_distance_ly"])  # type: ignore[arg-type]
    fuel_capacity = float(preset["fuel_capacity"])  # type: ignore[arg-type]
    # Base speed: calibrated so the trip takes roughly the expected game-years
    # at perfect efficiency. Proxima ~42yr, Tau Ceti ~120yr, TRAPPIST ~400yr
    # 1 tick = 1 day = 1/365 year. Speed = distance / (years * 365)
    trip_years = {4.24: 42.0, 11.9: 120.0, 39.6: 400.0}.get(total, total * 10.0)
    base_speed = total / (trip_years * 365.0)
    return JourneyState(
        destination=str(preset["destination"]),
        total_distance_ly=total,
        distance_remaining_ly=total,
        base_speed=base_speed,
        fuel=fuel_capacity * cfg.initial_resource_fill,
        fuel_capacity=fuel_capacity,
        fuel_efficiency=1.0,
        milestones=list(preset["milestones"]),  # type: ignore[arg-type]
    )


def _build_ring(ring_id: str, seed: int, cfg: SimConfig) -> RingState:
    pop_rng = init_rng(seed, "population", ring_id)
    n = cfg.initial_pop_per_ring
    population = [_build_person(i, ring_id, pop_rng, cfg) for i in range(n)]

    capacity = cfg.resource_capacity
    fill = cfg.initial_resource_fill

    resources = ResourcePool(
        food=capacity * fill,
        water=capacity * fill,
        oxygen=capacity * fill,
        power=capacity * fill,
        morale=_mean_morale(population),
    )
    pressures = HiddenPressures(
        maintenance_debt=cfg.initial_maintenance_debt,
        ecological_drift=cfg.initial_ecological_drift,
        social_tension=cfg.initial_social_tension,
    )
    return RingState(ring_id=ring_id, population=population, resources=resources, pressures=pressures)


def _build_person(index: int, ring_id: str, rng: random.Random, cfg: SimConfig) -> Person:
    occupation = _pick_occupation(rng, cfg)
    traits = _pick_traits(rng, cfg)
    age = rng.uniform(18.0, 55.0)

    return Person(
        person_id=f"{ring_id}_p{index:04d}",
        name=_generate_name(rng),
        age=age,
        occupation=occupation,
        health=rng.uniform(0.75, 1.0),
        morale=rng.uniform(0.65, 0.95),
        influence=rng.uniform(0.0, 0.2),
        ring_id=ring_id,
        traits=traits,
        parent_ids=None,
    )


def _pick_occupation(rng: random.Random, cfg: SimConfig) -> Occupation:
    keys = list(cfg.occupation_weights.keys())
    weights = [cfg.occupation_weights[k] for k in keys]
    chosen = rng.choices(keys, weights=weights, k=1)[0]
    return Occupation(chosen)


def _pick_traits(rng: random.Random, cfg: SimConfig) -> list[Trait]:
    # Founding generation: 0–2 traits, each with ~30% base probability
    all_traits = list(Trait)
    n_traits = rng.choices([0, 1, 2], weights=[0.4, 0.4, 0.2], k=1)[0]
    if n_traits == 0:
        return []
    return rng.sample(all_traits, min(n_traits, len(all_traits)))


def _mean_morale(population: list[Person]) -> float:
    if not population:
        return 0.5
    return sum(p.morale for p in population) / len(population)
