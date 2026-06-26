"""Tests for optional Bugsink/Sentry error reporting (no real SDK needed)."""

import sys
import types

from mesea_operator import errors


def test_init_no_dsn_disables(monkeypatch):
    monkeypatch.setattr(errors.config, "BUGSINK_DSN", "")
    assert errors.init_error_reporting("0.0.0") is False


def test_init_with_dsn_calls_sentry(monkeypatch):
    calls = {}
    fake_sdk = types.SimpleNamespace(init=lambda **kw: calls.update(kw))
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
    monkeypatch.setattr(errors.config, "BUGSINK_DSN", "https://key@bugsink.example/1")

    assert errors.init_error_reporting("1.2.3") is True
    assert calls["dsn"] == "https://key@bugsink.example/1"
    assert calls["release"] == "mesea-operator@1.2.3"


def test_init_swallows_sentry_failure(monkeypatch):
    def boom(**_kw):
        raise RuntimeError("bad dsn")

    monkeypatch.setitem(sys.modules, "sentry_sdk", types.SimpleNamespace(init=boom))
    monkeypatch.setattr(errors.config, "BUGSINK_DSN", "https://key@bugsink.example/1")
    # A failing init must never propagate — reporting is best-effort.
    assert errors.init_error_reporting("1.2.3") is False
