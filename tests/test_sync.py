from pathlib import Path

import pytest

from git_ssh_sync import sync
from git_ssh_sync.config import AppConfig, DevConfig, LocalConfig, OptionsConfig, ProjectConfig
from git_ssh_sync.git import CommandResult
from git_ssh_sync.errors import CommandExecutionError


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

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        calls.append(("run-git", tuple(args), cwd, check))
        return _result(("git", *args))

    def fake_push(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("push", remote, tuple(refspecs), cwd))
        return _result(("git", "push"))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        calls.append(("remote-git", host, repo_path, tuple(args), user, check))
        return _result(("ssh", host))

    monkeypatch.setattr(sync.git, "fetch", fake_fetch)
    monkeypatch.setattr(sync.git, "run_git", fake_run_git)
    monkeypatch.setattr(sync.git, "push", fake_push)
    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    sync.pull_project("myproject", branch="main")

    cache_url = "ssh://user@devserver/home/user/cache%20repo/myproject.git"
    assert calls == [
        ("fetch", "origin", (), local_path),
        ("run-git", ("show-ref", "--verify", "--quiet", "refs/remotes/origin/main"), local_path, False),
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
            ("show-ref", "--verify", "--quiet", "refs/heads/main"),
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
            ("show-ref", "--verify", "--quiet", "refs/heads/main"),
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
    monkeypatch.setattr(sync.git, "run_git", lambda *args, **kwargs: _result(("git", "show-ref")))
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
        sync.pull_project("myproject", branch="main")

    message = str(exc_info.value)
    assert "Cannot fast-forward main." in message
    assert "origin/main and dev/main have diverged." in message
    assert "git merge gitsync/main" in message
    assert "git rebase gitsync/main" in message


def test_pull_project_requires_branch() -> None:
    with pytest.raises(sync.SyncError) as exc_info:
        sync.pull_project("myproject")

    message = str(exc_info.value)
    assert "`git-ssh-sync pull` requires --branch <branch>." in message
    assert "git-ssh-sync pull myproject --branch main" in message


def test_checkout_project_switches_new_branch_from_gitsync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "run_git", lambda *args, **kwargs: _result(("git", "show-ref")))
    monkeypatch.setattr(sync.git, "push", lambda *args, **kwargs: _result(("git", "push")))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        calls.append(("remote-git", tuple(args), check))
        if tuple(args) == ("status", "--porcelain"):
            return _result(("ssh", host), "")
        if tuple(args) == ("show-ref", "--verify", "--quiet", "refs/heads/feature/foo"):
            return _result(("ssh", host), returncode=1)
        return _result(("ssh", host))

    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    sync.checkout_project("myproject", "feature/foo")

    assert calls[-1] == ("remote-git", ("switch", "--track", "-c", "feature/foo", "gitsync/feature/foo"), True)


def test_checkout_project_creates_branch_from_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    local_calls: list[tuple[str, object]] = []
    remote_calls: list[tuple[str, object]] = []
    origin_refs = {"develop"}

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))

    def fake_fetch(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        local_calls.append(("fetch", remote, tuple(refspecs), cwd))
        if tuple(refspecs) == ("refs/heads/feature/foo:refs/remotes/origin/feature/foo",):
            origin_refs.add("feature/foo")
        return _result(("git", "fetch"))

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        local_calls.append(("run-git", tuple(args), cwd, check))
        if tuple(args[:3]) == ("show-ref", "--verify", "--quiet"):
            branch = str(args[3]).removeprefix("refs/remotes/origin/")
            return _result(("git", *args), returncode=0 if branch in origin_refs else 1)
        return _result(("git", *args))

    def fake_push(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        local_calls.append(("push", remote, tuple(refspecs), cwd))
        return _result(("git", "push"))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        remote_calls.append(("remote-git", tuple(args), check))
        if tuple(args) == ("status", "--porcelain"):
            return _result(("ssh", host), "")
        if tuple(args) == ("show-ref", "--verify", "--quiet", "refs/heads/feature/foo"):
            return _result(("ssh", host), returncode=1)
        return _result(("ssh", host))

    monkeypatch.setattr(sync.git, "fetch", fake_fetch)
    monkeypatch.setattr(sync.git, "run_git", fake_run_git)
    monkeypatch.setattr(sync.git, "push", fake_push)
    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    sync.checkout_project("myproject", "feature/foo", base_branch="develop")

    cache_url = "ssh://user@devserver/home/user/cache%20repo/myproject.git"
    assert local_calls == [
        ("fetch", "origin", (), local_path),
        ("run-git", ("show-ref", "--verify", "--quiet", "refs/remotes/origin/develop"), local_path, False),
        ("run-git", ("show-ref", "--verify", "--quiet", "refs/remotes/origin/feature/foo"), local_path, False),
        ("push", "origin", ("refs/remotes/origin/develop:refs/heads/feature/foo",), local_path),
        (
            "fetch",
            "origin",
            ("refs/heads/feature/foo:refs/remotes/origin/feature/foo",),
            local_path,
        ),
        ("run-git", ("show-ref", "--verify", "--quiet", "refs/remotes/origin/feature/foo"), local_path, False),
        ("push", cache_url, ("refs/remotes/origin/feature/foo:refs/heads/feature/foo",), local_path),
    ]
    assert remote_calls == [
        (
            "remote-git",
            ("fetch", "gitsync", "refs/heads/feature/foo:refs/remotes/gitsync/feature/foo"),
            True,
        ),
        ("remote-git", ("status", "--porcelain"), True),
        ("remote-git", ("show-ref", "--verify", "--quiet", "refs/heads/feature/foo"), False),
        ("remote-git", ("switch", "--track", "-c", "feature/foo", "gitsync/feature/foo"), True),
    ]


def test_checkout_project_stops_when_base_branch_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "run_git", lambda *args, **kwargs: _result(("git", "show-ref"), returncode=1))

    with pytest.raises(sync.SyncError) as exc_info:
        sync.checkout_project("myproject", "feature/foo", base_branch="develop")

    message = str(exc_info.value)
    assert "Origin branch does not exist: develop" in message
    assert "git fetch origin" in message


def test_checkout_project_stops_when_target_branch_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "run_git", lambda *args, **kwargs: _result(("git", "show-ref")))

    with pytest.raises(sync.SyncError) as exc_info:
        sync.checkout_project("myproject", "feature/foo", base_branch="develop")

    message = str(exc_info.value)
    assert "Origin branch already exists: feature/foo" in message
    assert "git-ssh-sync checkout myproject feature/foo" in message


