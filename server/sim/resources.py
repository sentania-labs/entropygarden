"""
Resource consumption and production for a single ring per tick.

All functions are pure: (population, config) -> delta dict.
The tick engine applies deltas to the ResourcePool.
"""

from __future__ import annotations

from sim.state import Occupation, Person, SimConfig, Trait


def _productivity_mult(person: Person, cfg: SimConfig) -> float:
    """Combined productivity multiplier from a person's traits."""
    mult = 1.0
    if Trait.SKILLED in person.traits:
        mult *= cfg.trait_skilled_output_mult
    if Trait.LAZY in person.traits:
        mult *= cfg.trait_lazy_output_mult
    return mult


def consumption_for_ring(population: list[Person], cfg: SimConfig) -> dict[str, float]:
    """
    Return total resource consumption for a ring this tick.

    Power has a fixed ring-system overhead on top of per-person cost.
    """
    n = len(population)
    return {
        "food": cfg.food_per_person * n,
        "water": cfg.water_per_person * n,
        "oxygen": cfg.oxygen_per_person * n,
        "power": cfg.power_per_ring + (cfg.food_per_person * 0.2 * n),  # small per-person power draw
    }


def production_for_ring(population: list[Person], cfg: SimConfig) -> dict[str, float]:
    """
    Return total resource production for a ring this tick.

    Output is scaled by each worker's productivity multiplier.
    """
    food = 0.0
    oxygen = 0.0
    water = 0.0
    power = 0.0

    for person in population:
        mult = _productivity_mult(person, cfg)
        match person.occupation:
            case Occupation.FARMER:
                food += cfg.food_per_farmer * mult
            case Occupation.LIFE_SUPPORT:
                oxygen += cfg.oxygen_per_life_support * mult
                water += cfg.water_per_life_support * mult
            case Occupation.LABORER:
                power += cfg.power_per_laborer * mult
            case _:
                pass  # ENGINEER, MEDIC, ADMINISTRATOR produce no direct resources

    return {"food": food, "water": water, "oxygen": oxygen, "power": power}
