"""Unit tests for the Node bootstrap that keeps the Playwright MCP alive.

The failure this guards against is silent: with no Node on PATH the workspace's
`npx @playwright/mcp@latest` server never starts, and the demo-onboarding skill
drops to its degraded mode without anything erroring.
"""

import io
import tarfile
import zipfile

import pytest

from mesea_operator import node_runtime


@pytest.fixture(autouse=True)
def _private_dir(tmp_path, monkeypatch):
    """Point the private Node dir at a tmp dir for every test."""
    monkeypatch.setattr(node_runtime, "data_dir", lambda: tmp_path / "node")
    return tmp_path / "node"


def _make_posix_copy(root):
    """Lay out an extracted POSIX Node release."""
    bin_dir = root / "node-v22.11.0-linux-x64" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "node").write_text("#!/bin/sh\n")
    (bin_dir / "npx").write_text("#!/bin/sh\n")
    return bin_dir


def test_is_available_when_npx_on_path(monkeypatch):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: "/usr/bin/npx")
    assert node_runtime.is_available() is True


def test_is_available_via_private_copy(monkeypatch, _private_dir):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: None)
    _make_posix_copy(_private_dir)
    assert node_runtime.is_available() is True


def test_is_unavailable_with_neither(monkeypatch):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: None)
    assert node_runtime.is_available() is False


def test_ensure_is_a_noop_when_node_already_on_path(monkeypatch):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: "/usr/bin/npx")

    def explode(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("should not download when node is already present")

    monkeypatch.setattr(node_runtime.urllib.request, "urlopen", explode)

    result = node_runtime.ensure()

    assert result.status == "present"


def test_ensure_reuses_the_private_copy(monkeypatch, _private_dir):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: None)
    bin_dir = _make_posix_copy(_private_dir)

    def explode(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("should not re-download an existing copy")

    monkeypatch.setattr(node_runtime.urllib.request, "urlopen", explode)

    result = node_runtime.ensure()

    assert result.status == "present"
    assert result.bin_dir == bin_dir


def test_ensure_never_raises_when_the_download_fails(monkeypatch):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: None)

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(node_runtime.urllib.request, "urlopen", boom)

    result = node_runtime.ensure()

    # Degrades the Playwright steps; must never block login or the rest of a demo.
    assert result.status == "unavailable"
    assert "network down" in result.detail


def test_environ_with_node_leaves_an_existing_path_alone(monkeypatch):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: "/usr/bin/npx")

    env = node_runtime.environ_with_node({"PATH": "/usr/bin"})

    assert env["PATH"] == "/usr/bin"


def test_environ_with_node_prepends_the_private_copy(monkeypatch, _private_dir):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: None)
    bin_dir = _make_posix_copy(_private_dir)

    env = node_runtime.environ_with_node({"PATH": "/usr/bin"})

    assert env["PATH"].startswith(str(bin_dir))
    assert env["PATH"].endswith("/usr/bin")


def test_environ_with_node_is_a_passthrough_when_there_is_nothing(monkeypatch):
    monkeypatch.setattr(node_runtime.shutil, "which", lambda name: None)

    env = node_runtime.environ_with_node({"PATH": "/usr/bin"})

    assert env["PATH"] == "/usr/bin"


def test_extract_rejects_a_zip_entry_that_escapes_the_target(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "nope")

    with pytest.raises(ValueError, match="escapes the target directory"):
        node_runtime._extract(archive, tmp_path / "dest")


def test_extract_rejects_a_tar_entry_that_escapes_the_target(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    payload = b"nope"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("../escaped.txt")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="escapes the target directory"):
        node_runtime._extract(archive, tmp_path / "dest")


def test_archive_name_is_pinned_to_the_configured_version():
    name = node_runtime._archive_name()

    # Unsupported platforms return None rather than guessing a filename.
    if name is not None:
        assert node_runtime.NODE_VERSION in name
