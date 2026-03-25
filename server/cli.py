"""
CLI runner for the generation ship simulation.

Usage:
    python3 -m server.cli --seed 42 --ticks 365
    python3 -m server.cli --seed 42 --ticks 365 --verbose
    python3 -m server.cli --seed 42 --ticks 365 --json

Run from the repo root:
    cd /path/to/entropygarden
    python3 -m server.cli --seed 42 --ticks 365
"""

from __future__ import annotations

import argparse
import json
import sys
import time

# Allow running as `python3 -m server.cli` from the repo root
# or `python3 cli.py` from within server/
import os
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path

from sim.events import EventDef, load_events
from sim.initializer import build_initial_state
from sim.state import EventRecord, GameState, SimConfig
from sim.tick import tick

_EVENTS_PATH = Path(__file__).parent.parent / "data" / "events.yaml"


def summarize(state: GameState) -> dict[str, object]:
    """Produce a human-readable summary dict for a game state."""
    ring_summaries = {}
    for ring_id, ring in state.rings.items():
        pop = ring.population
        ring_summaries[ring_id] = {
            "population": len(pop),
            "mean_health": round(sum(p.health for p in pop) / len(pop), 3) if pop else 0,
            "mean_morale": round(sum(p.morale for p in pop) / len(pop), 3) if pop else 0,
            "resources": {
                "food": round(ring.resources.food, 1),
                "water": round(ring.resources.water, 1),
                "oxygen": round(ring.resources.oxygen, 1),
                "power": round(ring.resources.power, 1),
            },
            "pressures": {
                "maintenance_debt": round(ring.pressures.maintenance_debt, 4),
                "ecological_drift": round(ring.pressures.ecological_drift, 4),
                "social_tension": round(ring.pressures.social_tension, 4),
            },
        }

    total_pop = sum(len(r.population) for r in state.rings.values())
    return {
        "tick": state.tick,
        "year": round(state.year, 2),
        "total_population": total_pop,
        "rings": ring_summaries,
    }


def run(seed: int, ticks: int, verbose: bool, output_json: bool) -> None:
    cfg = SimConfig()
    state = build_initial_state(seed=seed, config=cfg)

    event_defs: list[EventDef] = []
    if _EVENTS_PATH.exists():
        event_defs = load_events(_EVENTS_PATH)

    if not output_json:
        print(f"Entropy Garden — seed={seed}, pop={sum(len(r.population) for r in state.rings.values())}")
        print(f"Running {ticks} ticks ({ticks/365:.1f} game-years)...\n")

    if verbose:
        _print_state(state, output_json)

    start = time.monotonic()
    prev_log_len = 0
    for i in range(ticks):
        state = tick(state, cfg, event_defs if event_defs else None)
        new_events = state.event_log[prev_log_len:]
        prev_log_len = len(state.event_log)
        if verbose:
            _print_state(state, output_json)
            if not output_json:
                for ev in new_events:
                    _print_event(ev)
        elif new_events and not output_json:
            for ev in new_events:
                _print_event(ev)

    elapsed = time.monotonic() - start

    if not verbose:
        _print_state(state, output_json)

    if not output_json:
        total_events = len(state.event_log)
        print(f"\n{ticks} ticks in {elapsed:.2f}s ({ticks/elapsed:.0f} ticks/sec) | {total_events} events fired")


def _print_state(state: GameState, as_json: bool) -> None:
    summary = summarize(state)
    if as_json:
        print(json.dumps(summary))
    else:
        print(f"Tick {summary['tick']:>6}  |  Year {summary['year']:>7.2f}  |  "
              f"Pop {summary['total_population']:>5}")
        for ring_id, r in summary["rings"].items():  # type: ignore[union-attr]
            p = r["pressures"]  # type: ignore[index]
            res = r["resources"]  # type: ignore[index]
            print(
                f"  {ring_id}: pop={r['population']:>4}  "  # type: ignore[index]
                f"health={r['mean_health']:.3f}  morale={r['mean_morale']:.3f}  "  # type: ignore[index]
                f"food={res['food']:>6.1f}  debt={p['maintenance_debt']:.4f}  "
                f"drift={p['ecological_drift']:.4f}  tension={p['social_tension']:.4f}"
            )


def _print_event(ev: EventRecord) -> None:
    scope = ev.ring_id if ev.ring_id else "ALL RINGS"
    effects_str = "  ".join(f"{k}={v:+.3g}" for k, v in ev.effects_applied.items())
    print(f"  [EVENT tick={ev.tick} {scope}] {ev.event_name} | {effects_str}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generation ship simulation runner")
    parser.add_argument("--seed", type=int, default=42, help="Global PRNG seed")
    parser.add_argument("--ticks", type=int, default=365, help="Number of ticks to advance")
    parser.add_argument("--verbose", action="store_true", help="Print state after every tick")
    parser.add_argument("--json", action="store_true", dest="output_json",
                        help="Output NDJSON (one JSON object per printed state)")
    args = parser.parse_args()
    run(seed=args.seed, ticks=args.ticks, verbose=args.verbose, output_json=args.output_json)


if __name__ == "__main__":
    main()
