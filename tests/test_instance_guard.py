"""Unit tests for sibling-instance detection and termination."""

from mesea_operator import instance_guard as ig
from mesea_operator.instance_guard import ProcessInfo


def test_find_other_instances_matches_app_family_excluding_self():
    procs = [
        ProcessInfo(999, "mesea-operator.exe", "/x/mesea-operator.exe"),  # self
        ProcessInfo(111, "mesea-operator-windows.exe", "C:/dl/mesea-operator-windows.exe"),
        ProcessInfo(222, "chrome.exe", "C:/p/chrome.exe"),  # unrelated → ignored
        ProcessInfo(333, "", "/usr/bin/mesea-operator"),  # matched by exe basename
        ProcessInfo(444, "mesea-operator-linux", ""),  # matched by name (no exe)
    ]
    others = ig.find_other_instances(own_pid=999, iter_processes=lambda: procs)
    assert {o.pid for o in others} == {111, 333, 444}


def test_find_other_instances_never_targets_foreign_processes():
    procs = [
        ProcessInfo(1, "explorer.exe", "C:/Windows/explorer.exe"),
        ProcessInfo(2, "python.exe", "C:/py/python.exe"),
    ]
    assert ig.find_other_instances(own_pid=999, iter_processes=lambda: procs) == []


# --- termination -------------------------------------------------------------
class _FakeError(Exception):
    pass


class _FakeNoSuchProcess(_FakeError):
    pass


class _FakeProc:
    def __init__(self, pid, behavior, alive):
        self.pid = pid
        self._behavior = behavior  # "terminate" | "kill" | "never"
        self._alive = alive

    def terminate(self):
        if self._behavior == "terminate":
            self._alive[self.pid] = False

    def kill(self):
        if self._behavior == "kill":
            self._alive[self.pid] = False


class _FakePsutil:
    NoSuchProcess = _FakeNoSuchProcess
    Error = _FakeError

    def __init__(self, behaviors, missing=()):
        self._behaviors = behaviors
        self._missing = set(missing)
        self.alive = {pid: True for pid in behaviors}

    def Process(self, pid):
        if pid in self._missing:
            raise self.NoSuchProcess(pid)
        return _FakeProc(pid, self._behaviors[pid], self.alive)

    def wait_procs(self, procs, timeout=None):
        gone, alive = [], []
        for proc in procs:
            (alive if self.alive.get(proc.pid, False) else gone).append(proc)
        return gone, alive


def test_terminate_escalates_then_reports_per_pid():
    fake = _FakePsutil(
        behaviors={100: "terminate", 200: "kill", 300: "never"},
        missing={400},
    )
    results = ig.terminate([100, 200, 300, 400], timeout=0, psutil_mod=fake)
    assert results == {
        100: True,  # closed on graceful terminate
        200: True,  # survived terminate, closed on kill
        300: False,  # stubborn — reported as not closed
        400: True,  # already gone counts as closed
    }


def test_terminate_returns_false_when_psutil_unavailable(monkeypatch):
    monkeypatch.setattr(ig, "_import_psutil", lambda: None)
    assert ig.terminate([1, 2]) == {1: False, 2: False}


# --- mutex -------------------------------------------------------------------
def test_acquire_singleton_noop_off_windows(monkeypatch):
    monkeypatch.setattr(ig.sys, "platform", "linux")
    assert ig.acquire_singleton() is None


def test_acquire_singleton_does_not_raise_on_host():
    # Whatever the host OS, acquiring the mutex must never crash startup.
    ig.acquire_singleton()
