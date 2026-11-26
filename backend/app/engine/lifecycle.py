"""Module E: recommendation states. `executed -> verified` is only reachable through
mark_verified(), which requires a successful verification result."""
from __future__ import annotations

STATES = ["detected", "reviewed", "approved", "executed", "verified", "rejected", "failed", "requires_manual_review"]

# Transitions a person can request through the API.
MANUAL_TRANSITIONS: dict[str, set[str]] = {
    "detected": {"reviewed", "rejected", "requires_manual_review"},
    "requires_manual_review": {"reviewed", "rejected"},
    "reviewed": {"approved", "rejected", "requires_manual_review"},
    "approved": {"rejected", "reviewed"},
    "failed": {"reviewed", "rejected"},
    "rejected": {"detected"},
    "executed": set(),
    "verified": set(),
}
# Transitions only the remediation/verification service makes.
SYSTEM_TRANSITIONS: dict[str, set[str]] = {
    "approved": {"executed", "failed"},
    "executed": {"verified", "failed"},
}


class TransitionError(Exception):
    pass


def check_manual(current: str, target: str) -> None:
    if target not in MANUAL_TRANSITIONS.get(current, set()):
        allowed = ", ".join(sorted(MANUAL_TRANSITIONS.get(current, set()))) or "none"
        raise TransitionError(f"can't move from '{current}' to '{target}' (allowed: {allowed})")


def check_system(current: str, target: str, verification_ok: bool | None = None) -> None:
    if target not in SYSTEM_TRANSITIONS.get(current, set()):
        raise TransitionError(f"can't move from '{current}' to '{target}'")
    if target == "verified" and verification_ok is not True:
        raise TransitionError("'verified' needs a successful verification")
