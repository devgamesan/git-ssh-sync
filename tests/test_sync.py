from pathlib import Path

import pytest

from git_ssh_sync import sync
from git_ssh_sync.config import AppConfig, DevConfig, LocalConfig, OptionsConfig, ProjectConfig
from git_ssh_sync.git import CommandResult


def _project_config(local_path: Path) -> ProjectConfig:
    return ProjectConfig(
        origin="git@github.com:example/myproject.git",
        default_branch="main",
        local=LocalConfig(repo_path=str(local_path)),
        dev=DevConfig(
            host="devserver",
            user="user",
            work_path="/home/user/work/myproject",
            cache_path="/home/user/cache repo/myproject.git",
        ),
        options=OptionsConfig(),
    )


def _app_config(local_path: Path) -> AppConfig:
    return AppConfig(projects={"myproject": _project_config(local_path)})


def _result(command: tuple[str, ...], stdout: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult(
        environment="test",
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_pull_project_fast_forwards_existing_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))

    def fake_fetch(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("fetch", remote, tuple(refspecs), cwd))
        return _result(("git", "fetch"))

    def fake_rev_parse(revisions, *, cwd=None, check=True, **kwargs):
        calls.append(("rev-parse", tuple(revisions), cwd, check))
        return _result(("git", "rev-parse"))

    def fake_push(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("push", remote, tuple(refspecs), cwd))
        return _result(("git", "push"))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        calls.append(("remote-git", host, repo_path, tuple(args), user, check))
        return _result(("ssh", host))

    monkeypatch.setattr(sync.git, "fetch", fake_fetch)
    monkeypatch.setattr(sync.git, "rev_parse", fake_rev_parse)
    monkeypatch.setattr(sync.git, "push", fake_push)
    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    sync.pull_project("myproject", branch="main")

    cache_url = "ssh://user@devserver/home/user/cache%20repo/myproject.git"
    assert calls == [
        ("fetch", "origin", (), local_path),
        ("rev-parse", ("--verify", "refs/remotes/origin/main"), local_path, False),
        ("push", cache_url, ("refs/remotes/origin/main:refs/heads/main",), local_path),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("fetch", "gitsync", "refs/heads/main:refs/remotes/gitsync/main"),
            "user",
            True,
        ),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("rev-parse", "--verify", "refs/heads/main"),
            "user",
            False,
        ),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("merge-base", "--is-ancestor", "refs/heads/main", "refs/remotes/gitsync/main"),
            "user",
            False,
        ),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("rev-parse", "--verify", "refs/heads/main"),
            "user",
            False,
        ),
        ("remote-git", "devserver", "/home/user/work/myproject", ("switch", "main"), "user", True),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("merge", "--ff-only", "gitsync/main"),
            "user",
            True,
        ),
    ]


def test_pull_project_stops_when_branch_diverged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "rev_parse", lambda *args, **kwargs: _result(("git", "rev-parse")))
    monkeypatch.setattr(sync.git, "push", lambda *args, **kwargs: _result(("git", "push")))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
        }
        if tuple(args) == ("merge-base", "--is-ancestor", "refs/heads/main", "refs/remotes/gitsync/main"):
            return _result(("ssh", host), returncode=1)
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    with pytest.raises(sync.SyncError) as exc_info:
        sync.pull_project("myproject")

    message = str(exc_info.value)
    assert "Cannot fast-forward main." in message
    assert "origin/main and dev/main have diverged." in message
    assert "git merge gitsync/main" in message
    assert "git rebase gitsync/main" in message


def test_checkout_project_switches_new_branch_from_gitsync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "rev_parse", lambda *args, **kwargs: _result(("git", "rev-parse")))
    monkeypatch.setattr(sync.git, "push", lambda *args, **kwargs: _result(("git", "push")))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        calls.append(("remote-git", tuple(args), check))
        if tuple(args) == ("status", "--porcelain"):
            return _result(("ssh", host), "")
        if tuple(args) == ("rev-parse", "--verify", "refs/heads/feature/foo"):
            return _result(("ssh", host), returncode=1)
        return _result(("ssh", host))

    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    sync.checkout_project("myproject", "feature/foo")

    assert calls[-1] == ("remote-git", ("switch", "--track", "-c", "feature/foo", "gitsync/feature/foo"), True)


def test_checkout_project_stops_when_development_worktree_is_dirty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "rev_parse", lambda *args, **kwargs: _result(("git", "rev-parse")))
    monkeypatch.setattr(sync.git, "push", lambda *args, **kwargs: _result(("git", "push")))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        outputs = {
            ("status", "--porcelain"): " M app.py\n",
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    with pytest.raises(sync.SyncError) as exc_info:
        sync.checkout_project("myproject", "feature/foo")

    message = str(exc_info.value)
    assert "Development working tree is dirty" in message
    assert "branch: main" in message
    assert "commit: abc1234" in message
    assert "Commit or stash changes first." in message


def test_pull_project_reports_missing_gateway_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync, "load_config", lambda: _app_config(tmp_path / "missing"))

    with pytest.raises(sync.SyncError, match="gateway repository does not exist"):
        sync.pull_project("myproject", branch="main")
