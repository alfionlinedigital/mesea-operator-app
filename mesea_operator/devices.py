"""Admin-only device directory lookup for the demo-device picker.

Calls ``GET /api/v1/devices`` (workstream B) with the operator bearer token to
list registered hardware, optionally filtered by a name/serial substring (``q``)
or to only-unassigned devices. Pure and list-returning — no Tk — so the picker's
networking is unit-testable against a stub server, mirroring ``api.py``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import config


class DevicesError(Exception):
    """Device lookup failed (HTTP, network, or unparseable response)."""


def _build_url(url: str, q: str | None, unassigned: bool | None) -> str:
    params: dict[str, str] = {}
    if q:
        params["q"] = q
    if unassigned is not None:
        params["unassigned"] = "true" if unassigned else "false"
    if not params:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urllib.parse.urlencode(params)}"


def fetch_devices(
    token: str,
    q: str | None = None,
    unassigned: bool | None = None,
    url: str | None = None,
) -> list[dict]:
    """Return the device list from the API, raising ``DevicesError`` on failure.

    Each item is the raw ``DeviceResponse`` dict (keys read by the caller with
    ``.get`` so a field rename on the server degrades gracefully, never crashes).
    """
    target = _build_url(url or config.DEVICES_URL, q, unassigned)
    req = urllib.request.Request(
        target,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise DevicesError(f"Device lookup failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise DevicesError(f"Could not reach the device endpoint: {exc.reason}") from exc
    except ValueError as exc:
        raise DevicesError("Device endpoint returned invalid JSON.") from exc

    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise DevicesError(f"Unexpected device response shape: {payload!r}")
    return [d for d in data if isinstance(d, dict)]
