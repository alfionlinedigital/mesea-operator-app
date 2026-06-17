"""Unit tests for the keyring-backed demo-device store, in-memory backend."""

import keyring
import keyring.backend
import pytest

from mesea_operator import device_store


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


def test_load_returns_empty_when_unset():
    chosen = device_store.load()
    assert chosen.tablet_id is None
    assert chosen.phone_id is None


def test_store_then_load_round_trip():
    device_store.store("dev-tab", "dev-phone")
    chosen = device_store.load()
    assert chosen.tablet_id == "dev-tab"
    assert chosen.phone_id == "dev-phone"


def test_store_allows_partial_selection():
    device_store.store("dev-tab", None)
    chosen = device_store.load()
    assert chosen.tablet_id == "dev-tab"
    assert chosen.phone_id is None


def test_clear_removes_selection():
    device_store.store("dev-tab", "dev-phone")
    device_store.clear()
    assert device_store.load().tablet_id is None


def test_clear_is_idempotent():
    device_store.clear()  # nothing stored — must not raise
    device_store.clear()


def test_load_tolerates_corrupt_blob():
    keyring.set_password(device_store.config.KEYRING_SERVICE, "demo-devices", "{bad")
    assert device_store.load().tablet_id is None
