"""
Decision window lifecycle and conflict resolution.

Pure logic — no I/O, no async. All models imported from sim.state to avoid
circular imports.
"""

from __future__ import annotations

import uuid

from .state import (
    DecisionWindow,
    PendingAction,
    RejectedAction,
    WindowResolution,
    WindowStatus,
)

# Role authority order: index 0 = highest authority.
# Roles absent from this list are treated as lower than all listed roles.
ROLE_HIERARCHY: list[str] = [
    "captain",
    "engineer",
    "ecologist",
    "governor",
    "ring_1_delegate",
    "ring_2_delegate",
    "ring_3_delegate",
]


def _role_priority(role: str) -> int:
    """Lower value = higher authority. Unknown roles get the lowest authority."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return len(ROLE_HIERARCHY)


def open_window(opened_tick: int, interval: int) -> DecisionWindow:
    """Create a new open DecisionWindow."""
    return DecisionWindow(
        window_id=str(uuid.uuid4()),
        opened_tick=opened_tick,
        closes_tick=opened_tick + interval,
        status=WindowStatus.OPEN,
    )


def resolve_window(
    window: DecisionWindow,
    pending_actions: list[PendingAction],
) -> tuple[DecisionWindow, list[PendingAction]]:
    """
    Close a window and apply role-hierarchy conflict resolution.

    Two actions conflict when they target the same ring_id.  For each ring,
    the action from the highest-authority role wins; all others are rejected.
    Actions on different rings never conflict with each other.

    Returns:
      - A closed DecisionWindow with resolution populated.
      - The filtered list of PendingActions (conflicts removed).
    """
    # Group actions by ring_id
    by_ring: dict[str, list[PendingAction]] = {}
    for action in pending_actions:
        by_ring.setdefault(action.ring_id, []).append(action)

    accepted: list[PendingAction] = []
    rejected: list[RejectedAction] = []

    for ring_actions in by_ring.values():
        if len(ring_actions) == 1:
            accepted.append(ring_actions[0])
            continue

        # Sort by authority (ascending index = higher authority)
        sorted_actions = sorted(ring_actions, key=lambda a: _role_priority(a.role))
        winner = sorted_actions[0]
        accepted.append(winner)

        for loser in sorted_actions[1:]:
            rejected.append(
                RejectedAction(
                    action_id=loser.action_id,
                    role=loser.role,
                    reason=f"overridden_by_{winner.role}",
                    overridden_by_role=winner.role,
                )
            )

    accepted_ids = [a.action_id for a in accepted]
    resolution = WindowResolution(
        accepted_action_ids=accepted_ids,
        rejected=rejected,
        fallback_roles=[],  # populated by store after absent-role detection
    )

    closed_window = window.model_copy(
        update={
            "status": WindowStatus.CLOSED,
            "resolution": resolution,
        }
    )
    return closed_window, accepted
