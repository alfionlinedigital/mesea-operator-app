"""Unit tests for self-update version comparison + asset selection."""

import io

import pytest

from mesea_operator import updater


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("v0.2.0", "0.1.0", True),
        ("0.1.1", "0.1.0", True),
        ("v1.0.0", "0.9.9", True),
        ("0.1.0", "0.1.0", False),
        ("v0.1.0", "0.2.0", False),
        ("0.1", "0.1.0", False),
        ("1.2.3", "1.2.3", False),
        ("v2", "1.9.9", True),
    ],
)
def test_is_newer(latest, current, expected):
    assert updater.is_newer(latest, current) is expected


def test_parse_tolerates_v_prefix_and_garbage():
    assert updater._parse("v1.2.3") == (1, 2, 3)
    assert updater._parse("1.2.3-rc1") == (1, 2, 3)
    assert updater._parse("garbage") == (0,)


def test_check_for_update_handles_network_failure(monkeypatch):
    def boom(*_a, **_k):
        raise updater.urllib.error.URLError("offline")

    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    info = updater.check_for_update(repo="x/y", current="0.1.0")
    assert info.available is False
    assert "failed" in info.detail


def test_check_for_update_detects_newer(monkeypatch):
    import io
    import json

    payload = {
        "tag_name": "v0.9.0",
        "assets": [
            {"name": "mesea-operator-windows.exe", "browser_download_url": "http://w"},
            {"name": "mesea-operator-macos", "browser_download_url": "http://m"},
            {"name": "mesea-operator-linux", "browser_download_url": "http://l"},
        ],
    }

    class FakeResp(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResp(json.dumps(payload).encode()),
    )
    monkeypatch.setattr(updater, "_asset_suffix", lambda *a, **k: "linux")
    info = updater.check_for_update(repo="x/y", current="0.1.0")
    assert info.available is True
    assert info.latest_version == "v0.9.0"
    assert info.download_url == "http://l"


def _fake_release(monkeypatch, payload):
    import io
    import json

    class FakeResp(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResp(json.dumps(payload).encode()),
    )


def test_check_for_update_redirects_by_context(monkeypatch):
    """Installed → platform installer asset; portable → bare per-OS binary."""
    payload = {
        "tag_name": "v0.9.0",
        "assets": [
            {"name": "mesea-operator-windows.exe", "browser_download_url": "http://portable"},
            {"name": "mesea-operator-windows-setup.exe", "browser_download_url": "http://setup"},
        ],
    }
    _fake_release(monkeypatch, payload)
    monkeypatch.setattr(updater.sys, "platform", "win32")

    installed = updater.check_for_update(
        repo="x/y", current="0.1.0", context=updater.install_context.CONTEXT_INSTALLED
    )
    assert installed.download_url == "http://setup"
    assert installed.context == updater.install_context.CONTEXT_INSTALLED

    portable = updater.check_for_update(
        repo="x/y", current="0.1.0", context=updater.install_context.CONTEXT_PORTABLE
    )
    assert portable.download_url == "http://portable"
    assert portable.context == updater.install_context.CONTEXT_PORTABLE


class _Resp(io.BytesIO):
    """Fake urlopen response carrying headers (context-manager)."""

    def __init__(self, data=b"{}", headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_check_for_update_sends_if_none_match_when_etag_given(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["inm"] = req.get_header("If-none-match")
        return _Resp(b'{"tag_name": "v0.1.0"}', {"ETag": '"e2"'})

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    updater.check_for_update(repo="x/y", current="0.1.0", etag='"e1"')
    assert captured["inm"] == '"e1"'


def test_check_for_update_304_reports_not_modified(monkeypatch):
    def not_modified(*_a, **_k):
        raise updater.urllib.error.HTTPError("u", 304, "Not Modified", None, None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", not_modified)
    info = updater.check_for_update(repo="x/y", current="0.1.0", etag='"e1"')
    assert info.available is False
    assert info.not_modified is True
    assert info.etag == '"e1"'  # the cached etag is preserved for the next poll


def test_check_for_update_returns_new_etag(monkeypatch):
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *a, **k: _Resp(b'{"tag_name": "v0.1.0"}', {"ETag": '"e9"'}),
    )
    info = updater.check_for_update(repo="x/y", current="0.1.0")
    assert info.etag == '"e9"'
