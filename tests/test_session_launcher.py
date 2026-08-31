"""Unit tests for the launch sequence extracted out of the Tk view.

The ordering rules asserted here were previously unreachable by tests because
they lived in a closure over Tk state — including the two that keep the AM's
token from being left behind in ``~/.claude/settings.json``.
"""

import pytest

from mesea_operator import session_launcher


class _Recorder:
    def __init__(self):
        self.statuses = []
        self.errors = []
        self.finished = 0

    def callbacks(self):
        return session_launcher.SessionCallbacks(
            set_status=self.statuses.append,
            on_error=self.errors.append,
            on_finished=lambda: setattr(self, "finished", self.finished + 1),
        )


class _Ws:
    def __init__(self, status, detail="", path="/tmp/ws"):
        self.status = status
        self.detail = detail
        self.path = path


class _Proc:
    def __init__(self):
        self.waited = False

    def wait(self):
        self.waited = True
        return 0


@pytest.fixture
def wired(monkeypatch):
    """Stub every collaborator and record what the sequence did."""
    calls = {"scrubbed": 0, "ensure_node": 0, "launched": None, "proc": _Proc()}

    monkeypatch.setattr(
        session_launcher.claude_bridge,
        "scrub_session",
        lambda: calls.__setitem__("scrubbed", calls["scrubbed"] + 1),
    )
    monkeypatch.setattr(
        session_launcher.node_runtime,
        "ensure",
        lambda: (
            calls.__setitem__("ensure_node", calls["ensure_node"] + 1),
            session_launcher.node_runtime.NodeResult("present"),
        )[1],
    )

    def fake_launch(executable, workspace_dir, resume=False):
        calls["launched"] = (executable, workspace_dir, resume)
        return calls["proc"]

    monkeypatch.setattr(session_launcher.claude_bridge, "launch_claude", fake_launch)
    return calls


def test_happy_path_ensures_node_then_launches_then_scrubs(monkeypatch, wired):
    monkeypatch.setattr(
        session_launcher.workspace, "ensure_workspace", lambda token: _Ws("downloaded")
    )
    rec = _Recorder()

    session_launcher.run_session("tok", "/bin/claude", False, rec.callbacks())

    assert wired["ensure_node"] == 1
    assert wired["launched"] == ("/bin/claude", "/tmp/ws", False)
    assert wired["proc"].waited is True
    assert wired["scrubbed"] == 1
    assert rec.errors == []
    assert rec.finished == 1


def test_resume_flag_reaches_the_launcher(monkeypatch, wired):
    monkeypatch.setattr(
        session_launcher.workspace, "ensure_workspace", lambda token: _Ws("up-to-date")
    )

    session_launcher.run_session("tok", "/bin/claude", True, _Recorder().callbacks())

    assert wired["launched"][2] is True


def test_workspace_failure_scrubs_the_token_and_never_launches(monkeypatch, wired):
    monkeypatch.setattr(
        session_launcher.workspace,
        "ensure_workspace",
        lambda token: _Ws("error", detail="404 from the bundle endpoint"),
    )
    rec = _Recorder()

    session_launcher.run_session("tok", "/bin/claude", False, rec.callbacks())

    assert wired["launched"] is None
    # The token was already staged into settings.json before we got here.
    assert wired["scrubbed"] == 1
    assert rec.errors == ["404 from the bundle endpoint"]
    assert rec.finished == 1


def test_token_is_scrubbed_even_when_the_launch_itself_raises(monkeypatch, wired):
    monkeypatch.setattr(
        session_launcher.workspace, "ensure_workspace", lambda token: _Ws("downloaded")
    )

    def boom(*a, **k):
        raise OSError("exec format error")

    monkeypatch.setattr(session_launcher.claude_bridge, "launch_claude", boom)
    rec = _Recorder()

    with pytest.raises(OSError):
        session_launcher.run_session("tok", "/bin/claude", False, rec.callbacks())

    assert wired["scrubbed"] == 1
    assert rec.finished == 1


def test_unavailable_node_does_not_stop_the_session(monkeypatch, wired):
    monkeypatch.setattr(
        session_launcher.workspace, "ensure_workspace", lambda token: _Ws("downloaded")
    )
    monkeypatch.setattr(
        session_launcher.node_runtime,
        "ensure",
        lambda: session_launcher.node_runtime.NodeResult("unavailable", None, "offline"),
    )

    session_launcher.run_session("tok", "/bin/claude", False, _Recorder().callbacks())

    # Everything except the Playwright-driven steps still works.
    assert wired["launched"] is not None
    assert wired["scrubbed"] == 1
