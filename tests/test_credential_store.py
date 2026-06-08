"""Unit tests for the keyring-backed credential store, using an in-memory backend."""

import keyring
import keyring.backend
import pytest

from mesea_operator import credential_store


class _MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self._store:
            raise keyring.errors.PasswordDeleteError("not set")
        del self._store[(service, username)]


@pytest.fixture(autouse=True)
def memory_backend():
    previous = keyring.get_keyring()
    keyring.set_keyring(_MemoryKeyring())
    yield
    keyring.set_keyring(previous)


def test_load_returns_none_when_empty():
    assert credential_store.load() is None


def test_store_then_load_round_trip():
    credential_store.store("msk_live_t", "2026-09-05T00:00:00+00:00", "Octav (AM)")
    cred = credential_store.load()
    assert cred is not None
    assert cred.access_token == "msk_live_t"
    assert cred.expires_at.startswith("2026-09-05")
    assert cred.account_label == "Octav (AM)"


def test_clear_removes_credential():
    credential_store.store("msk_live_t", None, None)
    credential_store.clear()
    assert credential_store.load() is None


def test_clear_is_idempotent():
    credential_store.clear()  # nothing stored — must not raise
    credential_store.clear()


def test_load_tolerates_corrupt_blob():
    keyring.set_password(credential_store.config.KEYRING_SERVICE, "token", "{not json")
    assert credential_store.load() is None
