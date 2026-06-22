from pathlib import Path

import pytest

from git_ssh_sync import attach
from git_ssh_sync.config import AppConfig, build_project_config
from git_ssh_sync.git import CommandResult


def _config(tmp_path: Path) -> AppConfig:
    project = build_project_config(
        "myproject",
        origin="git@github.com:example/myproject.git",
        dev_host="devserver",
        dev_user="user",
        dev_work_path="/home/user/work/myproject",
        local_repo_path=str(tmp_path / "gateway" / "myproject"),
        dev_cache_path="/home/user/cache repo/myproject.git",
    )
    return AppConfig(projects={"myproject": project})


def _result(
    command: tuple[str, ...],
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
    cwd: Path | None = None,
) -> CommandResult:
    return CommandResult("test", command, returncode, stdout, stderr, cwd)


def test_attach_project_creates_missing_cache_and_adds_gitsync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    local_path = Path(config.projects["myproject"].local.repo_path)
    local_path.mkdir(parents=True)
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(attach, "load_config", lambda: config)

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        command = tuple(args)
        calls.append(("git", (command, cwd, check)))
        outputs = {
            ("rev-parse", "--git-dir"): ".git\n",
            ("get-url", "origin"): "git@github.com:example/myproject.git\n",
            ("remote", "get-url", "origin"): "git@github.com:example/myproject.git\n",
            ("branch", "--show-current"): "main\n",
            ("show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): "",
        }
        return _result(("git", *command), outputs.get(command, ""), cwd=cwd)

    def fake_fetch(remote="origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("fetch", (remote, tuple(refspecs), cwd)))
        return _result(("git", "fetch", remote, *refspecs), cwd=cwd)

    def fake_push(remote="origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("push", (remote, tuple(refspecs), cwd)))
        return _result(("git", "push", remote, *refspecs), cwd=cwd)

    def fake_remote_path_exists(host, path, *, user, remote_os, path_type):
        calls.append(("path-exists", (host, path, path_type)))
        returncode = 0 if path == "/home/user/work/myproject" else 1
        return _result(("ssh", host), returncode=returncode)

    def fake_remote_git(host, repo_path, args, *, user=None, check=True, **kwargs):
        command = tuple(args)
        calls.append(("remote-git", (repo_path, command, check)))
        outputs = {
            ("rev-parse", "--is-inside-work-tree"): "true\n",
            ("branch", "--show-current"): "main\n",
            ("status", "--porcelain"): "",
        }
        if command == ("remote", "get-url", "gitsync"):
            return _result(("ssh", host), returncode=2, stderr="No such remote\n")
        return _result(("ssh", host), outputs.get(command, ""))

    monkeypatch.setattr(attach.git, "run_git", fake_run_git)
    monkeypatch.setattr(attach.git, "remote", fake_run_git)
    monkeypatch.setattr(attach.git, "fetch", fake_fetch)
    monkeypatch.setattr(attach.git, "push", fake_push)
    monkeypatch.setattr(attach.ssh, "remote_path_exists", fake_remote_path_exists)
    monkeypatch.setattr(
        attach.ssh,
        "remote_mkdir",
        lambda *args, **kwargs: (
            calls.append(("mkdir", args)) or _result(("ssh", "mkdir"))
        ),
    )
    monkeypatch.setattr(
        attach.ssh,
        "run_remote_command",
        lambda *args, **kwargs: (
            calls.append(("remote-command", args)) or _result(("ssh", "git"))
        ),
    )
    monkeypatch.setattr(attach.ssh, "run_remote_git", fake_remote_git)

    attach.attach_project("myproject", yes=True)

    assert ("mkdir", ("devserver", "/home/user/cache repo")) in calls
    assert (
        "push",
        (
            "ssh://user@devserver/home/user/cache%20repo/myproject.git",
            ("refs/remotes/origin/main:refs/heads/main",),
            local_path,
        ),
    ) in calls
    assert (
        "remote-git",
        (
            "/home/user/work/myproject",
            ("remote", "add", "gitsync", "/home/user/cache repo/myproject.git"),
            True,
        ),
    ) in calls


def test_attach_project_stops_when_work_repo_is_dirty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    local_path = Path(config.projects["myproject"].local.repo_path)
    local_path.mkdir(parents=True)
    monkeypatch.setattr(attach, "load_config", lambda: config)
    monkeypatch.setattr(
        attach.git,
        "run_git",
        lambda args, *, cwd=None, check=True, **kwargs: _result(
            ("git", *args),
            {
                ("rev-parse", "--git-dir"): ".git\n",
                ("get-url", "origin"): "git@github.com:example/myproject.git\n",
                (
                    "remote",
                    "get-url",
                    "origin",
                ): "git@github.com:example/myproject.git\n",
                ("branch", "--show-current"): "main\n",
                ("show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): "",
            }.get(tuple(args), ""),
            cwd=cwd,
        ),
    )
    monkeypatch.setattr(attach.git, "remote", attach.git.run_git)
    monkeypatch.setattr(
        attach.git,
        "fetch",
        lambda *args, **kwargs: _result(("git", "fetch"), cwd=kwargs.get("cwd")),
    )
    monkeypatch.setattr(
        attach.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: _result(("ssh", "test"), returncode=0),
    )

    def fake_remote_git(host, repo_path, args, *, user=None, check=True, **kwargs):
        outputs = {
            ("rev-parse", "--is-inside-work-tree"): "true\n",
            ("branch", "--show-current"): "main\n",
            ("status", "--porcelain"): " M app.py\n",
            ("rev-parse", "--is-bare-repository"): "true\n",
            ("remote", "get-url", "gitsync"): "/home/user/cache repo/myproject.git\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(attach.ssh, "run_remote_git", fake_remote_git)

    with pytest.raises(attach.AttachError, match="preflight failed"):
        attach.attach_project("myproject", yes=True)
