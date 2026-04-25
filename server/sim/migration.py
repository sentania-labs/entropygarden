"""
Autonomous inter-ring migration and cross-ring labor assignment.

Settlers evaluate their conditions and decide to move or work elsewhere.
This is sim-driven, not player-controlled. Players can only restrict movement.

Pure function — no I/O, no mutation.
"""

from __future__ import annotations

import random

from sim.state import GameState, Occupation, Person, RingState, SimConfig


# Productive occupations that labor drafts can hold
_PRODUCTIVE_OCCUPATIONS = frozenset({
    Occupation.FARMER,
    Occupation.ENGINEER,
    Occupation.LIFE_SUPPORT,
    Occupation.LABORER,
})


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _resource_fill(ring: RingState, cfg: SimConfig) -> float:
    """Mean fill level (0-1) across food, water, oxygen, power."""
    cap = cfg.resource_capacity
    r = ring.resources
    fills = [r.food / cap, r.water / cap, r.oxygen / cap, r.power / cap]
    return sum(fills) / len(fills)


def _migration_pressure(person: Person, ring: RingState, cfg: SimConfig, rng: random.Random) -> float:
    """Compute how much a settler wants to leave their current ring."""
    fill = _resource_fill(ring, cfg)
    tension = ring.pressures.social_tension

    pressure = 0.0
    pressure += max(0.0, 0.5 - fill) * 2.0           # scarcity pushes out
    pressure += max(0.0, tension - 0.3) * 1.5         # tension pushes out
    pressure += max(0.0, 0.5 - person.morale) * 1.0   # personal unhappiness
    pressure += rng.uniform(0.0, 0.1)                  # boredom / wanderlust
    pressure -= fill * 0.5                             # abundance retains
    return pressure


def _ring_attractiveness(ring: RingState, cfg: SimConfig) -> float:
    """How attractive a ring is as a migration destination."""
    fill = _resource_fill(ring, cfg)
    tension = ring.pressures.social_tension
    return fill * 1.0 + (1.0 - tension) * 0.5


def process_migration(state: GameState, cfg: SimConfig, rng: random.Random) -> GameState:
    """Evaluate migration and cross-ring labor for a fraction of the population.

    Called once per tick, after morale updates but before mortality.
    """
    # Build ring lookup and attractiveness
    ring_attract = {rid: _ring_attractiveness(ring, cfg) for rid, ring in state.rings.items()}

    # Collect all people with their rings
    all_people: list[tuple[str, Person]] = []
    for ring_id, ring in state.rings.items():
        for person in ring.population:
            all_people.append((ring_id, person))

    if not all_people:
        return state

    # Evaluate a fraction of the population
    n_eval = max(1, int(len(all_people) * cfg.migration_eval_fraction))
    sample = rng.sample(all_people, min(n_eval, len(all_people)))

    # Track moves: person_id -> new_ring_id
    moves: dict[str, str] = {}
    # Track cross-ring labor: person_id -> work_ring_id
    labor_changes: dict[str, str | None] = {}

    for ring_id, person in sample:
        if person.migration_cooldown > 0:
            continue

        ring = state.rings[ring_id]
        pressure = _migration_pressure(person, ring, cfg, rng)
        home_attract = ring_attract[ring_id]

        # Find best alternative ring
        best_ring: str | None = None
        best_attract = home_attract
        for other_id, other_attract in ring_attract.items():
            if other_id == ring_id:
                continue
            if other_attract > best_attract:
                best_attract = other_attract
                best_ring = other_id

        if best_ring is None:
            continue

        # Check full migration
        if pressure >= cfg.migration_pressure_threshold:
            if _can_migrate(person, ring_id, best_ring, state, cfg):
                moves[person.person_id] = best_ring
                continue

        # Check cross-ring labor (lower threshold)
        if pressure >= cfg.cross_ring_work_threshold:
            if person.work_ring_id != best_ring and _can_work_cross_ring(person, ring_id, best_ring, state, cfg):
                labor_changes[person.person_id] = best_ring

    # Apply moves and labor changes
    if not moves and not labor_changes:
        # Still need to decrement cooldowns
        return _decrement_cooldowns(state)

    new_rings: dict[str, RingState] = {}
    for ring_id, ring in state.rings.items():
        new_pop: list[Person] = []
        for p in ring.population:
            if p.person_id in moves:
                # This person is leaving — they'll be added to the target ring
                continue
            updated = p
            if p.person_id in labor_changes:
                updated = p.model_copy(update={"work_ring_id": labor_changes[p.person_id]})
            if updated.migration_cooldown > 0:
                updated = updated.model_copy(update={"migration_cooldown": updated.migration_cooldown - 1})
            new_pop.append(updated)
        new_rings[ring_id] = ring.model_copy(update={"population": new_pop})

    # Add migrants to their new rings
    for ring_id, ring in state.rings.items():
        for p in ring.population:
            if p.person_id in moves and moves[p.person_id] != ring_id:
                target_id = moves[p.person_id]
                migrant = p.model_copy(update={
                    "ring_id": target_id,
                    "work_ring_id": None,  # reset cross-ring labor on move
                    "migration_cooldown": cfg.migration_cooldown_ticks,
                })
                new_rings[target_id] = new_rings[target_id].model_copy(update={
                    "population": new_rings[target_id].population + [migrant],
                })

    return state.model_copy(update={"rings": new_rings})


