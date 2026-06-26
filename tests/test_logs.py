"""Tests for cross-OS file logging (headless)."""

import logging
from logging.handlers import RotatingFileHandler

from mesea_operator import logs


def _remove_file_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


def test_log_path_uses_localappdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(logs.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert logs.log_path() == tmp_path / "mesea-operator" / "mesea-operator.log"


def test_log_path_uses_xdg_state_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(logs.sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert logs.log_path() == tmp_path / "mesea-operator" / "mesea-operator.log"


def test_setup_logging_creates_file_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(logs, "log_path", lambda: tmp_path / "mesea-operator.log")
    try:
        path = logs.setup_logging()
        assert path.exists()
        logging.getLogger("mesea_operator.test").info("hello log")
        count = lambda: sum(  # noqa: E731 - terse local in a test
            isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers
        )
        first = count()
        logs.setup_logging()  # a second call must NOT add a duplicate handler
        assert first == count() == 1
    finally:
        _remove_file_handlers()
