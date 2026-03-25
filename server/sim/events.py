"""
Event system for the generation ship simulation.

Events are pure, deterministic functions — no I/O, no LLM, no mutation.

Two trigger types:
  threshold — fires when a ring's hidden pressure >= threshold and cooldown has elapsed
  random    — fires with probability_per_tick chance per tick (uses tick_rng)

Two scopes:
  ring  — evaluated per-ring; effects apply to that ring only
  ship  — evaluated once per tick; effects apply to all rings

Effects are applied immediately on trigger. Choices are defined in the YAML
but not yet resolved by players; that comes with the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sim.prng import tick_rng
from sim.state import EventRecord, GameState, RingState, SimConfig


# ---------------------------------------------------------------------------
# Event definition (loaded from YAML once at startup)
# ---------------------------------------------------------------------------


@dataclass
class EventDef:
    id: str
    name: str
    description: str
    trigger: dict[str, Any]     # {type, pressure?, threshold?, cooldown_ticks?, probability_per_tick?}
    scope: str                   # "ring" | "ship"
    effects: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_events(path: Path) -> list[EventDef]:
    """Load event definitions from a YAML file. Call once at startup."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return [
        EventDef(
            id=e["id"],
            name=e["name"],
            description=e["description"],
            trigger=e["trigger"],
            scope=e.get("scope", "ring"),
            effects={k: float(v) for k, v in e.get("effects", {}).items()},
        )
        for e in data["events"]
    ]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_events(
    state: GameState,
    event_defs: list[EventDef],
    cfg: SimConfig,
) -> tuple[GameState, list[EventRecord]]:
    """
    Evaluate all event definitions against the current state.
    Returns a new GameState (with effects applied and logs updated) and
    the list of EventRecords that fired this tick.

    Pure function — does not mutate state.
    """
    new_rings = dict(state.rings)
    new_cooldowns = dict(state.event_cooldowns)
    fired_this_tick: list[EventRecord] = []

    for event in event_defs:
        trigger_type = event.trigger["type"]

        if event.scope == "ring":
            for ring_id, ring in list(new_rings.items()):
                should_fire = False

                if trigger_type == "threshold":
                    should_fire = _check_threshold(event, ring, tick=state.tick, cooldowns=new_cooldowns)
                elif trigger_type == "random":
                    rng = tick_rng(state.seed, state.tick, f"events_{event.id}", ring_id)
                    should_fire = rng.random() < event.trigger["probability_per_tick"]

                if should_fire:
                    eff_rng = tick_rng(state.seed, state.tick, f"effects_{event.id}", ring_id)
                    new_rings[ring_id] = _apply_effects(ring, event.effects, eff_rng, cfg)
                    new_cooldowns[f"{event.id}:{ring_id}"] = state.tick
                    fired_this_tick.append(EventRecord(
                        tick=state.tick,
                        ring_id=ring_id,
                        event_id=event.id,
                        event_name=event.name,
                        description=event.description,
                        effects_applied=dict(event.effects),
                    ))

        elif event.scope == "ship":
            should_fire = False

            if trigger_type == "random":
                rng = tick_rng(state.seed, state.tick, f"events_{event.id}", "ship")
                should_fire = rng.random() < event.trigger["probability_per_tick"]
            elif trigger_type == "threshold":
                pressure_name = event.trigger["pressure"]
                threshold = float(event.trigger["threshold"])
                cooldown = int(event.trigger.get("cooldown_ticks", 0))
                cooldown_key = f"{event.id}:ship"
                last_fired = new_cooldowns.get(cooldown_key, -(cooldown + 1))
                if (state.tick - last_fired) >= cooldown:
                    should_fire = any(
                        getattr(r.pressures, pressure_name) >= threshold
                        for r in new_rings.values()
                    )

            if should_fire:
                for ring_id in list(new_rings.keys()):
                    eff_rng = tick_rng(state.seed, state.tick, f"effects_{event.id}", ring_id)
                    new_rings[ring_id] = _apply_effects(new_rings[ring_id], event.effects, eff_rng, cfg)
                new_cooldowns[f"{event.id}:ship"] = state.tick
                fired_this_tick.append(EventRecord(
                    tick=state.tick,
                    ring_id=None,
                    event_id=event.id,
                    event_name=event.name,
                    description=event.description,
                    effects_applied=dict(event.effects),
                ))

    new_state = state.model_copy(update={
        "rings": new_rings,
        "event_cooldowns": new_cooldowns,
        "event_log": list(state.event_log) + fired_this_tick,
    })
    return new_state, fired_this_tick


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_threshold(
    event: EventDef,
    ring: RingState,
    tick: int,
    cooldowns: dict[str, int],
) -> bool:
    """Return True if the threshold trigger condition is met and cooldown has elapsed."""
    pressure_name: str = event.trigger["pressure"]
    threshold = float(event.trigger["threshold"])
    cooldown = int(event.trigger.get("cooldown_ticks", 0))

    if getattr(ring.pressures, pressure_name) < threshold:
        return False

    cooldown_key = f"{event.id}:{ring.ring_id}"
    last_fired = cooldowns.get(cooldown_key, -(cooldown + 1))
    return (tick - last_fired) >= cooldown


def _apply_effects(
    ring: RingState,
    effects: dict[str, float],
    rng: Any,  # random.Random — passed for future use (e.g. pop_loss targeting)
    cfg: SimConfig,
) -> RingState:
    """Apply event effects to a ring. Returns a new RingState."""
    resources = ring.resources
    pressures = ring.pressures
    population = list(ring.population)

    # Resource deltas
    resource_updates: dict[str, float] = {}
    for key in ("food", "water", "oxygen", "power"):
        delta = effects.get(f"{key}_delta", 0.0)
        if delta:
            resource_updates[key] = max(0.0, min(cfg.resource_capacity, getattr(resources, key) + delta))
    if resource_updates:
        resources = resources.model_copy(update=resource_updates)

    # Pressure deltas
    pressure_updates: dict[str, float] = {}
    for key in ("maintenance_debt", "ecological_drift", "social_tension"):
        delta = effects.get(f"{key}_delta", 0.0)
        if delta:
            pressure_updates[key] = max(0.0, min(1.0, getattr(pressures, key) + delta))
    if pressure_updates:
        pressures = pressures.model_copy(update=pressure_updates)

    # Morale delta — applied to every person
    morale_delta = effects.get("morale_delta", 0.0)
    if morale_delta:
        population = [
            p.model_copy(update={"morale": max(0.0, min(1.0, p.morale + morale_delta))})
            for p in population
        ]

    # Health delta — applied to every person
    health_delta = effects.get("health_delta", 0.0)
    if health_delta:
        population = [
            p.model_copy(update={"health": max(0.0, min(1.0, p.health + health_delta))})
            for p in population
        ]

    # Population loss — remove N lowest-health people
    pop_loss = int(effects.get("population_loss", 0))
    if pop_loss and population:
        population.sort(key=lambda p: p.health)
        population = population[pop_loss:]

    return ring.model_copy(update={
        "resources": resources,
        "pressures": pressures,
        "population": population,
    })