def test_checkout_project_stops_when_development_worktree_is_dirty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "run_git", lambda *args, **kwargs: _result(("git", "show-ref")))
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


def test_push_project_pushes_dev_branch_when_origin_is_ancestor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))

    def fake_fetch(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("fetch", remote, tuple(refspecs), cwd))
        return _result(("git", "fetch"))

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        calls.append(("run-git", tuple(args), cwd, check))
        return _result(("git", *args))

    def fake_push(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("push", remote, tuple(refspecs), cwd))
        return _result(("git", "push"))

    monkeypatch.setattr(sync.git, "fetch", fake_fetch)
    monkeypatch.setattr(sync.git, "run_git", fake_run_git)
    monkeypatch.setattr(sync.git, "push", fake_push)

    sync.push_project("myproject", branch="main")

    work_url = "ssh://user@devserver/home/user/work/myproject"
    assert calls == [
        ("fetch", "origin", (), local_path),
        ("run-git", ("show-ref", "--verify", "--quiet", "refs/remotes/origin/main"), local_path, False),
        ("fetch", work_url, ("refs/heads/main:refs/remotes/dev/main",), local_path),
        (
            "run-git",
            ("merge-base", "--is-ancestor", "refs/remotes/origin/main", "refs/remotes/dev/main"),
            local_path,
            False,
        ),
        ("push", "origin", ("refs/remotes/dev/main:refs/heads/main",), local_path),
    ]


def test_push_project_stops_when_origin_and_dev_diverged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        if tuple(args) == (
            "merge-base",
            "--is-ancestor",
            "refs/remotes/origin/main",
            "refs/remotes/dev/main",
        ):
            return _result(("git", *args), returncode=1)
        return _result(("git", *args))

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, check=True, **kwargs):
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(sync.git, "run_git", fake_run_git)
    monkeypatch.setattr(sync.ssh, "run_remote_git", fake_run_remote_git)

    with pytest.raises(sync.SyncError) as exc_info:
        sync.push_project("myproject", branch="main")

    message = str(exc_info.value)
    assert "Cannot push main." in message
    assert "origin/main has commits that are not included in dev/main." in message
    assert "git-ssh-sync pull myproject --branch main" in message
    assert "branch: main" in message
    assert "commit: abc1234" in message


def test_push_project_requires_branch() -> None:
    with pytest.raises(sync.SyncError) as exc_info:
        sync.push_project("myproject")

    message = str(exc_info.value)
    assert "`git-ssh-sync push` requires --branch <branch>." in message
    assert "git-ssh-sync push myproject --branch main" in message


def test_push_project_reports_origin_push_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local_path = tmp_path / "gateway"
    local_path.mkdir()

    monkeypatch.setattr(sync, "load_config", lambda: _app_config(local_path))
    monkeypatch.setattr(sync.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch")))
    monkeypatch.setattr(sync.git, "run_git", lambda *args, **kwargs: _result(("git", "merge-base")))

    def fail_push(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        raise CommandExecutionError(
            environment="local",
            command=("git", "push", remote, *refspecs),
            returncode=1,
            cwd=cwd,
            stderr="remote rejected\n",
        )

    monkeypatch.setattr(sync.git, "push", fail_push)

    with pytest.raises(sync.SyncError) as exc_info:
        sync.push_project("myproject", branch="main")

    message = str(exc_info.value)
    assert "Failed to push main to origin." in message
    assert "Origin push failed:" in message
    assert "remote rejected" in message
