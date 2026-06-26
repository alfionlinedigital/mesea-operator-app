"""Materialise the mesea-operator account-manager workspace locally.

The workspace repo is private; account managers never get GitHub access.
Instead the Mesea backend serves it as a gzipped tar at
``/api/v1/operator-workspace``, gated by the operator OAuth token. We cache the
last ETag (the repo commit SHA) next to the workspace so repeat launches send
``If-None-Match`` and skip re-downloading an unchanged bundle.

Returns a typed result so the UI can report downloaded/up-to-date/skipped/error
without raising on a transient network failure (a present-but-stale workspace
is still launchable).
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import config

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceResult:
    path: Path
    status: str  # "downloaded" | "up-to-date" | "skipped" | "error"
    detail: str = ""
    commit: str | None = None  # resolved workspace commit (ETag), for display


def default_workspace_dir() -> Path:
    return Path.home() / "mesea-operator"


def _etag_path(dest: Path) -> Path:
    return dest.parent / (dest.name + ".etag")


def _is_present(dest: Path) -> bool:
    return (dest / ".claude").exists()


def ensure_workspace(
    token: str | None,
    dest: Path | None = None,
    url: str | None = None,
) -> WorkspaceResult:
    """Download (or refresh) the workspace bundle into ``dest``.

    ``token`` is the operator OAuth access token. Without it we cannot fetch the
    private bundle: reuse an existing copy if present, else report an error.
    """
    dest = dest or default_workspace_dir()
    url = url or config.WORKSPACE_URL
    sweep_stale_artifacts(dest)

    if not token:
        if _is_present(dest):
            return WorkspaceResult(dest, "skipped", "not signed in; using existing workspace")
        return WorkspaceResult(dest, "error", "sign in required to download the workspace")

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/gzip"}
    prior_etag = _read_prior_etag(dest)
    if prior_etag:
        headers["If-None-Match"] = prior_etag

    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=120
        ) as resp:
            data = resp.read()
            etag = resp.headers.get("ETag", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            commit = _strip_etag(prior_etag)
            logger.info("workspace up to date (%s)", commit)
            return WorkspaceResult(dest, "up-to-date", commit=commit)
        return _fallback(dest, f"download failed (HTTP {exc.code})")
    except urllib.error.URLError as exc:
        return _fallback(dest, f"network error: {exc.reason}")

    try:
        _apply_bundle_in_place(data, dest)
    except (tarfile.TarError, OSError) as exc:
        return _fallback(dest, f"apply failed: {exc}")

    if etag:
        _etag_path(dest).write_text(etag)
    commit = _strip_etag(etag)
    logger.info("workspace updated to %s", commit)
    return WorkspaceResult(dest, "downloaded", commit=commit)


def _read_prior_etag(dest: Path) -> str | None:
    etag_file = _etag_path(dest)
    if not _is_present(dest) or not etag_file.exists():
        return None
    value = etag_file.read_text().strip()
    return value or None


def _strip_etag(etag: str | None) -> str | None:
    """Bare commit SHA from an ETag header value (strips the surrounding quotes)."""
    return etag.strip('"') if etag else None


def _fallback(dest: Path, detail: str) -> WorkspaceResult:
    """Present-but-stale is still launchable; only hard-fail with nothing there.

    Carries the commit still on disk so the UI can name the stale version in use.
    """
    if _is_present(dest):
        logger.warning("workspace refresh skipped (%s); using existing copy", detail)
        return WorkspaceResult(
            dest, "skipped", f"{detail}; using existing", commit=_strip_etag(_read_prior_etag(dest))
        )
    logger.error("workspace unavailable: %s", detail)
    return WorkspaceResult(dest, "error", detail)


def sweep_stale_artifacts(dest: Path) -> None:
    """Remove orphaned artifacts from older builds so they can't accumulate.

    Earlier versions swapped the workspace by renaming it aside to ``<name>.bak``
    or ``.mesea-ws-*`` temp dirs; in-place updates create neither, so any such
    leftovers are pure orphans (a read-only git pack inside one could even
    survive cleanup). Best-effort and idempotent; never raises.
    """
    parent = dest.parent
    if not parent.exists():
        return
    legacy_bak = parent / (dest.name + ".bak")
    if legacy_bak.exists():
        _force_rmtree(legacy_bak)
    for orphan in parent.glob(".mesea-ws-*"):
        _force_rmtree(orphan)


def _apply_bundle_in_place(tar_gz: bytes, dest: Path) -> None:
    """Write the bundle's files INTO ``dest`` without renaming the live dir.

    The workspace is a running Claude session's working directory, so on Windows
    it can't be renamed (the old swap approach failed there) — but writing files
    inside it is fine. Each file is written atomically (temp + ``os.replace``).
    Files a prior bundle delivered but this one drops are pruned via a manifest,
    so user runtime artifacts (``.tmp``, screenshots, …) are preserved while
    removed tracked files don't linger.
    """
    with tarfile.open(fileobj=io.BytesIO(tar_gz), mode="r:gz") as tar:
        members = _safe_file_members(tar)  # validates every path before any write
        dest.mkdir(parents=True, exist_ok=True)
        new_paths: set[str] = set()
        for member in members:
            new_paths.add(member.name)
            target = dest / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            _atomic_write(target, source.read() if source else b"")
    _prune_removed_files(dest, new_paths)
    _write_manifest(dest, new_paths)


def _safe_file_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Regular-file members whose path stays inside the destination.

    Directory/symlink/special members are skipped — parents are created from the
    file paths — and an absolute or ``..``-escaping path is rejected outright
    (defence in depth; the bundle is produced by our own backend).
    """
    safe: list[tarfile.TarInfo] = []
    for member in tar.getmembers():
        if not member.isfile():
            continue
        rel = PurePosixPath(member.name)
        if rel.is_absolute() or ".." in rel.parts:
            raise tarfile.TarError(f"unsafe path in archive: {member.name}")
        safe.append(member)
    return safe


def _atomic_write(target: Path, data: bytes) -> None:
    """Replace ``target`` atomically: write a sibling temp, then ``os.replace``."""
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def _manifest_path(dest: Path) -> Path:
    return dest.parent / (dest.name + ".manifest")


def _read_manifest(dest: Path) -> set[str]:
    manifest = _manifest_path(dest)
    if not manifest.exists():
        return set()
    return {line for line in manifest.read_text().splitlines() if line}


def _write_manifest(dest: Path, paths: set[str]) -> None:
    _manifest_path(dest).write_text("\n".join(sorted(paths)) + "\n")


def _prune_removed_files(dest: Path, new_paths: set[str]) -> None:
    """Delete files the previous bundle delivered but this one omits — and ONLY
    those (tracked via the manifest), so user runtime artifacts are untouched.
    """
    for rel in _read_manifest(dest) - new_paths:
        stale = dest / rel
        if stale.is_file():
            _force_unlink(stale)


def _force_unlink(path: Path) -> None:
    """Best-effort file delete, clearing a read-only bit first (Windows)."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    try:
        path.unlink()
    except OSError:
        pass


def _force_rmtree(path: Path) -> None:
    """Recursively delete ``path``, clearing read-only bits that defeat
    ``shutil.rmtree`` on Windows (git marks pack objects read-only). A file held
    by a live handle is left behind rather than raising — best-effort cleanup.
    """
    if not path.exists():
        return

    def _on_error(func, target, _exc):  # shutil onexc/onerror callback
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_error)
    else:
        shutil.rmtree(path, onerror=_on_error)
