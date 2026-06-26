"""Periodic self-update checker for the running app.

Polls GitHub for a newer release on a timer (default 60s) and prompts AT MOST
once per discovered version. It threads the updater's ETag through each poll, so
repeat checks that find nothing new return ``304`` — which GitHub does not count
against the unauthenticated 60/hour rate limit — keeping a 60s cadence safe.

Imports only ``updater`` (logic); the Tk root and the prompt action are injected,
so it is unit-testable headless with a fake root.
"""

from __future__ import annotations

import threading
from typing import Callable

from . import updater

DEFAULT_INTERVAL_MS = 60_000


class UpdateChecker:
    def __init__(
        self,
        root,
        context: str,
        on_update: Callable[[updater.UpdateInfo], None],
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> None:
        self._root = root
        self._context = context
        self._on_update = on_update
        self._interval_ms = interval_ms
        self._etag: str | None = None
        self._prompted_version: str | None = None

    def start(self) -> None:
        """Run the first check now, then keep checking on the interval."""
        self._tick()

    def _tick(self) -> None:
        """Main-thread: poll on a worker (so the UI never blocks), then re-arm."""
        threading.Thread(target=self._check, daemon=True).start()
        self._root.after(self._interval_ms, self._tick)

    def _check(self) -> None:
        """Worker-thread: poll, remember the ETag, prompt once per new version."""
        info = updater.check_for_update(context=self._context, etag=self._etag)
        if info.etag:
            self._etag = info.etag
        if info.available and info.latest_version != self._prompted_version:
            self._prompted_version = info.latest_version
            self._root.after(0, lambda: self._on_update(info))
