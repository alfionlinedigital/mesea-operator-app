"""Unit tests for the direct API helpers (identity + revoke), server stubbed."""

import io
import json
import urllib.error

from mesea_operator import api


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_identity_reads_token_name(monkeypatch):
    body = json.dumps({"data": {"token_name": "Octav (AM)", "app_name": "Mesea"}}).encode()
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    assert api.fetch_identity("msk_live_t") == "Octav (AM)"


def test_fetch_identity_falls_back_to_app_name(monkeypatch):
    body = json.dumps({"data": {"app_name": "Mesea"}}).encode()
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    assert api.fetch_identity("t") == "Mesea"


def test_fetch_identity_returns_none_on_error(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(api.urllib.request, "urlopen", boom)
    assert api.fetch_identity("t") is None


def test_is_token_valid_true_on_2xx(monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda *a, **k: _Resp(b"{}"))
    assert api.is_token_valid("msk_live_t") is True


def test_is_token_valid_false_on_none_token():
    assert api.is_token_valid(None) is False
    assert api.is_token_valid("") is False


def test_is_token_valid_false_on_401(monkeypatch):
    def unauthorized(*_a, **_k):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr(api.urllib.request, "urlopen", unauthorized)
    assert api.is_token_valid("expired") is False


def test_is_token_valid_false_on_network_error(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(api.urllib.request, "urlopen", boom)
    assert api.is_token_valid("t") is False


def test_revoke_success(monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda *a, **k: _Resp(b"{}"))
    assert api.revoke("t") is True


def test_revoke_network_failure_returns_false(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(api.urllib.request, "urlopen", boom)
    assert api.revoke("t") is False
