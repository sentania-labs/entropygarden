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
    Occupation,
    Person,
    ResourcePool,
    RingState,
    SimConfig,
    Trait,
)

RING_IDS = ["ring_1", "ring_2", "ring_3"]


def build_initial_state(seed: int, config: SimConfig | None = None) -> GameState:
    """Generate a starting GameState for the given seed."""
    cfg = config or SimConfig()
    rings: dict[str, RingState] = {}

    for ring_id in RING_IDS:
        rings[ring_id] = _build_ring(ring_id, seed, cfg)

    return GameState(
        game_id=str(uuid.UUID(int=seed)),
        tick=0,
        seed=seed,
        rings=rings,
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
