"""
Core tick engine.

tick(state, config) -> GameState

Pure function — no I/O, no mutation, no LLM calls.
Tick sequence:
  1. Population aging + health decay
  2. Medic healing
  3. Resource consumption
  4. Resource production
  5. Apply net resource delta (clamped to [0, capacity])
  6. Morale update (per person, based on ring resource fill)
  7. Pressure accumulation
  8. Ring aggregate morale update
  9. Mortality
  10. Reproduction (if enabled by config)
  11. Increment tick counter
  12. Event evaluation (ship-level, fires against updated state)
"""

from __future__ import annotations

from collections.abc import Iterable

from sim.events import EventDef, evaluate_events
from sim.journey import process_journey
from sim.migration import apply_restriction_morale, process_migration
from sim.population import age_person, apply_medic_heal, apply_starvation, is_dead, reproduce, update_morale
from sim.pressures import accumulate_pressures
from sim.prng import tick_rng
from sim.resources import consumption_for_ring, production_for_ring
from sim.state import (
    ActionType,
    ActiveModifier,
    GameState,
    Occupation,
    Person,
    ResourcePool,
    RingRestrictions,
    RingState,
    SimConfig,
)


def tick(
    state: GameState,
    cfg: SimConfig | None = None,
    event_defs: list[EventDef] | None = None,
) -> GameState:
    """Advance the simulation by one tick. Returns a new GameState."""
    if cfg is None:
        cfg = SimConfig()

    # 0. Apply pending actions (one-shot effects + create modifiers), expire old modifiers
    state = _apply_pending_actions(state, cfg)

    # Build cross-ring worker lookup: ring_id -> list of workers from other rings
    cross_ring_workers: dict[str, list[Person]] = {rid: [] for rid in state.rings}
    for ring_id, ring in state.rings.items():
        for p in ring.population:
            if p.work_ring_id and p.work_ring_id != ring_id and p.work_ring_id in cross_ring_workers:
                cross_ring_workers[p.work_ring_id].append(p)

    new_rings: dict[str, RingState] = {}
    new_person_counter = state.tick  # use tick as part of unique ID for new births

    for ring_id, ring in state.rings.items():
        ring_mods = [m for m in state.active_modifiers if m.ring_id == ring_id]
        ring, new_person_counter = _tick_ring(
            ring, state.seed, state.tick, cfg, new_person_counter, ring_mods,
            cross_ring_workers=cross_ring_workers.get(ring_id, []),
        )
        new_rings[ring_id] = ring

    mid_state = state.model_copy(update={"rings": new_rings, "tick": state.tick + 1})

    # 11a. Migration (autonomous settler movement between rings)
    migration_rng = tick_rng(state.seed, state.tick, "migration", "ship")
    mid_state = process_migration(mid_state, cfg, migration_rng)

    # 11a2. Restriction morale penalties
    mid_state = apply_restriction_morale(mid_state, cfg)

    # 11b. Journey processing (fuel, distance, milestones, propulsion power drain)
    mid_state = process_journey(mid_state, cfg)

    # 12. Event evaluation (ship-level, after all rings are updated)
    if event_defs:
        mid_state, _ = evaluate_events(mid_state, event_defs, cfg)

    return mid_state


