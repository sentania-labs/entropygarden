"""
Policy evaluation: standing orders that guide AI behavior for absent roles.

Pure logic — no I/O, no async. All models imported from sim.state.
"""

from __future__ import annotations

from .state import Policy

# All roles known to the system for MVP
ALL_ROLES: list[str] = [
    "captain",
    "engineer",
    "ecologist",
    "governor",
    "ring_delegate",
]


def get_absent_roles(
    submitted_roles: list[str],
    active_roles: list[str] | None = None,
) -> list[str]:
    """
    Return roles that are active but did not submit during the window.

    submitted_roles: roles that submitted an action (from DecisionWindow.submitted).
    active_roles: the roles tracked for this game instance. Defaults to ALL_ROLES.
    """
    roles = active_roles if active_roles is not None else ALL_ROLES
    submitted_set = set(submitted_roles)
    return [r for r in roles if r not in submitted_set]


def policy_to_context(policy: Policy) -> str:
    """
    Serialize a Policy into a plain-text summary for LLM prompt injection.

    Returns a compact text block describing the standing orders so an agent
    can use them as context when deciding in the role's absence.
    """
    if not policy.priorities:
        return f"Standing orders for {policy.role}: none set."

    lines = [f"Standing orders for {policy.role}:"]
    for i, p in enumerate(policy.priorities, start=1):
        note_suffix = f" ({p.note})" if p.note else ""
        lines.append(f"  {i}. {p.action_type} on {p.ring_id}{note_suffix}")
    return "\n".join(lines)


def compliance_check(policy: Policy, rng_value: float) -> bool:
    """
    Return True if the agent should follow the policy this window.

    rng_value: a float in [0, 1] from the game's seeded PRNG.
    Stub for MVP: returns True when rng_value < policy.compliance.
    At compliance=1.0 this is always True (full compliance).
    """
    return rng_value < policy.compliance
