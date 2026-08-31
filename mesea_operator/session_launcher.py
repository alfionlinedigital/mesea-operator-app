"""The launch-a-Claude-session sequence, extracted out of the thin view.

`ui.py` used to hold this as a closure over Tk state, which made the ordering
rules below untestable — and they are the rules that matter most, because two
of them are about not leaving the AM's token lying in `settings.json`:

  1. workspace first: no session at all without the skills bundle;
  2. Node next, so the workspace's Playwright MCP can actually start;
  3. the token is scrubbed in a `finally`, on every exit path including a
     failed launch.

Tk-free by construction: the caller passes a `SessionCallbacks` bundle, so this
module is importable and testable on a headless machine like every other
non-view module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from . import claude_bridge, node_runtime, workspace

logger = logging.getLogger(__name__)


@dataclass
class SessionCallbacks:
    """View hooks. `on_error` and `on_finished` are marshalled to the UI thread
    by the caller; `set_status` must be safe to call from a worker thread."""

    set_status: Callable[[str], None]
    on_error: Callable[[str], None]
    on_finished: Callable[[], None]


def run_session(
    token: str,
    executable: str,
    resume: bool,
    callbacks: SessionCallbacks,
) -> None:
    """Refresh the workspace, guarantee Node, run Claude, then always scrub.

    Blocks until Claude exits — the caller runs it on a worker thread.
    """
    ws = workspace.ensure_workspace(token)
    if ws.status == "error":
        # Nothing launched, so the staged token has no consumer — take it back
        # out of settings.json rather than leaving it there until next run.
        claude_bridge.scrub_session()
        callbacks.on_error(ws.detail)
        callbacks.on_finished()
        return

    # macOS .dmg / portable builds have no installer step to run
    # `--ensure-node`; this is where they get theirs. A no-op when Node is
    # already on PATH, and non-fatal when it cannot be fetched — the AM only
    # loses the Playwright-driven website steps of a demo.
    callbacks.set_status("Se verifică Node.js…")
    node = node_runtime.ensure()
    if node.status == "unavailable":
        logger.warning("Node unavailable, Playwright MCP will not start: %s", node.detail)

    callbacks.set_status("Se pornește Claude…")
    try:
        proc = claude_bridge.launch_claude(executable, str(ws.path), resume=resume)
        proc.wait()
    finally:
        claude_bridge.scrub_session()
        callbacks.set_status("Claude s-a închis. Token-ul a fost retras din config.")
        callbacks.on_finished()
