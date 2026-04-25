"""
Pydantic response models for the Entropy Garden API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from sim.state import ActionType, EventRecord, GameState, JourneyState


class RingHistoryPoint(BaseModel):
    population: int
    mean_health: float
    mean_morale: float
    food: float
    water: float
    oxygen: float
    power: float


class HistoryPoint(BaseModel):
    tick: int
    year: float
    rings: dict[str, RingHistoryPoint]


class RingSummary(BaseModel):
    population: int
    mean_health: float
    mean_morale: float
    resources: dict[str, float]
    pressures: dict[str, float]


class JourneySummary(BaseModel):
    destination: str
    total_distance_ly: float
    distance_remaining_ly: float
    progress_pct: float
    fuel_pct: float
    fuel_efficiency: float
    next_milestone: str | None
    eta_ticks: int | None
    arrival_tick: int | None


class GameSummary(BaseModel):
    game_id: str
    seed: int
    tick: int
    year: float
    total_population: int
    tick_rate: float
    paused: bool
    rings: dict[str, RingSummary]
    journey: JourneySummary | None = None


class GameListItem(BaseModel):
    game_id: str
    seed: int
    tick: int
    year: float
    total_population: int
    tick_rate: float
    paused: bool


# ---------------------------------------------------------------------------
# Role views (information asymmetry encoded at the API layer)
# ---------------------------------------------------------------------------

_ENGINEER_ACTIONS = [a.value for a in ActionType]  # engineer can use all actions for now
_CAPTAIN_ACTIONS = [
    ActionType.RATION_RESOURCE.value,
    ActionType.BOOST_PRODUCTION.value,
    ActionType.DIVERT_POWER.value,
]


class EngineerRingView(BaseModel):
    power: float
    power_fill_pct: float              # 0–100
    maintenance_debt: float            # 0–1
    engineer_count: int
    engineer_fraction: float           # 0–1
    active_modifiers: list[str]        # active modifier types for this ring


class EngineerView(BaseModel):
    game_id: str
    tick: int
    year: float
    role: str = "engineer"
    rings: dict[str, EngineerRingView]
    ship_power_total: float
    recent_events: list[dict[str, Any]]   # power/maintenance-relevant events last 50 ticks
    available_actions: list[str]


class CaptainRingView(BaseModel):
    population: int
    mean_health: float
    mean_morale: float
    food_pct: float        # 0–100
    water_pct: float
    oxygen_pct: float
    power_pct: float
    risk_flags: list[str]  # e.g. ["high_maintenance_debt", "low_food"]


class CaptainView(BaseModel):
    game_id: str
    tick: int
    year: float
    role: str = "captain"
    rings: dict[str, CaptainRingView]
    ship_summary: dict[str, Any]      # total_population, critical_rings, high_tension_rings
    recent_events: list[dict[str, Any]]
    available_actions: list[str]


# ---------------------------------------------------------------------------
# Action request / response
# ---------------------------------------------------------------------------


class ActionRequest(BaseModel):
    role: str
    action_type: str
    ring_id: str
    parameters: dict[str, Any] = {}
    reasoning: str = ""   # populated by agent; stored for audit


class ActionResponse(BaseModel):
    action_id: str
    status: str            # "accepted" | "rejected"
    detail: str = ""
    applied_tick: int


# ---------------------------------------------------------------------------
# State → view helpers
# ---------------------------------------------------------------------------


def build_engineer_view(state: GameState, resource_capacity: float = 500.0) -> EngineerView:
    rings: dict[str, EngineerRingView] = {}
    for ring_id, ring in state.rings.items():
        pop = ring.population
        eng_count = sum(1 for p in pop if p.occupation.value == "engineer")
        active = [
            m.action_type.value
            for m in state.active_modifiers
            if m.ring_id == ring_id
        ]
        rings[ring_id] = EngineerRingView(
            power=round(ring.resources.power, 1),
            power_fill_pct=round(ring.resources.power / resource_capacity * 100, 1),
            maintenance_debt=round(ring.pressures.maintenance_debt, 4),
            engineer_count=eng_count,
            engineer_fraction=round(eng_count / len(pop), 3) if pop else 0.0,
            active_modifiers=active,
        )
    recent = [
        e.model_dump()
        for e in state.event_log[-50:]
        if any(k in e.effects_applied for k in ("power", "maintenance_debt"))
    ]
    return EngineerView(
        game_id=state.game_id,
        tick=state.tick,
        year=round(state.year, 2),
        rings=rings,
        ship_power_total=round(
            sum(r.resources.power for r in state.rings.values()), 1
        ),
        recent_events=recent,
        available_actions=_ENGINEER_ACTIONS,
    )


def build_captain_view(state: GameState, resource_capacity: float = 500.0) -> CaptainView:
    rings: dict[str, CaptainRingView] = {}
    for ring_id, ring in state.rings.items():
        pop = ring.population
        n = len(pop)
        r = ring.resources
        p = ring.pressures

        def pct(val: float) -> float:
            return round(val / resource_capacity * 100, 1)

        flags: list[str] = []
        if p.maintenance_debt > 0.6:
            flags.append("high_maintenance_debt")
        if p.ecological_drift > 0.6:
            flags.append("high_ecological_drift")
        if p.social_tension > 0.6:
            flags.append("high_social_tension")
        if pct(r.food) < 20:
            flags.append("low_food")
        if pct(r.water) < 20:
            flags.append("low_water")
        if pct(r.oxygen) < 20:
            flags.append("low_oxygen")
        if pct(r.power) < 20:
            flags.append("low_power")

        rings[ring_id] = CaptainRingView(
            population=n,
            mean_health=round(sum(pp.health for pp in pop) / n, 3) if n else 0.0,
            mean_morale=round(sum(pp.morale for pp in pop) / n, 3) if n else 0.0,
            food_pct=pct(r.food),
            water_pct=pct(r.water),
            oxygen_pct=pct(r.oxygen),
            power_pct=pct(r.power),
            risk_flags=flags,
        )

    critical = [rid for rid, rv in rings.items() if rv.risk_flags]
    high_tension = [
        rid for rid, ring in state.rings.items()
        if ring.pressures.social_tension > 0.5
    ]
    return CaptainView(
        game_id=state.game_id,
        tick=state.tick,
        year=round(state.year, 2),
        rings=rings,
        ship_summary={
            "total_population": sum(len(r.population) for r in state.rings.values()),
            "critical_rings": critical,
            "high_tension_rings": high_tension,
        },
        recent_events=[e.model_dump() for e in state.event_log[-50:]],
        available_actions=_CAPTAIN_ACTIONS,
    )


def summarize_state(state: GameState, tick_rate: float, paused: bool) -> GameSummary:
    """Convert a GameState into the summary view returned by most REST endpoints."""
    rings: dict[str, RingSummary] = {}
    for ring_id, ring in state.rings.items():
        pop = ring.population
        n = len(pop)
        rings[ring_id] = RingSummary(
            population=n,
            mean_health=round(sum(p.health for p in pop) / n, 3) if n else 0.0,
            mean_morale=round(sum(p.morale for p in pop) / n, 3) if n else 0.0,
            resources={
                "food": round(ring.resources.food, 1),
                "water": round(ring.resources.water, 1),
                "oxygen": round(ring.resources.oxygen, 1),
                "power": round(ring.resources.power, 1),
            },
            pressures={
                "maintenance_debt": round(ring.pressures.maintenance_debt, 4),
                "ecological_drift": round(ring.pressures.ecological_drift, 4),
                "social_tension": round(ring.pressures.social_tension, 4),
            },
        )
    journey_summary = _summarize_journey(state.journey) if state.journey else None

    return GameSummary(
        game_id=state.game_id,
        seed=state.seed,
        tick=state.tick,
        year=round(state.year, 2),
        total_population=sum(len(r.population) for r in state.rings.values()),
        tick_rate=tick_rate,
        paused=paused,
        rings=rings,
        journey=journey_summary,
    )


def _summarize_journey(j: JourneyState) -> JourneySummary:
    progress = (j.total_distance_ly - j.distance_remaining_ly) / j.total_distance_ly if j.total_distance_ly > 0 else 0.0

    # Find next milestone
    reached = set(j.milestones_reached)
    next_ms = None
    for ms in j.milestones:
        if ms.milestone_id not in reached:
            next_ms = ms.name
            break

    # ETA
    eta = None
    if j.distance_remaining_ly > 0 and j.base_speed > 0 and j.fuel > 0:
        speed = j.base_speed * j.fuel_efficiency
        eta = int(j.distance_remaining_ly / speed) if speed > 0 else None

    return JourneySummary(
        destination=j.destination,
        total_distance_ly=round(j.total_distance_ly, 2),
        distance_remaining_ly=round(j.distance_remaining_ly, 4),
        progress_pct=round(progress * 100, 1),
        fuel_pct=round(j.fuel / j.fuel_capacity * 100, 1) if j.fuel_capacity > 0 else 0.0,
        fuel_efficiency=round(j.fuel_efficiency, 3),
        next_milestone=next_ms,
        eta_ticks=eta,
        arrival_tick=j.arrival_tick,
    )
