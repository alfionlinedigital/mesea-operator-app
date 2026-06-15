"""Decide whether this build is the *installed* copy or a *portable* binary.

Update redirection hinges on it: an installed copy should fetch the platform
**installer** (Inno ``.exe`` / ``.dmg`` / ``.deb``) so the user re-runs the same
managed install; a portable binary should fetch the bare per-OS **executable**
it can swap in place. Detection is pure — it takes the running exe path, the
platform string, and (on Windows) the installer's registry footprint as inputs —
so it is unit-testable offline on any host OS.

Per-platform heuristics (frozen builds only; an unfrozen ``python -m`` dev run
is always treated as portable):

* **Windows** — the Inno Setup installer (see ``packaging/windows/installer.iss``)
  writes a per-user uninstall registry key whose ``InstallLocation`` is the
  install directory. If the running exe lives under that directory we are the
  installed copy. Fallback: an exe under ``Program Files`` or in a folder named
  like the app.
* **macOS** — the installer ships a ``.app`` bundle (exe at
  ``…/Mesea Operator.app/Contents/MacOS/…``); the portable artifact is the bare
  unix binary. Running from inside a ``.app`` ⇒ installed.
* **Linux** — the ``.deb`` installs under a system prefix (``/usr``…). Running
  from there ⇒ installed; anywhere else (Downloads, ``$HOME``) ⇒ portable.
"""

from __future__ import annotations

import os
import sys

CONTEXT_INSTALLED = "installed"
CONTEXT_PORTABLE = "portable"

# The Inno Setup AppId (packaging/windows/installer.iss). Inno records the
# per-user uninstall entry under "<AppId>_is1"; the leading "{{" in the .iss is
# its escape for a literal "{", so the stored AppId keeps a single brace pair.
_WIN_UNINSTALL_SUBKEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{8F4E2A10-MESEA-OPER-ATOR-0000A1B2C3D4}_is1"
)


def executable_path() -> str:
    """Absolute path of the running program (frozen exe, or the dev script)."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0] or __file__)


def detect_context(
    *,
    frozen: bool | None = None,
    exe_path: str | None = None,
    platform: str | None = None,
    win_install_location: str | None = None,
) -> str:
    """Classify the running build as ``installed`` or ``portable``.

    All inputs are injectable so the per-OS logic can be exercised on any host.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    platform = platform or sys.platform
    exe_path = exe_path or executable_path()

    if not frozen:
        # A source / `python -m` run isn't a packaged artifact; never nag it
        # toward an installer.
        return CONTEXT_PORTABLE

    if platform.startswith("win"):
        if win_install_location is None:
            win_install_location = _read_windows_install_location()
        return _classify_windows(exe_path, win_install_location)
    if platform == "darwin":
        return _classify_macos(exe_path)
    return _classify_linux(exe_path)


def asset_suffix(context: str, platform: str | None = None) -> str:
    """Release-asset filename suffix to redirect to for ``context``.

    Matches the asset names produced by ``.github/workflows/release.yml``.
    """
    platform = platform or sys.platform
    installed = context == CONTEXT_INSTALLED
    if platform.startswith("win"):
        return "windows-setup.exe" if installed else "windows.exe"
    if platform == "darwin":
        return "macos.dmg" if installed else "macos"
    return "linux.deb" if installed else "linux"


# --- per-OS classifiers (host-independent string logic) ----------------------
def _norm(path: str) -> str:
    """Lowercased, forward-slashed, trailing-slash-stripped — comparable on any
    host regardless of ``os.sep``."""
    return path.replace("\\", "/").rstrip("/").lower()


def _classify_windows(exe_path: str, install_location: str | None) -> str:
    exe = _norm(exe_path)
    if install_location:
        loc = _norm(install_location)
        if exe == loc or exe.startswith(loc + "/"):
            return CONTEXT_INSTALLED
    parent = exe.rsplit("/", 1)[0] if "/" in exe else ""
    if "/program files" in exe or parent.endswith("/mesea operator"):
        return CONTEXT_INSTALLED
    return CONTEXT_PORTABLE


def _classify_macos(exe_path: str) -> str:
    if ".app/contents/macos/" in _norm(exe_path) + "/":
        return CONTEXT_INSTALLED
    return CONTEXT_PORTABLE


def _classify_linux(exe_path: str) -> str:
    exe = exe_path.replace("\\", "/")
    if exe.startswith(("/usr/", "/opt/")):
        return CONTEXT_INSTALLED
    return CONTEXT_PORTABLE


def _read_windows_install_location() -> str | None:
    """``InstallLocation`` from the Inno uninstall key, or None if not installed."""
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, _WIN_UNINSTALL_SUBKEY) as key:
                value, _ = winreg.QueryValueEx(key, "InstallLocation")
                if value:
                    return str(value)
        except OSError:
            continue
    return None
