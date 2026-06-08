"""Encrypted-at-rest token storage via the OS credential store (keyring).

Windows → Credential Manager (DPAPI), macOS → Keychain, Linux → SecretService.
A single JSON blob (token + expiry + account label) is stored under one
keyring entry. The token value never leaves this module except when written
into the Claude settings bridge at launch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import keyring

from . import config

_USERNAME = "token"  # single per-machine operator credential


@dataclass
class StoredCredential:
    access_token: str
    expires_at: str | None
    account_label: str | None


def store(access_token: str, expires_at: str | None, account_label: str | None) -> None:
    blob = json.dumps(
        {
            "access_token": access_token,
            "expires_at": expires_at,
            "account_label": account_label,
        }
    )
    keyring.set_password(config.KEYRING_SERVICE, _USERNAME, blob)


def load() -> StoredCredential | None:
    raw = keyring.get_password(config.KEYRING_SERVICE, _USERNAME)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    token = data.get("access_token")
    if not token:
        return None
    return StoredCredential(
        access_token=token,
        expires_at=data.get("expires_at"),
        account_label=data.get("account_label"),
    )


def clear() -> None:
    try:
        keyring.delete_password(config.KEYRING_SERVICE, _USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass  # already absent — idempotent sign-out
