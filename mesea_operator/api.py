"""Minimal Mesea API calls the launcher makes directly (stdlib only).

Just two: confirm an issued token works + read its display label (`get_me`),
and revoke a token on sign-out. Kept separate from oauth_client so it's
unit-testable against a stub server without touching the OAuth flow.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import config


class TokenUnreachable(Exception):
    """The token could not be confirmed valid *or* invalid.

    Raised by :func:`is_token_valid` on a transient server fault (HTTP >= 500)
    or a network/URL error. The caller must fail *closed* (treat the session as
    unusable for now) but must NOT treat it as a revoked token — we simply could
    not verify it, so re-authentication is not the right remedy.
    """


def fetch_identity(token: str) -> str | None:
    """Return the token's human label from /api/v1/me, or None on failure.

    Never raises — identity is best-effort UI polish; the token is still
    usable if the probe fails.
    """
    req = urllib.request.Request(
        config.ME_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError):
        return None
    body = data.get("data", data)
    return body.get("token_name") or body.get("app_name")


def is_token_valid(token: str | None) -> bool:
    """Probe ``/api/v1/me`` to confirm the stored token is still accepted.

    Three distinct outcomes — never proceed on an unconfirmed token:

    * **valid** → ``True`` on a 2xx response.
    * **definitively invalid** → ``False`` on a missing token or an HTTP 4xx
      (401/403 = expired/revoked, or any other client error). The launcher
      blocks startup and tells the AM to re-authorize.
    * **unverifiable** → raises :class:`TokenUnreachable` on an HTTP 5xx
      (transient server fault) or a network/URL error. A transient outage is
      NOT a revoked token, so the caller fails closed without forcing a re-auth.

    The token value is never logged or echoed.
    """
    if not token:
        return False
    req = urllib.request.Request(
        config.ME_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            raise TokenUnreachable(f"server error {exc.code}") from exc
        return False  # 4xx — the token itself is definitively rejected
    except urllib.error.URLError as exc:
        raise TokenUnreachable(str(exc.reason)) from exc


def revoke(token: str) -> bool:
    """Best-effort token revocation on sign-out. Returns success."""
    payload = json.dumps({"token": token}).encode("utf-8")
    req = urllib.request.Request(
        config.REVOKE_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        return exc.code == 200
    except urllib.error.URLError:
        return False
