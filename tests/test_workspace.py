"""Unit tests for the workspace download (urllib mocked, no network)."""

import io
import os
import stat
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


def test_readonly_leftover_does_not_block_refresh(monkeypatch, tmp_path):
    """The original wedge: a read-only file in a leftover backup must not stop
    the next update. It used to, because rmtree(ignore_errors=True) can't delete
    read-only files on Windows and the fixed-name backup rename then collided."""
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    workspace._etag_path(dest).write_text('"old-sha"')

    legacy_bak = dest.parent / (dest.name + ".bak")
    legacy_bak.mkdir()
    locked = legacy_bak / "pack.idx"
    locked.write_text("readonly")
    os.chmod(locked, stat.S_IREAD)

    bundle = _make_bundle({".claude/skills/x.md": b"fresh", "README.md": b"hi"})
    _patch_urlopen(monkeypatch, lambda req, timeout=0: _FakeResponse(bundle, '"new-sha"'))

    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")

    assert res.status == "downloaded"
    assert workspace._etag_path(dest).read_text() == '"new-sha"'
    assert (dest / ".claude" / "skills" / "x.md").read_text() == "fresh"
    assert not legacy_bak.exists()


def test_swap_completes_even_if_old_copy_is_undeletable(monkeypatch, tmp_path):
    """Robustness by construction: even when the retired copy can't be deleted
    (truly locked), the new bundle still lands and the etag advances."""
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    (dest / "old.txt").write_text("old")
    workspace._etag_path(dest).write_text('"old-sha"')
    monkeypatch.setattr(workspace, "_force_rmtree", lambda p: None)

    bundle = _make_bundle({".claude/x": b"y", "README.md": b"new"})
    _patch_urlopen(monkeypatch, lambda req, timeout=0: _FakeResponse(bundle, '"new-sha"'))

    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")

    assert res.status == "downloaded"
    assert workspace._etag_path(dest).read_text() == '"new-sha"'
    assert (dest / "README.md").read_text() == "new"
    assert not (dest / "old.txt").exists()


def test_sweep_removes_legacy_artifacts(tmp_path):
    dest = tmp_path / "ws"
    dest.mkdir()
    legacy_bak = dest.parent / (dest.name + ".bak")
    legacy_bak.mkdir()
    ro = legacy_bak / "pack.idx"
    ro.write_text("x")
    os.chmod(ro, stat.S_IREAD)
    orphan = dest.parent / ".mesea-ws-old-abc123"
    orphan.mkdir()

    workspace.sweep_stale_artifacts(dest)

    assert not legacy_bak.exists()
    assert not orphan.exists()
    # idempotent: a second sweep on a clean parent does nothing and never raises
    workspace.sweep_stale_artifacts(dest)


def test_result_exposes_commit_on_download(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    bundle = _make_bundle({".claude/x": b"y"})
    _patch_urlopen(monkeypatch, lambda req, timeout=0: _FakeResponse(bundle, '"abc1234"'))

    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")

    assert res.commit == "abc1234"


def test_skipped_fallback_carries_prior_commit(monkeypatch, tmp_path):
    """When a refresh fails but a copy is present, the result reports the commit
    still in use so the UI can show which (stale) version is live."""
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    workspace._etag_path(dest).write_text('"sha-old"')

    def boom(req, timeout=0):
        raise urllib.error.URLError("offline")

    _patch_urlopen(monkeypatch, boom)
    res = workspace.ensure_workspace(token="t", dest=dest, url="https://x/api")

    assert res.status == "skipped"
    assert res.commit == "sha-old"
