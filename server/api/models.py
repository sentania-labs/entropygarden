"""
Pydantic response models for the Entropy Garden API.
"""

from __future__ import annotations

from pydantic import BaseModel

from sim.state import EventRecord, GameState


class RingSummary(BaseModel):
    population: int
    mean_health: float
    mean_morale: float
    resources: dict[str, float]
    pressures: dict[str, float]


class GameSummary(BaseModel):
    game_id: str
    seed: int
    tick: int
    year: float
    total_population: int
    tick_rate: float
    paused: bool
    rings: dict[str, RingSummary]


class GameListItem(BaseModel):
    game_id: str
    seed: int
    tick: int
    year: float
    total_population: int
    tick_rate: float
    paused: bool


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
    return GameSummary(
        game_id=state.game_id,
        seed=state.seed,
        tick=state.tick,
        year=round(state.year, 2),
        total_population=sum(len(r.population) for r in state.rings.values()),
        tick_rate=tick_rate,
        paused=paused,
        rings=rings,
    )
