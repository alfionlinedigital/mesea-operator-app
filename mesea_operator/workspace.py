"""Keep the mesea-operator AM workspace cloned and up to date.

Uses git when available (clone on first run, fast-forward pull thereafter).
Returns a typed result so the UI can report dispatched/updated/skipped/error
without raising on a transient network failure (a stale-but-present workspace
is still usable).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class WorkspaceResult:
    path: Path
    status: str  # "cloned" | "updated" | "skipped" | "error"
    detail: str = ""


def default_workspace_dir() -> Path:
    return Path.home() / "mesea-operator"


def ensure_workspace(dest: Path | None = None, repo_url: str | None = None) -> WorkspaceResult:
    dest = dest or default_workspace_dir()
    repo_url = repo_url or config.OPERATOR_REPO

    git = shutil.which("git")
    if not git:
        if (dest / ".claude").exists():
            return WorkspaceResult(dest, "skipped", "git not found; using existing workspace")
        return WorkspaceResult(dest, "error", "git not found and no existing workspace")

    try:
        if (dest / ".git").exists():
            subprocess.run(
                [git, "-C", str(dest), "pull", "--ff-only"],
                check=True, capture_output=True, text=True, timeout=120,
            )
            return WorkspaceResult(dest, "updated")
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [git, "clone", "--depth", "1", repo_url, str(dest)],
            check=True, capture_output=True, text=True, timeout=180,
        )
        return WorkspaceResult(dest, "cloned")
    except subprocess.CalledProcessError as exc:
        # Present-but-stale is still launchable; only hard-fail if nothing's there.
        if (dest / ".claude").exists():
            return WorkspaceResult(dest, "skipped", f"update failed, using existing: {exc.stderr.strip()}")
        return WorkspaceResult(dest, "error", exc.stderr.strip() or str(exc))
    except subprocess.TimeoutExpired:
        if (dest / ".claude").exists():
            return WorkspaceResult(dest, "skipped", "update timed out, using existing")
        return WorkspaceResult(dest, "error", "clone timed out")
