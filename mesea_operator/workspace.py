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
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import config


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
            return WorkspaceResult(dest, "up-to-date", commit=_strip_etag(prior_etag))
        return _fallback(dest, f"download failed (HTTP {exc.code})")
    except urllib.error.URLError as exc:
        return _fallback(dest, f"network error: {exc.reason}")

    try:
        _extract_atomically(data, dest)
    except (tarfile.TarError, OSError) as exc:
        return _fallback(dest, f"extract failed: {exc}")

    if etag:
        _etag_path(dest).write_text(etag)
    return WorkspaceResult(dest, "downloaded", commit=_strip_etag(etag))


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
        return WorkspaceResult(
            dest, "skipped", f"{detail}; using existing", commit=_strip_etag(_read_prior_etag(dest))
        )
    return WorkspaceResult(dest, "error", detail)


def sweep_stale_artifacts(dest: Path) -> None:
    """Remove orphaned update artifacts so a stuck leftover can't wedge updates.

    Targets the legacy fixed-name backup (``<name>.bak`` written by older builds —
    a read-only git pack inside it could survive cleanup and block every later
    swap) and any abandoned ``.mesea-ws-old-*`` retired dirs from interrupted
    runs. Active ``.mesea-ws-new-*`` staging dirs are left alone. Best-effort and
    idempotent; never raises.
    """
    parent = dest.parent
    if not parent.exists():
        return
    legacy_bak = parent / (dest.name + ".bak")
    if legacy_bak.exists():
        _force_rmtree(legacy_bak)
    for orphan in parent.glob(".mesea-ws-old-*"):
        _force_rmtree(orphan)


def _extract_atomically(tar_gz: bytes, dest: Path) -> None:
    """Extract into a sibling staging dir, then swap it into place.

    The swap never depends on deleting the old copy: the previous workspace is
    renamed to a UNIQUE throwaway dir, so an undeletable leftover (e.g. a
    read-only git pack on Windows) can't block the rename and wedge future
    updates. Cleanup of the staging/retired dirs is best-effort.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".mesea-ws-new-", dir=str(dest.parent)))
    retired: Path | None = None
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_gz), mode="r:gz") as tar:
            _safe_extractall(tar, staging)
        if dest.exists():
            retired = _reserve_unique_dir(dest.parent, ".mesea-ws-old-")
            dest.rename(retired)
        staging.rename(dest)
    finally:
        _force_rmtree(staging)
        if retired is not None:
            _force_rmtree(retired)


def _reserve_unique_dir(parent: Path, prefix: str) -> Path:
    """A unique, currently-free path in ``parent``.

    ``mkdtemp`` reserves a unique name atomically; we drop the empty dir so the
    following ``rename`` onto it succeeds on Windows (which refuses to rename onto
    an existing directory). Single-writer, so the reserve→rename gap is safe.
    """
    reserved = Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))
    reserved.rmdir()
    return reserved


def _force_rmtree(path: Path) -> None:
    """Recursively delete ``path``, clearing read-only bits that defeat
    ``shutil.rmtree`` on Windows (git marks pack objects read-only). A file held
    by a live handle is left behind rather than raising — unique retire names mean
    a survivor can never block a future swap.
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


def _safe_extractall(tar: tarfile.TarFile, dest: Path) -> None:
    """Reject path-traversal members before extracting (defence in depth — the
    archive is produced by our own backend, but never trust tar member paths)."""
    dest_root = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if target != dest_root and dest_root not in target.parents:
            raise tarfile.TarError(f"unsafe path in archive: {member.name}")
    tar.extractall(dest)  # noqa: S202 — members validated above
