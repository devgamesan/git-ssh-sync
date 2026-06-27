from pathlib import Path

import pytest

from git_ssh_sync import branch
from git_ssh_sync.config import AppConfig, DevConfig, LocalConfig, ProjectConfig
from git_ssh_sync.git import CommandResult


def _project_config(local_path: Path) -> ProjectConfig:
    return ProjectConfig(
        origin="git@github.com:example/myproject.git",
        local=LocalConfig(repo_path=str(local_path)),
        dev=DevConfig(
            host="devserver",
            user="user",
            work_path="/home/user/work/myproject",
            cache_path="/home/user/cache/myproject.git",
        ),
    )


def _app_config(local_path: Path) -> AppConfig:
    return AppConfig(projects={"myproject": _project_config(local_path)})


def _result(command: tuple[str, ...], stdout: str = "") -> CommandResult:
    return CommandResult(
        environment="test",
        command=command,
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def test_branch_delete_stops_when_target_is_current_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()

    monkeypatch.setattr(branch, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(
        branch.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch"))
    )
    monkeypatch.setattr(
        branch.ssh,
        "run_remote_git",
        lambda *args, **kwargs: _result(("ssh", "devserver"), "feature/foo\n"),
    )

    with pytest.raises(branch.BranchError) as exc_info:
        branch.branch_delete_project("myproject", "feature/foo", yes=True)

    assert "Cannot delete the current development branch" in str(exc_info.value)


def test_branch_delete_dry_run_prints_all_matching_refs_without_deleting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()

    monkeypatch.setattr(branch, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(
        branch.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch"))
    )

    def fake_run_git(args, *, cwd=None, **kwargs):
        if tuple(args) == ("ls-remote", "--heads", "origin"):
            return _result(
                ("git", *args),
                "abc\trefs/heads/main\nabc\trefs/heads/feature/foo\n",
            )
        if tuple(args) == (
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/origin",
        ):
            return _result(("git", *args), "refs/remotes/origin/feature/foo\n")
        if tuple(args) == (
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/dev",
        ):
            return _result(("git", *args), "refs/remotes/dev/feature/foo\n")
        if tuple(args[:2]) == ("update-ref", "-d"):
            raise AssertionError("dry-run must not delete local refs")
        return _result(("git", *args))

    def fake_run_remote_git(host, repo_path, args, **kwargs):
        if tuple(args) == ("branch", "--show-current"):
            return _result(("ssh", host), "main\n")
        if tuple(args) == ("for-each-ref", "--format=%(refname)", "refs/heads"):
            return _result(("ssh", host), "refs/heads/feature/foo\n")
        if tuple(args[:2]) == ("branch", "-D"):
            raise AssertionError("dry-run must not delete remote branches")
        return _result(("ssh", host))

    def fail_push(*args, **kwargs):
        raise AssertionError("dry-run must not delete origin branches")

    monkeypatch.setattr(branch.git, "run_git", fake_run_git)
    monkeypatch.setattr(branch.git, "push", fail_push)
    monkeypatch.setattr(branch.ssh, "run_remote_git", fake_run_remote_git)

    branch.branch_delete_project("myproject", "feature/foo", dry_run=True)

    output = capsys.readouterr().out
    assert "Mode: dry-run" in output
    assert "Target branch: feature/foo" in output
    assert "origin" in output
    assert "dev cache" in output
    assert "work repo" in output
    assert "gateway origin ref" in output
    assert "gateway dev ref" in output


def test_branch_delete_yes_applies_all_matching_deletions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(branch, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(
        branch.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch"))
    )

    def fake_run_git(args, *, cwd=None, **kwargs):
        calls.append(("run-git", tuple(args), cwd))
        if tuple(args) == ("ls-remote", "--heads", "origin"):
            return _result(
                ("git", *args),
                "abc\trefs/heads/main\nabc\trefs/heads/feature/foo\n",
            )
        if tuple(args) == (
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/origin",
        ):
            return _result(("git", *args), "refs/remotes/origin/feature/foo\n")
        if tuple(args) == (
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/dev",
        ):
            return _result(("git", *args), "refs/remotes/dev/feature/foo\n")
        return _result(("git", *args))

    def fake_push(remote="origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("push", remote, tuple(refspecs), cwd))
        return _result(("git", "push"))

    def fake_run_remote_git(host, repo_path, args, **kwargs):
        calls.append(("remote-git", repo_path, tuple(args)))
        if tuple(args) == ("branch", "--show-current"):
            return _result(("ssh", host), "main\n")
        if tuple(args) == ("for-each-ref", "--format=%(refname)", "refs/heads"):
            return _result(("ssh", host), "refs/heads/feature/foo\n")
        return _result(("ssh", host))

    monkeypatch.setattr(branch.git, "run_git", fake_run_git)
    monkeypatch.setattr(branch.git, "push", fake_push)
    monkeypatch.setattr(branch.ssh, "run_remote_git", fake_run_remote_git)

    branch.branch_delete_project("myproject", "feature/foo", yes=True)

    assert ("push", "origin", (":refs/heads/feature/foo",), local_path) in calls
    assert (
        "remote-git",
        "/home/user/cache/myproject.git",
        ("branch", "-D", "feature/foo"),
    ) in calls
    assert (
        "remote-git",
        "/home/user/work/myproject",
        ("branch", "-D", "feature/foo"),
    ) in calls
    assert (
        "run-git",
        ("update-ref", "-d", "refs/remotes/origin/feature/foo"),
        local_path,
    ) in calls
    assert (
        "run-git",
        ("update-ref", "-d", "refs/remotes/dev/feature/foo"),
        local_path,
    ) in calls


def test_branch_prune_deletes_refs_missing_from_origin_except_current_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(branch, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(
        branch.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch"))
    )

    def fake_run_git(args, *, cwd=None, **kwargs):
        calls.append(("run-git", tuple(args), cwd))
        if tuple(args) == ("ls-remote", "--heads", "origin"):
            return _result(("git", *args), "abc\trefs/heads/main\n")
        if tuple(args) == (
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/origin",
        ):
            return _result(
                ("git", *args),
                "refs/remotes/origin/main\nrefs/remotes/origin/stale\n",
            )
        if tuple(args) == (
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/dev",
        ):
            return _result(("git", *args), "refs/remotes/dev/stale\n")
        return _result(("git", *args))

    def fake_run_remote_git(host, repo_path, args, **kwargs):
        calls.append(("remote-git", repo_path, tuple(args)))
        if tuple(args) == ("branch", "--show-current"):
            return _result(("ssh", host), "main\n")
        if tuple(args) == ("for-each-ref", "--format=%(refname)", "refs/heads"):
            return _result(
                ("ssh", host),
                "refs/heads/main\nrefs/heads/stale\n",
            )
        return _result(("ssh", host))

    monkeypatch.setattr(branch.git, "run_git", fake_run_git)
    monkeypatch.setattr(branch.ssh, "run_remote_git", fake_run_remote_git)

    branch.branch_prune_project("myproject", yes=True)

    assert (
        "remote-git",
        "/home/user/cache/myproject.git",
        ("branch", "-D", "stale"),
    ) in calls
    assert (
        "remote-git",
        "/home/user/work/myproject",
        ("branch", "-D", "stale"),
    ) in calls
    assert (
        "run-git",
        ("update-ref", "-d", "refs/remotes/origin/stale"),
        local_path,
    ) in calls
    assert (
        "run-git",
        ("update-ref", "-d", "refs/remotes/dev/stale"),
        local_path,
    ) in calls
    assert (
        "remote-git",
        "/home/user/work/myproject",
        ("branch", "-D", "main"),
    ) not in calls