def _apply_pending_actions(state: GameState, cfg: SimConfig) -> GameState:
    """Apply pending actions: one-shot effects immediately, multi-tick effects as ActiveModifiers."""
    if not state.pending_actions:
        # Still expire old modifiers
        kept = [m for m in state.active_modifiers if m.expires_tick > state.tick]
        if len(kept) == len(state.active_modifiers):
            return state
        return state.model_copy(update={"active_modifiers": kept})

    rings = dict(state.rings)
    new_modifiers: list[ActiveModifier] = []

    for action in state.pending_actions:
        ring = rings.get(action.ring_id)
        if ring is None:
            continue

        if action.action_type == ActionType.EMERGENCY_REPAIR:
            p = ring.pressures
            r = ring.resources
            rings[action.ring_id] = ring.model_copy(update={
                "pressures": p.model_copy(update={
                    "maintenance_debt": max(0.0, p.maintenance_debt - 0.05),
                }),
                "resources": r.model_copy(update={
                    "power": max(0.0, r.power - 5.0),
                }),
            })

        elif action.action_type in (ActionType.DIVERT_POWER, ActionType.TRANSFER_RESOURCE):
            # Unified resource transfer with waste factor
            resource = str(action.parameters.get("resource", "power"))
            if action.action_type == ActionType.DIVERT_POWER:
                resource = "power"  # legacy alias always transfers power
            target_id = str(action.parameters.get("target_ring", ""))
            amount = float(action.parameters.get("amount", 10.0))
            target = rings.get(target_id)
            if target is None or resource not in ("food", "water", "oxygen", "power"):
                continue
            r_src = ring.resources
            src_val = getattr(r_src, resource)
            actual = min(amount, src_val)
            waste = cfg.transfer_waste.get(resource, 0.0)
            delivered = actual * (1.0 - waste)
            # Update source
            rings[action.ring_id] = ring.model_copy(update={
                "resources": r_src.model_copy(update={resource: src_val - actual}),
            })
            # Update target
            ring = rings[action.ring_id]  # refresh ref
            r_tgt = target.resources
            tgt_val = getattr(r_tgt, resource)
            rings[target_id] = target.model_copy(update={
                "resources": r_tgt.model_copy(update={
                    resource: min(cfg.resource_capacity, tgt_val + delivered),
                }),
            })

        elif action.action_type == ActionType.PRIORITIZE_MAINTENANCE:
            new_modifiers.append(ActiveModifier(
                modifier_id=action.action_id,
                action_type=ActionType.PRIORITIZE_MAINTENANCE,
                ring_id=action.ring_id,
                parameters={},
                expires_tick=state.tick + 50,
            ))

        elif action.action_type == ActionType.RATION_RESOURCE:
            new_modifiers.append(ActiveModifier(
                modifier_id=action.action_id,
                action_type=ActionType.RATION_RESOURCE,
                ring_id=action.ring_id,
                parameters=action.parameters,
                expires_tick=state.tick + 30,
            ))

        elif action.action_type == ActionType.BOOST_PRODUCTION:
            new_modifiers.append(ActiveModifier(
                modifier_id=action.action_id,
                action_type=ActionType.BOOST_PRODUCTION,
                ring_id=action.ring_id,
                parameters=action.parameters,
                expires_tick=state.tick + 30,
            ))

        elif action.action_type == ActionType.IMPOSE_LOCKDOWN:
            restr = ring.restrictions
            rings[action.ring_id] = ring.model_copy(update={
                "restrictions": restr.model_copy(update={"lockdown": True}),
            })

        elif action.action_type == ActionType.IMPOSE_CIVIL_RESTRICTION:
            restr = ring.restrictions
            rings[action.ring_id] = ring.model_copy(update={
                "restrictions": restr.model_copy(update={"civil_restriction": True}),
            })

        elif action.action_type == ActionType.IMPOSE_LABOR_DRAFT:
            restr = ring.restrictions
            rings[action.ring_id] = ring.model_copy(update={
                "restrictions": restr.model_copy(update={"labor_draft": True}),
            })

        elif action.action_type == ActionType.LIFT_RESTRICTION:
            rings[action.ring_id] = ring.model_copy(update={
                "restrictions": RingRestrictions(),  # clear all
            })

    kept_mods = [m for m in state.active_modifiers if m.expires_tick > state.tick]
    return state.model_copy(update={
        "rings": rings,
        "pending_actions": [],
        "active_modifiers": kept_mods + new_modifiers,
    })


