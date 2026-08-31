"""Guarantee a Node.js runtime for the workspace's Playwright MCP server.

The operator workspace's ``.mcp.json`` starts Playwright with
``npx @playwright/mcp@latest``. Without Node on PATH that server simply never
comes up: Claude Code reports the MCP as failed and the ``demo-onboarding``
skill silently falls back to its degraded mode, so the account manager ends up
eyeballing brand colours from a pasted screenshot instead of sampling them.
Nothing crashes — the demo is just quietly worse, which is the hardest kind of
failure to notice.

So the launcher owns Node the same way it owns the workspace bundle: check for
it, fetch it if missing, and hand it to the child process on PATH.

Placement rules:
  * A Node already on PATH always wins — we never shadow the AM's own install.
  * Otherwise we use a private copy under the user data dir. It is per-user, so
    no elevation is needed, and it is invisible to the rest of the system.

The Windows installer calls this at install time (``--ensure-node``); the .deb
declares a ``nodejs`` dependency so apt does it; macOS .dmg and the portable
builds have no install step, so the first launch bootstraps. Every path lands
on the same directory, so a later launch just finds it.

Tk-free and importable on headless machines, like every module outside ``ui``.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

logger = logging.getLogger(__name__)

# Pinned LTS. Bumping is a deliberate act — a floating "latest" would silently
# change the runtime under the AM between two launches of the same app build.
NODE_VERSION = os.environ.get("MESEA_NODE_VERSION", "22.11.0")
NODE_BASE_URL = os.environ.get("MESEA_NODE_BASE_URL", "https://nodejs.org/dist")

DOWNLOAD_TIMEOUT_SECONDS = 180


@dataclass
class NodeResult:
    status: str  # "present" | "installed" | "unavailable"
    bin_dir: Path | None = None
    detail: str = ""


def data_dir() -> Path:
    """Per-user directory holding the private Node copy."""
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "MeseaOperator" / "node"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MeseaOperator" / "node"
    return Path.home() / ".local" / "share" / "mesea-operator" / "node"


def _archive_name() -> str | None:
    """Official Node distribution filename for this platform, or None."""
    machine = (os.uname().machine if hasattr(os, "uname") else os.environ.get("PROCESSOR_ARCHITECTURE", "")).lower()
    if sys.platform.startswith("win"):
        arch = "arm64" if "arm" in machine else "x64"
        return f"node-v{NODE_VERSION}-win-{arch}.zip"
    if sys.platform == "darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        return f"node-v{NODE_VERSION}-darwin-{arch}.tar.gz"
    if sys.platform.startswith("linux"):
        arch = "arm64" if machine in ("aarch64", "arm64") else "x64"
        return f"node-v{NODE_VERSION}-linux-{arch}.tar.gz"
    return None


def _bundled_bin_dir() -> Path | None:
    """The bin directory inside our private copy, if it is actually there."""
    root = data_dir()
    if not root.exists():
        return None
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        # Windows ships node.exe at the archive root; POSIX under bin/.
        for candidate in (child / "bin", child):
            if (candidate / "node").exists() or (candidate / "node.exe").exists():
                return candidate
    return None


def is_available() -> bool:
    """True when npx can be resolved — from PATH or our private copy."""
    if shutil.which("npx") is not None:
        return True
    return _bundled_bin_dir() is not None


def environ_with_node(base: dict[str, str] | None = None) -> dict[str, str]:
    """A copy of the environment with the private Node bin dir on PATH.

    A Node already on PATH is left alone: we append nothing and shadow nothing.
    """
    env = dict(base if base is not None else os.environ)
    if shutil.which("npx") is not None:
        return env
    bin_dir = _bundled_bin_dir()
    if bin_dir is None:
        return env
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return env


def ensure(force: bool = False) -> NodeResult:
    """Make Node available, downloading it only when it genuinely is not.

    Never raises: a failed bootstrap must degrade the Playwright steps, never
    block the AM from logging in and running everything else.
    """
    if not force and shutil.which("npx") is not None:
        return NodeResult("present", None, "node already on PATH")

    existing = _bundled_bin_dir()
    if existing is not None and not force:
        return NodeResult("present", existing, "using the launcher's Node copy")

    archive = _archive_name()
    if archive is None:
        return NodeResult("unavailable", None, f"unsupported platform: {sys.platform}")

    url = f"{NODE_BASE_URL}/v{NODE_VERSION}/{archive}"
    target = data_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory() as tmp:
            local = Path(tmp) / archive
            logger.info("Downloading Node %s from %s", NODE_VERSION, url)
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
                local.write_bytes(resp.read())
            _extract(local, target)
    except Exception as exc:  # noqa: BLE001 - bootstrap must never be fatal
        logger.warning("Node bootstrap failed: %s", exc)
        return NodeResult("unavailable", None, str(exc))

    bin_dir = _bundled_bin_dir()
    if bin_dir is None:
        return NodeResult("unavailable", None, "archive extracted but no node binary found")
    logger.info("Node %s installed at %s", NODE_VERSION, bin_dir)
    return NodeResult("installed", bin_dir, f"Node {NODE_VERSION}")


def _extract(archive: Path, dest: Path) -> None:
    """Extract a Node release archive, refusing entries that escape ``dest``."""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            _assert_contained(zf.namelist(), dest)
            zf.extractall(dest)
        return
    with tarfile.open(archive, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile() or m.isdir() or m.issym()]
        _assert_contained([m.name for m in members], dest)
        tf.extractall(dest, members=members)
    # tarfile drops the exec bit on some platforms; restore it for the binaries.
    bin_dir = _bundled_bin_dir()
    if bin_dir is not None:
        for entry in bin_dir.iterdir():
            if entry.is_file():
                entry.chmod(entry.stat().st_mode | 0o111)


def _assert_contained(names: list[str], dest: Path) -> None:
    root = dest.resolve()
    for name in names:
        resolved = (dest / name).resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"archive entry escapes the target directory: {name}")
