"""Pure startup decision logic — no Tk, so it's unit-testable headless.

The UI runs :func:`evaluate_token` on a background thread, then dispatches the
returned :class:`TokenOutcome` back onto the Tk main loop. Keeping the decision
here (instead of inline in ``ui.py``, which imports Tk and can't be imported in
a headless test) lets us cover the fail-open / fail-closed rules directly.
"""

from __future__ import annotations

from enum import Enum

from . import api, workspace


class TokenOutcome(Enum):
    """The three mutually-exclusive states a stored token can resolve to.

    * ``NONE`` — no token stored at all (nothing to validate).
    * ``VALID`` — confirmed accepted by the server; safe to enable launch.
    * ``INVALID`` — definitively rejected (4xx); the AM must re-authorize.
    * ``UNREACHABLE`` — could not be verified (5xx / network); fail closed but
      do NOT claim the token was revoked.
    """

    NONE = "none"
    VALID = "valid"
    INVALID = "invalid"
    UNREACHABLE = "unreachable"


def evaluate_token(token: str | None) -> TokenOutcome:
    """Classify a stored token into exactly one :class:`TokenOutcome`.

    Never raises: :class:`api.TokenUnreachable` is mapped to
    ``UNREACHABLE`` so callers branch on a single value instead of mixing
    return values with exception handling.
    """
    if not token:
        return TokenOutcome.NONE
    try:
        return TokenOutcome.VALID if api.is_token_valid(token) else TokenOutcome.INVALID
    except api.TokenUnreachable:
        return TokenOutcome.UNREACHABLE


def workspace_status_message(result: workspace.WorkspaceResult) -> str | None:
    """Status-line text for a workspace refresh outcome, or ``None`` when it
    succeeded (``downloaded`` / ``up-to-date`` need no message).

    Surfaces BOTH failure shapes so a frozen workspace is visible: a hard
    ``error`` (nothing usable on disk) and a ``skipped`` refresh that fell back
    to the last-good copy — named by its short commit when known, since a silent
    stale fallback is exactly how an un-updating workspace went unnoticed.
    """
    if result.status == "error":
        return f"Atenție workspace: {result.detail}"
    if result.status == "skipped":
        version = f" (commit {result.commit[:7]})" if result.commit else ""
        return f"Workspace neactualizat; se folosește ultima versiune{version}."
    return None
