"""Re-authorization must unlock launch + resume without restarting the app.

Drives the real Tk view with every network / OS collaborator stubbed. Needs a
display (CI runs pytest under ``xvfb-run``); skipped where Tk cannot open one.
"""

import threading
import time

import pytest

tk = pytest.importorskip("tkinter")
pytest.importorskip("sv_ttk")

from mesea_operator import (  # noqa: E402
    api,
    claude_bridge,
    credential_store,
    instance_guard,
    oauth_client,
    prompts,
    ui,
    update_checker,
    workspace,
)


class _Store:
    def __init__(self, token):
        self.cred = credential_store.StoredCredential(token, None, "AM") if token else None

    def load(self):
        return self.cred

    def store(self, access_token, expires_at, account_label):
        self.cred = credential_store.StoredCredential(access_token, expires_at, account_label)


class _NoUpdates:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass


@pytest.fixture(scope="module")
def tk_root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for Tk: {exc}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def root(tk_root):
    """One Tk interpreter for the module; each test gets it clean. Worker threads
    the app started are drained first — they post back via ``after``, so tearing
    the widgets down under them would crash Tcl."""
    before = set(threading.enumerate())
    yield tk_root
    workers = [t for t in threading.enumerate() if t not in before]
    assert _pump_until(tk_root, lambda: not any(t.is_alive() for t in workers))
    for pending in tk_root.tk.splitlist(tk_root.tk.call("after", "info")):
        tk_root.after_cancel(pending)
    for child in tk_root.winfo_children():
        child.destroy()


@pytest.fixture
def stubs(monkeypatch, tmp_path):
    valid = {"old": False, "new": True}
    store = _Store("old")
    monkeypatch.setattr(credential_store, "load", store.load)
    monkeypatch.setattr(credential_store, "store", store.store)
    monkeypatch.setattr(api, "is_token_valid", lambda t: valid[t])
    monkeypatch.setattr(api, "fetch_identity", lambda _t: "AM")
    monkeypatch.setattr(
        oauth_client,
        "run_authorization_flow",
        lambda: oauth_client.TokenResult(access_token="new", expires_at=None),
    )
    monkeypatch.setattr(
        workspace,
        "ensure_workspace",
        lambda _t: workspace.WorkspaceResult(tmp_path, "up-to-date", "", None),
    )
    monkeypatch.setattr(instance_guard, "acquire_singleton", lambda: None)
    monkeypatch.setattr(claude_bridge, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(prompts, "enforce_single_instance", lambda _c: None)
    monkeypatch.setattr(update_checker, "UpdateChecker", _NoUpdates)
    monkeypatch.setattr(ui.messagebox, "showwarning", lambda *_a, **_k: None)
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *_a, **_k: None)
    return valid


def _pump_until(root, condition, timeout=5.0):
    """Run the real mainloop (worker threads post via ``root.after``, which Tk
    only accepts while it runs) until ``condition`` holds or the deadline hits."""
    deadline = time.monotonic() + timeout
    met = []

    def poll():
        if condition():
            met.append(True)
            root.quit()
        elif time.monotonic() >= deadline:
            root.quit()
        else:
            root.after(10, poll)

    root.after(0, poll)
    root.mainloop()
    return bool(met)


def _launch_enabled(app):
    return not app.launch_btn.instate(["disabled"]) and not app.resume_btn.instate(["disabled"])


def test_reauthorizing_an_expired_token_unlocks_launch_and_resume(root, stubs):
    app = ui.OperatorApp(root)
    assert _pump_until(root, lambda: "expirat" in app.status.cget("text"))
    assert not _launch_enabled(app)

    app.on_authorize()

    assert _pump_until(root, lambda: _launch_enabled(app))


def test_reauthorizing_after_an_unreachable_server_unlocks_launch(root, stubs, monkeypatch):
    def unreachable(_t):
        raise api.TokenUnreachable("offline")

    monkeypatch.setattr(api, "is_token_valid", unreachable)
    app = ui.OperatorApp(root)
    assert _pump_until(root, lambda: "indisponibil" in app.status.cget("text"))

    monkeypatch.setattr(api, "is_token_valid", lambda t: stubs[t])
    app.on_authorize()

    assert _pump_until(root, lambda: _launch_enabled(app))


def test_failed_reauthorization_keeps_launch_locked(root, stubs, monkeypatch):
    def denied():
        raise oauth_client.OAuthError("Authorization denied: access_denied")

    monkeypatch.setattr(oauth_client, "run_authorization_flow", denied)
    app = ui.OperatorApp(root)
    assert _pump_until(root, lambda: "expirat" in app.status.cget("text"))

    app.on_authorize()

    assert _pump_until(root, lambda: not app.auth_btn.instate(["disabled"]))
    assert not _pump_until(root, lambda: _launch_enabled(app), timeout=0.5)