def _can_migrate(person: Person, source: str, target: str, state: GameState, cfg: SimConfig) -> bool:
    """Check if migration is allowed given restrictions."""
    src_ring = state.rings[source]
    tgt_ring = state.rings[target]

    # Source lockdown blocks all outgoing movement
    if src_ring.restrictions.lockdown:
        return False

    # Source labor draft blocks productive workers from leaving
    if src_ring.restrictions.labor_draft and person.occupation in _PRODUCTIVE_OCCUPATIONS:
        return False

    # Target civil restriction blocks incoming movement
    if tgt_ring.restrictions.civil_restriction:
        return False

    return True


def _can_work_cross_ring(person: Person, source: str, target: str, state: GameState, cfg: SimConfig) -> bool:
    """Check if cross-ring labor is allowed."""
    src_ring = state.rings[source]
    tgt_ring = state.rings[target]

    # Lockdown prevents all cross-ring activity
    if src_ring.restrictions.lockdown:
        return False

    # Civil restriction in target prevents incoming workers too
    if tgt_ring.restrictions.civil_restriction:
        return False

    return True


def _decrement_cooldowns(state: GameState) -> GameState:
    """Decrement migration cooldowns for all people."""
    new_rings: dict[str, RingState] = {}
    changed = False
    for ring_id, ring in state.rings.items():
        new_pop: list[Person] = []
        for p in ring.population:
            if p.migration_cooldown > 0:
                new_pop.append(p.model_copy(update={"migration_cooldown": p.migration_cooldown - 1}))
                changed = True
            else:
                new_pop.append(p)
        new_rings[ring_id] = ring.model_copy(update={"population": new_pop})
    return state.model_copy(update={"rings": new_rings}) if changed else state


def apply_restriction_morale(state: GameState, cfg: SimConfig) -> GameState:
    """Apply morale penalties from active restrictions. Called during tick."""
    new_rings: dict[str, RingState] = {}
    changed = False
    for ring_id, ring in state.rings.items():
        penalty = 0.0
        if ring.restrictions.lockdown:
            penalty += cfg.lockdown_morale_penalty
        if ring.restrictions.civil_restriction:
            penalty += cfg.civil_restriction_morale_penalty
        if ring.restrictions.labor_draft:
            penalty += cfg.labor_draft_morale_penalty

        if penalty == 0.0:
            new_rings[ring_id] = ring
            continue

        changed = True
        new_pop = [
            p.model_copy(update={"morale": _clamp01(p.morale - penalty)})
            for p in ring.population
        ]
        new_rings[ring_id] = ring.model_copy(update={"population": new_pop})

    return state.model_copy(update={"rings": new_rings}) if changed else state
