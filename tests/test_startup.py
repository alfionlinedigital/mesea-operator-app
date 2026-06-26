"""Tests for the headless startup decision (``startup.evaluate_token``).

``ui.py`` imports Tk and cannot run in a headless CI, so the launch-gating rules
live in ``startup`` and are proven here. The UI dispatches on the returned
:class:`TokenOutcome`:

* VALID       → launch + resume enabled
* INVALID     → ``_block_invalid_token`` (buttons stay disabled, re-auth prompt)
* UNREACHABLE → fail closed (buttons stay disabled) WITHOUT the revoked-token block
* NONE        → not signed in

so each outcome below maps 1:1 to one of those UI branches.
"""

from pathlib import Path

from mesea_operator import api, startup, workspace


def test_none_token_returns_none_outcome():
    assert startup.evaluate_token(None) is startup.TokenOutcome.NONE
    assert startup.evaluate_token("") is startup.TokenOutcome.NONE


def test_valid_token_enables_launch(monkeypatch):
    # A definitively-valid token is the ONLY outcome that unlocks launch/resume.
    monkeypatch.setattr(api, "is_token_valid", lambda _t: True)
    assert startup.evaluate_token("good") is startup.TokenOutcome.VALID


def test_invalid_token_blocks_and_keeps_buttons_disabled(monkeypatch):
    # 4xx → definitively invalid → the UI runs _block_invalid_token, never enable.
    monkeypatch.setattr(api, "is_token_valid", lambda _t: False)
    assert startup.evaluate_token("revoked") is startup.TokenOutcome.INVALID


def test_unreachable_does_not_trigger_revoked_block(monkeypatch):
    # 5xx / network → could-not-verify → fail closed, but NOT the revoked block.
    def unreachable(_t):
        raise api.TokenUnreachable("server error 503")

    monkeypatch.setattr(api, "is_token_valid", unreachable)
    outcome = startup.evaluate_token("maybe-good")
    assert outcome is startup.TokenOutcome.UNREACHABLE
    assert outcome is not startup.TokenOutcome.INVALID  # never conflated with revoked


def _ws(status: str, detail: str = "", commit: str | None = None) -> workspace.WorkspaceResult:
    return workspace.WorkspaceResult(Path("ws"), status, detail, commit)


def test_workspace_message_shows_success_states_with_commit():
    # Success is no longer silent — the workspace state (and commit) is shown.
    assert (
        startup.workspace_status_message(_ws("downloaded", commit="abc1234def"))
        == "Workspace actualizat (commit abc1234)."
    )
    assert (
        startup.workspace_status_message(_ws("up-to-date", commit="abc1234def"))
        == "Workspace la zi (commit abc1234)."
    )


def test_workspace_message_surfaces_hard_error():
    msg = startup.workspace_status_message(_ws("error", detail="disk full"))
    assert msg == "Atenție workspace: disk full"


def test_workspace_message_surfaces_stale_skip_with_commit():
    # A frozen workspace must be visible, named by the (short) commit in use.
    msg = startup.workspace_status_message(_ws("skipped", commit="abc1234def"))
    assert msg == "Workspace neactualizat; se folosește ultima versiune (commit abc1234)."


def test_workspace_message_stale_skip_without_commit():
    msg = startup.workspace_status_message(_ws("skipped", commit=None))
    assert msg == "Workspace neactualizat; se folosește ultima versiune."
