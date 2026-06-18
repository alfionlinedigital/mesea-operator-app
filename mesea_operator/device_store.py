"""Durable storage for the AM's chosen demo tablet/phone device IDs.

Persisted in the OS credential store (keyring) under a dedicated username so the
choice survives across launches and machine reboots, exactly like the operator
token in ``credential_store``. The IDs are not secrets, but keyring gives us one
consistent, dependency-free persistence path on every OS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import keyring

from . import config

_USERNAME = "demo-devices"  # single per-machine demo-hardware selection


@dataclass
class DemoDevices:
    tablet_id: str | None
    phone_id: str | None


def store(tablet_id: str | None, phone_id: str | None) -> None:
    blob = json.dumps({"tablet_id": tablet_id, "phone_id": phone_id})
    keyring.set_password(config.KEYRING_SERVICE, _USERNAME, blob)


def load() -> DemoDevices:
    """Return the saved selection; empty (both ``None``) when nothing is stored."""
    raw = keyring.get_password(config.KEYRING_SERVICE, _USERNAME)
    if not raw:
        return DemoDevices(None, None)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return DemoDevices(None, None)
    return DemoDevices(tablet_id=data.get("tablet_id"), phone_id=data.get("phone_id"))


def clear() -> None:
    try:
        keyring.delete_password(config.KEYRING_SERVICE, _USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass  # already absent — idempotent
