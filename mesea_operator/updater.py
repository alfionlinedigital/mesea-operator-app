"""Self-update check against this app's GitHub releases.

Compares the running version to the latest release tag and reports whether a
newer build is available, plus the per-OS asset download URL. The asset is
chosen by *install context* (see ``install_context``): an installed copy is
redirected to the platform installer (Inno ``.exe`` / ``.dmg`` / ``.deb``), a
portable copy to the bare per-OS binary it can swap in place. Downloading and
swapping the running exe is the UI's job; this module is pure logic + one
GitHub API call, so the version comparison is unit-testable offline.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import __version__, config, install_context


def _parse(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("vV")
    parts = []
    for chunk in cleaned.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """True if `latest` is a strictly higher version than `current`."""
    a, b = _parse(latest), _parse(current)
    length = max(len(a), len(b))
    a += (0,) * (length - len(a))
    b += (0,) * (length - len(b))
    return a > b


def _asset_suffix(context: str | None = None) -> str:
    context = context or install_context.detect_context()
    return install_context.asset_suffix(context, sys.platform)


@dataclass
class UpdateInfo:
    available: bool
    latest_version: str
    download_url: str | None
    detail: str = ""
    context: str = ""


def check_for_update(
    repo: str | None = None,
    current: str | None = None,
    context: str | None = None,
) -> UpdateInfo:
    repo = repo or config.SELF_UPDATE_REPO
    current = current or __version__
    context = context or install_context.detect_context()
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as exc:
        return UpdateInfo(False, current, None, f"update check failed: {exc}", context)

    latest = data.get("tag_name", "")
    if not latest or not is_newer(latest, current):
        return UpdateInfo(False, latest or current, None, "", context)

    suffix = _asset_suffix(context)
    download_url = None
    for asset in data.get("assets", []):
        if asset.get("name", "").endswith(suffix):
            download_url = asset.get("browser_download_url")
            break
    return UpdateInfo(True, latest, download_url, "", context)
