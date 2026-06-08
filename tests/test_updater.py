"""Unit tests for self-update version comparison + asset selection."""

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
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda *a, **k: FakeResp(json.dumps(payload).encode()),
    )
    monkeypatch.setattr(updater, "_asset_suffix", lambda: "linux")
    info = updater.check_for_update(repo="x/y", current="0.1.0")
    assert info.available is True
    assert info.latest_version == "v0.9.0"
    assert info.download_url == "http://l"
