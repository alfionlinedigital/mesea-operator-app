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

    Returns ``True`` only on a 2xx response. A 401/403 (expired or revoked
    token), a missing token, or any other non-2xx status returns ``False`` so
    the launcher can block startup and tell the AM to re-authorize. A transient
    network error also returns ``False`` — we never proceed on an unconfirmed
    token. The token value is never logged or echoed.
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
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError:
        return False


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
