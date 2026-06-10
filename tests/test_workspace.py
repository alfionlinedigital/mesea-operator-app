"""Unit tests for the workspace download (urllib mocked, no network)."""

import io
import tarfile
import urllib.error

from mesea_operator import workspace


def _make_bundle(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes, etag: str = "") -> None:
        self._data = data
        self.headers = {"ETag": etag}

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


def _patch_urlopen(monkeypatch, handler):
    monkeypatch.setattr(workspace.urllib.request, "urlopen", handler)


def test_error_when_no_token_and_no_existing(tmp_path):
    res = workspace.ensure_workspace(token=None, dest=tmp_path / "ws")
    assert res.status == "error"


def test_skipped_when_no_token_but_workspace_present(tmp_path):
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    res = workspace.ensure_workspace(token=None, dest=dest)
    assert res.status == "skipped"


def test_download_extracts_bundle_and_writes_etag(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    bundle = _make_bundle({".claude/skills/x.md": b"hello", "README.md": b"hi"})
    _patch_urlopen(monkeypatch, lambda req, timeout=0: _FakeResponse(bundle, '"abc123"'))

    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")

    assert res.status == "downloaded"
    assert (dest / ".claude" / "skills" / "x.md").read_text() == "hello"
    assert workspace._etag_path(dest).read_text() == '"abc123"'


def test_up_to_date_on_304(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    workspace._etag_path(dest).write_text('"abc123"')

    def not_modified(req, timeout=0):
        raise urllib.error.HTTPError("https://x", 304, "Not Modified", None, None)

    _patch_urlopen(monkeypatch, not_modified)
    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")
    assert res.status == "up-to-date"


def test_sends_if_none_match_when_etag_cached(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    workspace._etag_path(dest).write_text('"sha1"')
    captured = {}

    def capture(req, timeout=0):
        captured["inm"] = req.get_header("If-none-match")
        return _FakeResponse(_make_bundle({".claude/x": b"y"}), '"sha2"')

    _patch_urlopen(monkeypatch, capture)
    workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")
    assert captured["inm"] == '"sha1"'


def test_skipped_on_network_error_when_present(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)

    def boom(req, timeout=0):
        raise urllib.error.URLError("offline")

    _patch_urlopen(monkeypatch, boom)
    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")
    assert res.status == "skipped"


def test_error_on_network_error_when_absent(monkeypatch, tmp_path):
    dest = tmp_path / "ws"

    def boom(req, timeout=0):
        raise urllib.error.URLError("offline")

    _patch_urlopen(monkeypatch, boom)
    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")
    assert res.status == "error"


def test_rejects_path_traversal_member(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    evil = _make_bundle({"../escape.md": b"x"})
    _patch_urlopen(monkeypatch, lambda req, timeout=0: _FakeResponse(evil, '"e"'))

    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")

    assert res.status == "error"
    assert not (tmp_path / "escape.md").exists()
    assert not dest.exists()
