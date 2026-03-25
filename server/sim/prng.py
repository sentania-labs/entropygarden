"""
Seeded PRNG helpers for the simulation.

Strategy: per-system × per-ring seeds derived from the global seed.
Each RNG is recreated per tick from (global_seed, tick, system, ring_id)
so ticks are independently replayable without carrying PRNG state.

Python's hash() is not stable across interpreter runs (PYTHONHASHSEED).
We use a manual FNV-1a hash for reproducible seeds.
"""

from __future__ import annotations

import random


def _fnv1a(s: str) -> int:
    """FNV-1a hash — stable across Python runs, unlike hash()."""
    h = 2166136261
    for ch in s.encode():
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def tick_rng(global_seed: int, tick: int, system: str, ring_id: str) -> random.Random:
    """
    Return a seeded Random instance for a specific (tick, system, ring) combination.

    Calling this with the same arguments always returns an equivalent RNG — no
    state needs to be threaded through the tick pipeline.
    """
    combined = _fnv1a(f"{global_seed}:{tick}:{system}:{ring_id}")
    return random.Random(combined)


def init_rng(global_seed: int, system: str, ring_id: str) -> random.Random:
    """
    Return a seeded Random instance for initial state generation.

    Separate from tick_rng so that changing tick math doesn't alter the
    initial population layout for a given seed.
    """
    combined = _fnv1a(f"init:{global_seed}:{system}:{ring_id}")
    return random.Random(combined)
