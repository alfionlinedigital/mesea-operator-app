"""Unit tests for workspace clone/pull orchestration (git mocked)."""

import subprocess

from mesea_operator import workspace


def test_error_when_no_git_and_no_existing(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace.shutil, "which", lambda _n: None)
    res = workspace.ensure_workspace(dest=tmp_path / "ws")
    assert res.status == "error"


def test_skipped_when_no_git_but_workspace_present(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    (dest / ".claude").mkdir(parents=True)
    monkeypatch.setattr(workspace.shutil, "which", lambda _n: None)
    res = workspace.ensure_workspace(dest=dest)
    assert res.status == "skipped"


def test_clone_when_absent(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    monkeypatch.setattr(workspace.shutil, "which", lambda _n: "/usr/bin/git")
    calls = []

    def fake_run(cmd, **_k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(workspace.subprocess, "run", fake_run)
    res = workspace.ensure_workspace(dest=dest, repo_url="https://example/repo.git")
    assert res.status == "cloned"
    assert any("clone" in c for c in calls[0])


def test_pull_when_present(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    (dest / ".git").mkdir(parents=True)
    monkeypatch.setattr(workspace.shutil, "which", lambda _n: "/usr/bin/git")
    monkeypatch.setattr(
        workspace.subprocess, "run",
        lambda cmd, **_k: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    res = workspace.ensure_workspace(dest=dest)
    assert res.status == "updated"


def test_pull_failure_with_existing_claude_is_skipped(monkeypatch, tmp_path):
    dest = tmp_path / "ws"
    (dest / ".git").mkdir(parents=True)
    (dest / ".claude").mkdir(parents=True)
    monkeypatch.setattr(workspace.shutil, "which", lambda _n: "/usr/bin/git")

    def fail(cmd, **_k):
        raise subprocess.CalledProcessError(1, cmd, "", "network down")

    monkeypatch.setattr(workspace.subprocess, "run", fail)
    res = workspace.ensure_workspace(dest=dest)
    assert res.status == "skipped"
