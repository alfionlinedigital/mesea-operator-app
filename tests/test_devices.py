"""Unit tests for the device-directory client (query build + parse + errors)."""

import io
import json
import urllib.error

import pytest

from mesea_operator import config, devices


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture_url(monkeypatch, body=b'{"data": []}'):
    """Patch urlopen to record the requested URL and return a canned body."""
    seen: dict = {}

    def fake_urlopen(req, *a, **k):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _Resp(body)

    monkeypatch.setattr(devices.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_fetch_devices_parses_data_list(monkeypatch):
    body = json.dumps({"data": [{"id": 1, "device_name": "Tab"}, {"id": 2}]}).encode()
    _capture_url(monkeypatch, body)
    result = devices.fetch_devices("msk_live_t")
    assert [d["id"] for d in result] == [1, 2]


def test_fetch_devices_sends_bearer_token(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("msk_live_t")
    assert seen["auth"] == "Bearer msk_live_t"


def test_fetch_devices_no_params_hits_base_url(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t")
    assert seen["url"] == config.DEVICES_URL
    assert "?" not in seen["url"]


def test_fetch_devices_builds_query_for_q_and_unassigned(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t", q="tab", unassigned=True)
    assert "q=tab" in seen["url"]
    assert "unassigned=true" in seen["url"]


def test_fetch_devices_builds_query_for_mdm(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t", mdm="scalefusion")
    assert "mdm=scalefusion" in seen["url"]


def test_fetch_devices_builds_query_for_all_filters(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t", q="tab", mdm="hexnode", unassigned=True)
    assert "q=tab" in seen["url"]
    assert "mdm=hexnode" in seen["url"]
    assert "unassigned=true" in seen["url"]


def test_fetch_devices_empty_mdm_omitted(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t", mdm="")
    assert "mdm=" not in seen["url"]
    assert "?" not in seen["url"]


def test_fetch_devices_returns_enrichment_fields(monkeypatch):
    body = json.dumps(
        {
            "data": [
                {
                    "id": 1,
                    "device_name": "Tab",
                    "business_name": "Le Sorelle",
                    "worker_name": "Bucătar",
                    "mdm_name": "Scalefusion",
                }
            ]
        }
    ).encode()
    _capture_url(monkeypatch, body)
    [d] = devices.fetch_devices("t")
    assert d["business_name"] == "Le Sorelle"
    assert d["worker_name"] == "Bucătar"
    assert d["mdm_name"] == "Scalefusion"


def test_fetch_devices_unassigned_false_is_explicit(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t", unassigned=False)
    assert "unassigned=false" in seen["url"]
    assert "q=" not in seen["url"]


def test_fetch_devices_respects_url_override(monkeypatch):
    seen = _capture_url(monkeypatch)
    devices.fetch_devices("t", q="x", url="https://staging.test/api/v1/devices")
    assert seen["url"].startswith("https://staging.test/api/v1/devices?")


def test_fetch_devices_tolerates_top_level_list(monkeypatch):
    _capture_url(monkeypatch, json.dumps([{"id": 9}]).encode())
    assert devices.fetch_devices("t") == [{"id": 9}]


def test_fetch_devices_filters_non_dict_entries(monkeypatch):
    _capture_url(monkeypatch, json.dumps({"data": [{"id": 1}, "junk", None]}).encode())
    assert devices.fetch_devices("t") == [{"id": 1}]


def test_fetch_devices_raises_on_http_error(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr(devices.urllib.request, "urlopen", boom)
    with pytest.raises(devices.DevicesError):
        devices.fetch_devices("t")


def test_fetch_devices_raises_on_network_error(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(devices.urllib.request, "urlopen", boom)
    with pytest.raises(devices.DevicesError):
        devices.fetch_devices("t")


def test_fetch_devices_raises_on_bad_json(monkeypatch):
    _capture_url(monkeypatch, b"{not json")
    with pytest.raises(devices.DevicesError):
        devices.fetch_devices("t")


def test_fetch_devices_raises_on_unexpected_shape(monkeypatch):
    _capture_url(monkeypatch, json.dumps({"data": {"id": 1}}).encode())
    with pytest.raises(devices.DevicesError):
        devices.fetch_devices("t")
