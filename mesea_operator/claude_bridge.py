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


def _scrub_keys(path: Path, keys: tuple[str, ...]) -> None:
    """Remove the given keys from the settings ``env`` block. Idempotent."""
    if not path.exists():
        return
    data = _read(path)
    env = data.get("env")
    if not isinstance(env, dict):
        return
    changed = False
    for key in keys:
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


def scrub_token(path: Path) -> None:
    """Remove the operator token (and MCP url) from settings. Idempotent."""
    _scrub_keys(path, (config.TOKEN_ENV_VAR, config.MCP_URL_ENV_VAR))


def write_demo_devices(path: Path, tablet_id: str | None, phone_id: str | None) -> None:
    """Merge the chosen demo device IDs into the settings ``env`` block.

    A ``None``/empty id removes that single key (e.g. only a tablet is picked),
    so the env never carries a stale half of the pair. Other keys are preserved.
    """
    data = _read(path)
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
    for key, value in (
        (config.DEMO_TABLET_ENV_VAR, tablet_id),
        (config.DEMO_PHONE_ENV_VAR, phone_id),
    ):
        if value:
            env[key] = value
        else:
            env.pop(key, None)
    if env:
        data["env"] = env
    else:
        data.pop("env", None)
    _write(path, data)


def scrub_demo_devices(path: Path) -> None:
    """Remove both demo device-ID keys from settings. Idempotent."""
    _scrub_keys(path, (config.DEMO_TABLET_ENV_VAR, config.DEMO_PHONE_ENV_VAR))


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


def launch_claude(
    executable: str, workspace_dir: str, resume: bool = False
) -> subprocess.Popen:
    """Start Claude Code with the operator workspace as its project root.

    Claude Code resolves ``.mcp.json``, ``.claude/settings.json`` and ``CLAUDE.md``
    relative to its working directory, so the workspace is handed over as the child
    ``cwd`` — never as a positional argument. A positional arg is read by the CLI as
    the initial *prompt* (it would leak the folder path into the chat), and without
    an explicit ``cwd`` the child inherits the launcher's own install dir as the
    project root — leaving the workspace's ``mesea`` MCP server unloaded. Returns the
    Popen so the launcher can wait for exit and then scrub the token.

    With ``resume=True`` the CLI is started with ``--resume``, which lists the
    workspace's prior conversations so the AM can pick one to continue. Sessions
    are stored per-project, so running it in the same ``cwd`` surfaces exactly the
    operator-workspace history and nothing else.
    """
    argv = [executable, "--resume"] if resume else [executable]
    return subprocess.Popen(argv, cwd=workspace_dir)
