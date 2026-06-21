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

from mesea_operator import api, startup


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