def _tick_ring(
    ring: RingState,
    seed: int,
    tick_num: int,
    cfg: SimConfig,
    person_counter: int,
    modifiers: list[ActiveModifier] | None = None,
    cross_ring_workers: list[Person] | None = None,
) -> tuple[RingState, int]:
    population = list(ring.population)
    ring_id = ring.ring_id
    if modifiers is None:
        modifiers = []

    # 1. Age + health decay
    population = [age_person(p, cfg) for p in population]

    # 2. Medic healing
    medic_count = sum(1 for p in population if p.occupation == Occupation.MEDIC)
    pop_size = len(population)
    population = [apply_medic_heal(p, medic_count, pop_size, cfg) for p in population]

    # 3 & 4. Resource consumption and production (modifiers applied as multipliers)
    consumption_mult = 1.0
    production_mult = 1.0
    for mod in modifiers:
        if mod.action_type == ActionType.RATION_RESOURCE:
            consumption_mult *= 0.8
        elif mod.action_type == ActionType.BOOST_PRODUCTION:
            production_mult *= 1.2

    # Residents consume; local workers + cross-ring commuters produce
    # Local workers = residents who work here (work_ring_id is None or matches this ring)
    local_workers = [p for p in population if p.work_ring_id is None or p.work_ring_id == ring_id]
    consumed = consumption_for_ring(population, cfg)
    produced = production_for_ring(local_workers, cfg, cross_ring_workers=cross_ring_workers)

    if consumption_mult != 1.0:
        consumed = {k: v * consumption_mult for k, v in consumed.items()}
    if production_mult != 1.0:
        produced = {k: v * production_mult for k, v in produced.items()}

    # 5. Apply net resource delta, clamped to [0, capacity]
    def net(resource: str, current: float) -> float:
        delta = produced.get(resource, 0.0) - consumed.get(resource, 0.0)
        return max(0.0, min(cfg.resource_capacity, current + delta))

    r = ring.resources
    new_resources = ResourcePool(
        food=net("food", r.food),
        water=net("water", r.water),
        oxygen=net("oxygen", r.oxygen),
        power=net("power", r.power),
        morale=r.morale,  # updated in step 8
    )

    # 6. Morale update + starvation health damage per person
    resource_fill = _mean_resource_fill(new_resources, cfg)
    food_fill = new_resources.food / cfg.resource_capacity
    oxygen_fill = new_resources.oxygen / cfg.resource_capacity
    # Starvation driven by whichever critical resource is most depleted
    critical_fill = min(food_fill, oxygen_fill)
    population = [
        update_morale(
            apply_starvation(p, critical_fill, cfg),
            resource_fill=resource_fill,
            social_tension=ring.pressures.social_tension,
            cfg=cfg,
        )
        for p in population
    ]

    # 7. Pressure accumulation (PRIORITIZE_MAINTENANCE applies extra debt reduction)
    new_pressures = accumulate_pressures(ring.pressures, population, cfg)
    if any(m.action_type == ActionType.PRIORITIZE_MAINTENANCE for m in modifiers):
        # Extra engineer focus: remove ~70% of base debt accumulation rate per tick
        extra_reduction = cfg.maintenance_debt_rate * 0.7
        new_pressures = new_pressures.model_copy(update={
            "maintenance_debt": max(0.0, new_pressures.maintenance_debt - extra_reduction),
        })

    # 8. Ring aggregate morale
    ring_morale = _mean(p.morale for p in population) if population else 0.5
    new_resources = new_resources.model_copy(update={"morale": ring_morale})

    # 9. Mortality
    mort_rng = tick_rng(seed, tick_num, "mortality", ring_id)
    survivors = [p for p in population if not is_dead(p, mort_rng, cfg)]

    # 10. Reproduction
    birth_rng = tick_rng(seed, tick_num, "population", ring_id)
    new_births: list[Person] = []
    eligible = [
        p for p in survivors
        if cfg.reproduction_age_min <= p.age <= cfg.reproduction_age_max
    ]
    if len(eligible) >= 2:
        birth_rng.shuffle(eligible)
        pairs = list(zip(eligible[::2], eligible[1::2]))
        for parent_a, parent_b in pairs:
            if birth_rng.random() < cfg.base_birth_rate:
                person_counter += 1
                child = reproduce(
                    parent_a, parent_b, birth_rng, cfg,
                    child_id=f"{ring_id}_b{person_counter:06d}",
                    ring_id=ring_id,
                )
                new_births.append(child)

    final_population = survivors + new_births

    new_ring = RingState(
        ring_id=ring_id,
        population=final_population,
        resources=new_resources,
        pressures=new_pressures,
        restrictions=ring.restrictions,
    )
    return new_ring, person_counter


def _mean_resource_fill(resources: ResourcePool, cfg: SimConfig) -> float:
    """Mean fill level (0–1) across food, water, oxygen, power."""
    cap = cfg.resource_capacity
    fills = [
        resources.food / cap,
        resources.water / cap,
        resources.oxygen / cap,
        resources.power / cap,
    ]
    return sum(fills) / len(fills)


def _mean(values: Iterable[float]) -> float:
    total = 0.0
    count = 0
    for v in values:
        total += v
        count += 1
    return total / count if count > 0 else 0.0
