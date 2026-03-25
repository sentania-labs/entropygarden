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
from sim.population import age_person, apply_medic_heal, apply_starvation, is_dead, reproduce, update_morale
from sim.pressures import accumulate_pressures
from sim.prng import tick_rng
from sim.resources import consumption_for_ring, production_for_ring
from sim.state import GameState, Occupation, Person, ResourcePool, RingState, SimConfig


def tick(
    state: GameState,
    cfg: SimConfig | None = None,
    event_defs: list[EventDef] | None = None,
) -> GameState:
    """Advance the simulation by one tick. Returns a new GameState."""
    if cfg is None:
        cfg = SimConfig()

    new_rings: dict[str, RingState] = {}
    new_person_counter = state.tick  # use tick as part of unique ID for new births

    for ring_id, ring in state.rings.items():
        ring, new_person_counter = _tick_ring(
            ring, state.seed, state.tick, cfg, new_person_counter
        )
        new_rings[ring_id] = ring

    mid_state = state.model_copy(update={"rings": new_rings, "tick": state.tick + 1})

    # 12. Event evaluation (ship-level, after all rings are updated)
    if event_defs:
        mid_state, _ = evaluate_events(mid_state, event_defs, cfg)

    return mid_state


def _tick_ring(
    ring: RingState,
    seed: int,
    tick_num: int,
    cfg: SimConfig,
    person_counter: int,
) -> tuple[RingState, int]:
    population = list(ring.population)
    ring_id = ring.ring_id

    # 1. Age + health decay
    population = [age_person(p, cfg) for p in population]

    # 2. Medic healing
    medic_count = sum(1 for p in population if p.occupation == Occupation.MEDIC)
    pop_size = len(population)
    population = [apply_medic_heal(p, medic_count, pop_size, cfg) for p in population]

    # 3 & 4. Resource consumption and production
    consumed = consumption_for_ring(population, cfg)
    produced = production_for_ring(population, cfg)

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

    # 7. Pressure accumulation
    new_pressures = accumulate_pressures(ring.pressures, population, cfg)

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
