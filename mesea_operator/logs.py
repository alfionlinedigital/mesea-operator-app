"""Cross-OS file logging for the launcher.

Writes a rotating log to a per-user location so account managers — and we — can
see WHY a launch or workspace update behaved as it did (the launcher otherwise
surfaces only a one-line status). Importable headless (no Tk).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_APP_DIR = "mesea-operator"
_LOG_FILE = "mesea-operator.log"


def log_dir() -> Path:
    """Per-OS writable log directory (created lazily by :func:`setup_logging`)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs"
    else:  # linux/debian — XDG state dir
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / _APP_DIR


def log_path() -> Path:
    return log_dir() / _LOG_FILE


def setup_logging(level: int = logging.INFO) -> Path:
    """Attach a rotating file handler to the root logger and return the log path.

    Idempotent: a second call never adds a duplicate handler, so it is safe to
    call from both the entry point and tests.
    """
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    return path


def open_logs() -> None:
    """Open the log file (or its folder, if no log yet) in the OS default viewer."""
    target = log_path() if log_path().exists() else log_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]  # Windows-only
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except OSError:
        logging.getLogger(__name__).exception("could not open logs at %s", target)
