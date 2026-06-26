"""Optional crash/error reporting to Bugsink — a self-hosted, Sentry-compatible
ingest. Initialised once at startup; a missing DSN or an unavailable
``sentry_sdk`` disables it SILENTLY so the launcher always runs. Importable
headless (no Tk).

With Sentry's default logging integration, anything logged at ``ERROR`` (e.g. a
workspace that can't be reached) is captured as an event, and unhandled
exceptions are reported automatically.
"""

from __future__ import annotations

import logging

from . import config

logger = logging.getLogger(__name__)


def init_error_reporting(release: str) -> bool:
    """Initialise Bugsink/Sentry reporting. Returns ``True`` when active.

    No-ops (returns ``False``) when no DSN is configured or ``sentry_sdk`` can't
    be imported — reporting is best-effort and must never block startup.
    """
    dsn = config.BUGSINK_DSN
    if not dsn:
        logger.info("no Bugsink DSN configured; error reporting disabled")
        return False
    try:
        import sentry_sdk
    except Exception:  # ImportError, or a broken/partial bundle in the frozen app
        logger.warning("sentry_sdk unavailable; error reporting disabled")
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            release=f"mesea-operator@{release}",
            traces_sample_rate=0.0,
            send_default_pii=False,
        )
    except Exception:
        logger.exception("failed to initialise error reporting")
        return False
    logger.info("error reporting initialised (release %s)", release)
    return True
