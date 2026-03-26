"""
Core state models for the generation ship simulation.

All models are Pydantic BaseModel and fully JSON-serializable.
State is immutable in the tick pipeline — tick() returns a new GameState.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Trait(str, Enum):
    RESILIENT = "resilient"      # dampens health/morale loss
    ANXIOUS = "anxious"          # amplifies morale loss from bad events
    SKILLED = "skilled"          # boosts occupation productivity
    LAZY = "lazy"                # reduces productivity
    INFLUENTIAL = "influential"  # increases influence gain rate
    REBELLIOUS = "rebellious"    # raises social_tension when morale is low


class Occupation(str, Enum):
    FARMER = "farmer"                    # produces Food
    ENGINEER = "engineer"                # slows Maintenance Debt accumulation
    MEDIC = "medic"                      # improves population health
    LIFE_SUPPORT = "life_support"        # produces Oxygen + Water
    ADMINISTRATOR = "administrator"      # dampens Social Tension
    LABORER = "laborer"                  # general-purpose resource production


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------


class Person(BaseModel):
    person_id: str
    name: str
    age: float                                  # game-years
    occupation: Occupation
    health: float = Field(ge=0.0, le=1.0)       # 0–1
    morale: float = Field(ge=0.0, le=1.0)       # 0–1
    influence: float = Field(ge=0.0, le=1.0)    # 0–1
    ring_id: str
    traits: list[Trait] = Field(default_factory=list)   # 0–3 traits; mutable
    parent_ids: tuple[str, str] | None = None           # None for founding gen


# ---------------------------------------------------------------------------
# Ring-level aggregates
# ---------------------------------------------------------------------------


class ResourcePool(BaseModel):
    food: float = Field(ge=0.0)
    water: float = Field(ge=0.0)
    oxygen: float = Field(ge=0.0)
    power: float = Field(ge=0.0)
    morale: float = Field(ge=0.0, le=1.0)   # ring-level mean of individual morale


class HiddenPressures(BaseModel):
    maintenance_debt: float = Field(ge=0.0, le=1.0)
    ecological_drift: float = Field(ge=0.0, le=1.0)
    social_tension: float = Field(ge=0.0, le=1.0)


class RingState(BaseModel):
    ring_id: str
    population: list[Person]
    resources: ResourcePool
    pressures: HiddenPressures


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class EventRecord(BaseModel):
    tick: int
    ring_id: str | None         # None = ship-wide event
    event_id: str
    event_name: str
    description: str
    effects_applied: dict[str, float]


# ---------------------------------------------------------------------------
# Actions & modifiers
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    PRIORITIZE_MAINTENANCE = "prioritize_maintenance"  # redirect engineer effort to one ring
    EMERGENCY_REPAIR = "emergency_repair"              # one-shot: -0.05 debt, costs 5 power
    DIVERT_POWER = "divert_power"                      # transfer power between rings
    RATION_RESOURCE = "ration_resource"                # -20% consumption for 30 ticks
    BOOST_PRODUCTION = "boost_production"              # +20% production for 30 ticks


# ---------------------------------------------------------------------------
# Decision windows
# ---------------------------------------------------------------------------


class WindowStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class RejectedAction(BaseModel):
    action_id: str
    role: str
    reason: str
    overridden_by_role: str | None = None


class WindowResolution(BaseModel):
    accepted_action_ids: list[str] = Field(default_factory=list)
    rejected: list[RejectedAction] = Field(default_factory=list)
    fallback_roles: list[str] = Field(default_factory=list)


class DecisionWindow(BaseModel):
    window_id: str
    opened_tick: int
    closes_tick: int
    status: WindowStatus = WindowStatus.OPEN
    submitted: list[str] = Field(default_factory=list)   # roles that submitted an action
    resolution: WindowResolution | None = None


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


class PolicyPriority(BaseModel):
    action_type: str        # must be a valid ActionType value
    ring_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    note: str = ""          # human-readable rationale shown to LLM as context


class Policy(BaseModel):
    role: str
    priorities: list[PolicyPriority] = Field(default_factory=list)
    # Compliance probability 0–1; stubbed at 1.0 for MVP, can be tuned later
    compliance: float = Field(default=1.0, ge=0.0, le=1.0)


class PendingAction(BaseModel):
    action_id: str
    role: str
    action_type: ActionType
    ring_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    submitted_tick: int


class ActiveModifier(BaseModel):
    modifier_id: str
    action_type: ActionType
    ring_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    expires_tick: int


# ---------------------------------------------------------------------------
# Top-level game state
# ---------------------------------------------------------------------------


class GameState(BaseModel):
    game_id: str
    tick: int = Field(ge=0)         # absolute day counter
    seed: int
    rings: dict[str, RingState]     # keyed by ring_id: "ring_1" | "ring_2" | "ring_3"
    event_log: list[EventRecord] = Field(default_factory=list)
    event_cooldowns: dict[str, int] = Field(default_factory=dict)  # "{event_id}:{ring_id}" -> last tick fired
    pending_actions: list[PendingAction] = Field(default_factory=list)
    active_modifiers: list[ActiveModifier] = Field(default_factory=list)
    decision_window_interval: int = 100  # ticks between decision windows
    current_window: DecisionWindow | None = None
    policies: dict[str, Policy] = Field(default_factory=dict)       # role → Policy
    window_history: list[DecisionWindow] = Field(default_factory=list)

    @property
    def year(self) -> float:
        """Current game-year (fractional)."""
        return self.tick / 365.0

    def all_people(self) -> list[Person]:
        """Flat list of all living individuals across all rings."""
        return [p for ring in self.rings.values() for p in ring.population]


# ---------------------------------------------------------------------------
# Configuration (tunable constants — not hardcoded in logic)
# ---------------------------------------------------------------------------


@dataclass
class SimConfig:
    # Resource consumption per person per tick (1 tick = 1 game-day)
    food_per_person: float = 0.003        # units/person/day
    water_per_person: float = 0.005       # units/person/day
    oxygen_per_person: float = 0.004      # units/person/day
    power_per_ring: float = 0.5           # units/ring/day (systems overhead)

    # Resource production per worker per tick (at base productivity)
    food_per_farmer: float = 0.008
    oxygen_per_life_support: float = 0.012
    water_per_life_support: float = 0.010
    power_per_laborer: float = 0.002      # laborers contribute a little power

    # Health
    health_decay_per_tick: float = 0.0001     # slow baseline aging/wear
    medic_heal_per_tick: float = 0.0005       # per medic in ring, spread across pop

    # Morale
    morale_resource_sensitivity: float = 0.002   # loss per % resource deficit
    morale_tension_sensitivity: float = 0.001    # loss per social_tension unit/tick

    # Pressure accumulation rates (per tick)
    maintenance_debt_rate: float = 0.0002        # base creep
    maintenance_debt_per_engineer: float = 0.00015  # reduction per engineer
    ecological_drift_rate: float = 0.00015       # base creep
    ecological_drift_per_farmer: float = 0.00010 # reduction per farmer
    ecological_drift_per_life_support: float = 0.00008
    social_tension_rate: float = 0.0001          # base creep when morale low
    social_tension_per_administrator: float = 0.00008  # dampening per admin

    # Trait multipliers
    trait_resilient_health_mult: float = 0.7
    trait_resilient_morale_mult: float = 0.8
    trait_anxious_morale_mult: float = 1.3
    trait_skilled_output_mult: float = 1.25
    trait_lazy_output_mult: float = 0.75
    trait_influential_influence_mult: float = 1.5
    trait_rebellious_tension_mult: float = 1.5
    trait_rebellious_threshold: float = 0.4   # morale below this triggers REBELLIOUS

    # Inheritance probabilities
    inherit_both_parents: float = 0.70
    inherit_one_parent: float = 0.35
    inherit_spontaneous: float = 0.05
    max_traits: int = 3

    # Reproduction
    reproduction_age_min: float = 18.0
    reproduction_age_max: float = 45.0
    base_birth_rate: float = 0.00008    # per eligible person per tick

    # Resource starvation health impact
    starvation_threshold: float = 0.15      # resource fill below this causes health damage
    starvation_health_penalty: float = 0.008  # max health loss per tick at fill=0

    # Mortality
    mortality_age_threshold: float = 65.0
    mortality_health_threshold: float = 0.15
    base_mortality_rate: float = 0.00002

    # Initial state
    initial_pop_per_ring: int = 333
    initial_resource_fill: float = 0.70     # fraction of capacity
    resource_capacity: float = 500.0        # max units per resource per ring
    initial_maintenance_debt: float = 0.05
    initial_ecological_drift: float = 0.02
    initial_social_tension: float = 0.01

    # Occupation distribution (fractions, must sum to ~1.0)
    occupation_weights: dict[str, float] = field(default_factory=lambda: {
        "farmer": 0.28,
        "engineer": 0.18,
        "medic": 0.08,
        "life_support": 0.15,
        "administrator": 0.06,
        "laborer": 0.25,
    })
