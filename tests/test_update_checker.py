"""Tests for the periodic self-update checker (headless: fake root, no Tk)."""

from mesea_operator import update_checker, updater


class FakeRoot:
    """Records ``after`` scheduling instead of running a Tk loop."""

    def __init__(self):
        self.scheduled = []

    def after(self, ms, fn):
        self.scheduled.append((ms, fn))

    def run_immediate(self):
        """Invoke (and consume) callbacks scheduled with delay 0."""
        due = [fn for ms, fn in self.scheduled if ms == 0]
        self.scheduled = [(ms, fn) for ms, fn in self.scheduled if ms != 0]
        for fn in due:
            fn()


def _info(available, version, etag=None, not_modified=False):
    return updater.UpdateInfo(
        available, version, "url" if available else None, etag=etag, not_modified=not_modified
    )


def test_prompts_once_per_version(monkeypatch):
    prompted = []
    root = FakeRoot()
    checker = update_checker.UpdateChecker(
        root, "portable", lambda info: prompted.append(info.latest_version)
    )

    monkeypatch.setattr(update_checker.updater, "check_for_update", lambda **_kw: _info(True, "v0.9.0", etag="e1"))
    checker._check()
    root.run_immediate()
    assert prompted == ["v0.9.0"]

    # next poll finds nothing new (304) — must NOT prompt again for the same version
    root.scheduled.clear()
    monkeypatch.setattr(
        update_checker.updater, "check_for_update", lambda **_kw: _info(False, "v0.9.0", etag="e1", not_modified=True)
    )
    checker._check()
    root.run_immediate()
    assert prompted == ["v0.9.0"]


def test_prompts_again_for_a_newer_version(monkeypatch):
    prompted = []
    root = FakeRoot()
    checker = update_checker.UpdateChecker(root, "portable", lambda info: prompted.append(info.latest_version))

    monkeypatch.setattr(update_checker.updater, "check_for_update", lambda **_kw: _info(True, "v0.9.0", etag="e1"))
    checker._check()
    root.run_immediate()
    monkeypatch.setattr(update_checker.updater, "check_for_update", lambda **_kw: _info(True, "v1.0.0", etag="e2"))
    checker._check()
    root.run_immediate()
    assert prompted == ["v0.9.0", "v1.0.0"]


def test_forwards_and_stores_etag(monkeypatch):
    root = FakeRoot()
    seen = {}

    def fake_check(**kw):
        seen["etag"] = kw.get("etag")
        return _info(False, "v0.1.0", etag="stored-etag")

    monkeypatch.setattr(update_checker.updater, "check_for_update", fake_check)
    checker = update_checker.UpdateChecker(root, "portable", lambda _i: None)

    checker._check()
    assert seen["etag"] is None  # first poll: nothing cached yet
    assert checker._etag == "stored-etag"
    checker._check()
    assert seen["etag"] == "stored-etag"  # cached etag forwarded on the next poll


def test_tick_reschedules_itself(monkeypatch):
    root = FakeRoot()
    checker = update_checker.UpdateChecker(root, "portable", lambda _i: None, interval_ms=60_000)
    monkeypatch.setattr(checker, "_check", lambda: None)  # avoid the worker thread / network
    checker._tick()
    assert any(ms == 60_000 and fn == checker._tick for ms, fn in root.scheduled)
