"""
Per-person update logic: aging, morale, reproduction, trait mechanics.

All functions are pure — they return new Person instances, never mutate.
"""

from __future__ import annotations

import random

from sim.state import Occupation, Person, SimConfig, Trait

# Priority order for dropping traits when over cap (drop last = lowest priority)
_TRAIT_PRIORITY: list[Trait] = [
    Trait.INFLUENTIAL,
    Trait.SKILLED,
    Trait.RESILIENT,
    Trait.ANXIOUS,
    Trait.REBELLIOUS,
    Trait.LAZY,
]


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Aging + health
# ---------------------------------------------------------------------------


def age_person(person: Person, cfg: SimConfig) -> Person:
    """Advance age by one tick and apply baseline health decay."""
    new_age = person.age + 1.0 / 365.0

    decay = cfg.health_decay_per_tick
    if Trait.RESILIENT in person.traits:
        decay *= cfg.trait_resilient_health_mult

    new_health = _clamp(person.health - decay)
    return person.model_copy(update={"age": new_age, "health": new_health})


def apply_starvation(person: Person, resource_fill: float, cfg: SimConfig) -> Person:
    """Apply health damage when resources fall critically low."""
    if resource_fill >= cfg.starvation_threshold:
        return person
    severity = 1.0 - (resource_fill / cfg.starvation_threshold)
    damage = cfg.starvation_health_penalty * severity
    if Trait.RESILIENT in person.traits:
        damage *= cfg.trait_resilient_health_mult
    return person.model_copy(update={"health": _clamp(person.health - damage)})


def apply_medic_heal(person: Person, medic_count: int, pop_size: int, cfg: SimConfig) -> Person:
    """Distribute medic healing across the ring population."""
    if medic_count == 0 or pop_size == 0:
        return person
    heal = (medic_count * cfg.medic_heal_per_tick) / pop_size
    return person.model_copy(update={"health": _clamp(person.health + heal)})


# ---------------------------------------------------------------------------
# Morale
# ---------------------------------------------------------------------------


def update_morale(
    person: Person,
    resource_fill: float,   # 0–1, mean resource fill level for the ring
    social_tension: float,  # 0–1
    cfg: SimConfig,
) -> Person:
    """
    Update a person's morale based on resource availability and social tension.

    resource_fill = 1.0 means fully stocked; 0.0 means empty.
    """
    resource_deficit = max(0.0, 1.0 - resource_fill)
    base_loss = (
        resource_deficit * cfg.morale_resource_sensitivity
        + social_tension * cfg.morale_tension_sensitivity
    )

    # Trait modifiers
    if Trait.ANXIOUS in person.traits:
        base_loss *= cfg.trait_anxious_morale_mult
    if Trait.RESILIENT in person.traits:
        base_loss *= cfg.trait_resilient_morale_mult

    new_morale = _clamp(person.morale - base_loss)
    return person.model_copy(update={"morale": new_morale})


# ---------------------------------------------------------------------------
# Reproduction
# ---------------------------------------------------------------------------


def reproduce(
    parent_a: Person,
    parent_b: Person,
    rng: random.Random,
    cfg: SimConfig,
    *,
    child_id: str,
    ring_id: str,
) -> Person:
    """
    Create a child from two parents using probabilistic trait inheritance.

    Inheritance probabilities:
    - Both parents have trait → cfg.inherit_both_parents (~70%)
    - One parent has trait   → cfg.inherit_one_parent    (~35%)
    - Neither parent has it  → cfg.inherit_spontaneous   (~5%)
    """
    traits_a = set(parent_a.traits)
    traits_b = set(parent_b.traits)
    child_traits: list[Trait] = []

    for trait in Trait:
        in_a = trait in traits_a
        in_b = trait in traits_b

        if in_a and in_b:
            prob = cfg.inherit_both_parents
        elif in_a or in_b:
            prob = cfg.inherit_one_parent
        else:
            prob = cfg.inherit_spontaneous

        if rng.random() < prob:
            child_traits.append(trait)

    # Cap at max_traits by dropping lowest-priority traits
    if len(child_traits) > cfg.max_traits:
        # Sort by priority (higher index = lower priority = drop first)
        child_traits.sort(key=lambda t: _TRAIT_PRIORITY.index(t) if t in _TRAIT_PRIORITY else 99)
        child_traits = child_traits[: cfg.max_traits]

    # Pick occupation based on parent occupations (simple: random from parents)
    occupation = rng.choice([parent_a.occupation, parent_b.occupation])

    return Person(
        person_id=child_id,
        name=_generate_name(rng),
        age=0.0,
        occupation=occupation,
        health=1.0,
        morale=0.9,
        influence=0.0,
        ring_id=ring_id,
        traits=child_traits,
        parent_ids=(parent_a.person_id, parent_b.person_id),
    )


def _generate_name(rng: random.Random) -> str:
    """Generate a name from syllable combinations — no external data needed."""
    prefixes = ["Aer", "Bel", "Cor", "Del", "Fen", "Gal", "Hel", "Iras", "Jor", "Kel",
                "Lyn", "Mar", "Nor", "Obr", "Pav", "Quen", "Ros", "Sel", "Tor", "Ura",
                "Vel", "Wren", "Xan", "Yar", "Zel"]
    suffixes = ["a", "an", "ara", "en", "eon", "era", "ia", "iel", "in", "ion",
                "is", "na", "on", "ora", "os", "ra", "ren", "ris", "on", "us"]
    return rng.choice(prefixes) + rng.choice(suffixes)


# ---------------------------------------------------------------------------
# Acquired traits
# ---------------------------------------------------------------------------


def apply_trait_event(person: Person, trait: Trait, add: bool) -> Person:
    """
    Add or remove a trait from a person. Called by the event system.

    - Adding a trait that's already present is a no-op.
    - Removing a trait that's absent is a no-op.
    - Adding respects the max_traits cap by dropping the lowest-priority trait.
    """
    cfg = SimConfig()  # use defaults for cap — events can pass custom cfg if needed
    traits = list(person.traits)

    if add:
        if trait not in traits:
            traits.append(trait)
            if len(traits) > cfg.max_traits:
                # Drop the lowest-priority trait (last in priority list)
                traits.sort(
                    key=lambda t: _TRAIT_PRIORITY.index(t) if t in _TRAIT_PRIORITY else 99
                )
                traits = traits[: cfg.max_traits]
    else:
        traits = [t for t in traits if t != trait]

    return person.model_copy(update={"traits": traits})


# ---------------------------------------------------------------------------
# Mortality
# ---------------------------------------------------------------------------


def is_dead(person: Person, rng: random.Random, cfg: SimConfig) -> bool:
    """Return True if this person dies this tick."""
    # Very low health — high mortality risk
    if person.health <= cfg.mortality_health_threshold:
        return rng.random() < 0.05

    # Old age
    if person.age >= cfg.mortality_age_threshold:
        excess = person.age - cfg.mortality_age_threshold
        age_risk = cfg.base_mortality_rate * (1.0 + excess * 0.1)
        return rng.random() < age_risk

    return rng.random() < cfg.base_mortality_rate
