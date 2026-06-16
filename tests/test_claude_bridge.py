"""Unit tests for the settings.json token bridge (merge / scrub)."""

import json

from mesea_operator import claude_bridge, config


def _read(path):
    return json.loads(path.read_text())


def test_write_token_creates_env_block(tmp_path):
    p = tmp_path / "settings.json"
    claude_bridge.write_token(p, "msk_live_abc", "https://mesea.ro/api/v1/mcp")
    data = _read(p)
    assert data["env"][config.TOKEN_ENV_VAR] == "msk_live_abc"
    assert data["env"][config.MCP_URL_ENV_VAR] == "https://mesea.ro/api/v1/mcp"


def test_write_token_preserves_existing_keys(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"theme": "dark", "env": {"OTHER": "keep"}}))
    claude_bridge.write_token(p, "msk_live_xyz")
    data = _read(p)
    assert data["theme"] == "dark"
    assert data["env"]["OTHER"] == "keep"
    assert data["env"][config.TOKEN_ENV_VAR] == "msk_live_xyz"


def test_scrub_removes_only_operator_keys(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps(
            {
                "theme": "dark",
                "env": {
                    "OTHER": "keep",
                    config.TOKEN_ENV_VAR: "secret",
                    config.MCP_URL_ENV_VAR: "url",
                },
            }
        )
    )
    claude_bridge.scrub_token(p)
    data = _read(p)
    assert config.TOKEN_ENV_VAR not in data["env"]
    assert config.MCP_URL_ENV_VAR not in data["env"]
    assert data["env"]["OTHER"] == "keep"
    assert data["theme"] == "dark"


def test_scrub_drops_empty_env_block(tmp_path):
    p = tmp_path / "settings.json"
    claude_bridge.write_token(p, "msk_live_only")
    claude_bridge.scrub_token(p)
    assert "env" not in _read(p)


def test_scrub_is_idempotent_and_safe_on_missing_file(tmp_path):
    p = tmp_path / "nope.json"
    claude_bridge.scrub_token(p)  # must not raise
    claude_bridge.write_token(p, "t")
    claude_bridge.scrub_token(p)
    claude_bridge.scrub_token(p)  # second scrub no-op


def test_write_then_scrub_round_trip_leaves_no_token(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"env": {"KEEP": "1"}}))
    claude_bridge.write_token(p, "msk_live_round", config.MCP_URL)
    assert config.TOKEN_ENV_VAR in _read(p)["env"]
    claude_bridge.scrub_token(p)
    assert config.TOKEN_ENV_VAR not in _read(p)["env"]
    assert _read(p)["env"]["KEEP"] == "1"


def test_launch_claude_runs_in_workspace_cwd_without_positional_arg(monkeypatch):
    """Claude Code resolves .mcp.json / .claude/settings.json / CLAUDE.md relative
    to its working directory, so the workspace MUST be the child cwd — not an argv
    member. Passing it positionally makes the CLI treat the path as the initial
    prompt and leaves the project root at the launcher's own (install) dir, so the
    workspace `mesea` MCP server never loads."""
    captured: dict = {}

    class _FakePopen:
        def __init__(self, argv, cwd=None, **kwargs):
            captured["argv"] = argv
            captured["cwd"] = cwd

    monkeypatch.setattr(claude_bridge.subprocess, "Popen", _FakePopen)

    workspace_dir = r"C:\Users\acct\mesea-operator"
    claude_bridge.launch_claude("claude.exe", workspace_dir)

    assert captured["cwd"] == workspace_dir
    assert captured["argv"] == ["claude.exe"]
    assert workspace_dir not in captured["argv"]
