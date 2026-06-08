"""Bridge the operator token into Claude Code and launch the desktop app.

The Claude desktop app has no documented per-launch env injection, so the
only supported channel is the ``env`` block of ``~/.claude/settings.json``.
We therefore write the token there just before launch and **scrub it on
exit**. ``scrub_token`` is idempotent, and the launcher also scrubs at
startup, so a crash that skips the post-exit scrub is cleaned up on the next
run (no token lingers across sessions beyond one crash window).

All JSON functions take an explicit path and are unit-testable without Tk or
a real Claude install.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_token(path: Path, token: str, mcp_url: str | None = None) -> None:
    """Merge the token into the settings ``env`` block, preserving other keys."""
    data = _read(path)
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
    env[config.TOKEN_ENV_VAR] = token
    if mcp_url:
        env[config.MCP_URL_ENV_VAR] = mcp_url
    data["env"] = env
    _write(path, data)


def scrub_token(path: Path) -> None:
    """Remove the operator token (and MCP url) from settings. Idempotent."""
    if not path.exists():
        return
    data = _read(path)
    env = data.get("env")
    if not isinstance(env, dict):
        return
    changed = False
    for key in (config.TOKEN_ENV_VAR, config.MCP_URL_ENV_VAR):
        if key in env:
            del env[key]
            changed = True
    if not changed:
        return
    if env:
        data["env"] = env
    else:
        data.pop("env", None)
    _write(path, data)


def find_claude_executable() -> str | None:
    """Best-effort discovery of the Claude desktop executable per OS.

    Returns a path/command or None if not found (the UI then tells the user
    to open Claude manually — the token is already staged in settings.json).
    """
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA", "")
        program = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        candidates += [
            Path(local) / "Programs" / "Claude" / "Claude.exe",
            Path(program) / "Claude" / "Claude.exe",
        ]
    elif sys.platform == "darwin":
        candidates += [Path("/Applications/Claude.app/Contents/MacOS/Claude")]
    else:  # linux/debian
        for name in ("claude", "claude-desktop", "Claude"):
            found = shutil.which(name)
            if found:
                return found
        candidates += [Path.home() / ".local" / "bin" / "claude"]
    for c in candidates:
        if c.exists():
            return str(c)
    # Fall back to a PATH lookup (works if the CLI is installed).
    return shutil.which("claude")


def launch_claude(executable: str, workspace_dir: str) -> subprocess.Popen:
    """Start the Claude app/CLI pointed at the workspace folder, detached.

    The folder argument is best-effort; if the desktop app ignores it the
    user picks the folder once and Claude remembers it. Returns the Popen so
    the launcher can wait for exit to trigger the scrub.
    """
    return subprocess.Popen([executable, workspace_dir])
