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
import shutil
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
            return WorkspaceResult(dest, "up-to-date")
        return _fallback(dest, f"download failed (HTTP {exc.code})")
    except urllib.error.URLError as exc:
        return _fallback(dest, f"network error: {exc.reason}")

    try:
        _extract_atomically(data, dest)
    except (tarfile.TarError, OSError) as exc:
        return _fallback(dest, f"extract failed: {exc}")

    if etag:
        _etag_path(dest).write_text(etag)
    return WorkspaceResult(dest, "downloaded")


def _read_prior_etag(dest: Path) -> str | None:
    etag_file = _etag_path(dest)
    if not _is_present(dest) or not etag_file.exists():
        return None
    value = etag_file.read_text().strip()
    return value or None


def _fallback(dest: Path, detail: str) -> WorkspaceResult:
    """Present-but-stale is still launchable; only hard-fail with nothing there."""
    if _is_present(dest):
        return WorkspaceResult(dest, "skipped", f"{detail}; using existing")
    return WorkspaceResult(dest, "error", detail)


def _extract_atomically(tar_gz: bytes, dest: Path) -> None:
    """Extract into a sibling staging dir, then swap it into place."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".mesea-ws-", dir=str(dest.parent)))
    backup = dest.parent / (dest.name + ".bak")
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_gz), mode="r:gz") as tar:
            _safe_extractall(tar, staging)
        if dest.exists():
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            dest.rename(backup)
        staging.rename(dest)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def _safe_extractall(tar: tarfile.TarFile, dest: Path) -> None:
    """Reject path-traversal members before extracting (defence in depth — the
    archive is produced by our own backend, but never trust tar member paths)."""
    dest_root = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if target != dest_root and dest_root not in target.parents:
            raise tarfile.TarError(f"unsafe path in archive: {member.name}")
    tar.extractall(dest)  # noqa: S202 — members validated above
