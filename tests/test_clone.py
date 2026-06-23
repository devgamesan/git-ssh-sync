from pathlib import Path

import pytest

from git_ssh_sync import clone
from git_ssh_sync.config import AppConfig, build_project_config
from git_ssh_sync.errors import CommandExecutionError
from git_ssh_sync.git import CommandResult


def _config(tmp_path: Path, *, sync_tags: bool = True) -> AppConfig:
    project = build_project_config(
        "myproject",
        origin="git@github.com:example/myproject.git",
        dev_host="devserver",
        dev_user="user",
        dev_work_path="/home/user/work/myproject",
        local_repo_path=str(tmp_path / "gateway" / "myproject"),
        dev_cache_path="/home/user/cache repo/myproject.git",
    )
    options = project.options.model_copy(update={"sync_tags": sync_tags})
    project = project.model_copy(update={"options": options})
    return AppConfig(projects={"myproject": project})


def test_clone_project_runs_initial_layout_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(clone, "load_config", lambda: _config(tmp_path))

    def fake_run_git(args, **kwargs):
        calls.append(("git", (args, kwargs)))
        if args == ["branch", "--show-current"]:
            return CommandResult(
                "local", ("git", *args), 0, "main\n", "", kwargs.get("cwd")
            )
        return CommandResult("local", ("git", *args), 0, "", "", kwargs.get("cwd"))

    def fake_fetch(remote="origin", refspecs=(), **kwargs):
        calls.append(("fetch", (remote, tuple(refspecs), kwargs)))
        return CommandResult(
            "local", ("git", "fetch", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        )

    def fake_push(remote="origin", refspecs=(), **kwargs):
        calls.append(("push", (remote, tuple(refspecs), kwargs)))
        return CommandResult(
            "local", ("git", "push", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        )

    def fake_run_ssh(host, command, **kwargs):
        relevant_kwargs = {
            key: value
            for key, value in kwargs.items()
            if value is not None
            and not (key == "verbose" and value is False)
            and not (key == "check" and value is True)
        }
        calls.append(("ssh", (host, tuple(command), relevant_kwargs)))
        returncode = 1 if command[:2] == ["test", "-e"] else 0
        return CommandResult(
            f"ssh:{kwargs['user']}@{host}", ("ssh", host, *command), returncode, "", ""
        )

    def fake_run_remote_git(host, repo_path, args, **kwargs):
        relevant_kwargs = {
            key: value
            for key, value in kwargs.items()
            if not (key == "remote_os" and value == "posix")
        }
        calls.append(
            ("remote_git", (host, str(repo_path), tuple(args), relevant_kwargs))
        )
        return CommandResult(
            f"ssh:{kwargs['user']}@{host}", ("ssh", host, "git", *args), 0, "", ""
        )

    monkeypatch.setattr(clone.git, "run_git", fake_run_git)
    monkeypatch.setattr(clone.git, "fetch", fake_fetch)
    monkeypatch.setattr(clone.git, "push", fake_push)
    monkeypatch.setattr(clone.ssh, "run_ssh", fake_run_ssh)
    monkeypatch.setattr(clone.ssh, "run_remote_git", fake_run_remote_git)

    clone.clone_project("myproject")

    local_path = tmp_path / "gateway" / "myproject"
    cache_url = "ssh://user@devserver/home/user/cache%20repo/myproject.git"
    assert calls == [
        (
            "ssh",
            (
                "devserver",
                ("test", "-e", "/home/user/cache repo/myproject.git"),
                {"user": "user", "check": False},
            ),
        ),
        (
            "ssh",
            (
                "devserver",
                ("test", "-e", "/home/user/work/myproject"),
                {"user": "user", "check": False},
            ),
        ),
        (
            "git",
            (["clone", "git@github.com:example/myproject.git", str(local_path)], {}),
        ),
        ("fetch", ("origin", (), {"cwd": local_path})),
        ("git", (["branch", "--show-current"], {"cwd": local_path})),
        (
            "ssh",
            ("devserver", ("mkdir", "-p", "/home/user/cache repo"), {"user": "user"}),
        ),
        (
            "ssh",
            (
                "devserver",
                ("git", "init", "--bare", "/home/user/cache repo/myproject.git"),
                {"user": "user"},
            ),
        ),
        (
            "push",
            (
                cache_url,
                ("refs/remotes/origin/main:refs/heads/main",),
                {"cwd": local_path},
            ),
        ),
        ("push", (cache_url, ("--tags",), {"cwd": local_path})),
        ("ssh", ("devserver", ("mkdir", "-p", "/home/user/work"), {"user": "user"})),
        (
            "ssh",
            (
                "devserver",
                (
                    "git",
                    "clone",
                    "/home/user/cache repo/myproject.git",
                    "/home/user/work/myproject",
                ),
                {"user": "user"},
            ),
        ),
        (
            "remote_git",
            (
                "devserver",
                "/home/user/work/myproject",
                ("remote", "rename", "origin", "gitsync"),
                {"user": "user"},
            ),
        ),
        (
            "remote_git",
            (
                "devserver",
                "/home/user/work/myproject",
                ("switch", "main"),
                {"user": "user"},
            ),
        ),
    ]


def test_clone_project_skips_tags_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pushes = []
    monkeypatch.setattr(
        clone, "load_config", lambda: _config(tmp_path, sync_tags=False)
    )
    monkeypatch.setattr(
        clone.git,
        "run_git",
        lambda args, **kwargs: CommandResult(
            "local",
            ("git", *args),
            0,
            "main\n" if args == ["branch", "--show-current"] else "",
            "",
            kwargs.get("cwd"),
        ),
    )
    monkeypatch.setattr(
        clone.git,
        "fetch",
        lambda remote="origin", refspecs=(), **kwargs: CommandResult(
            "local", ("git", "fetch", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        ),
    )

    def fake_push(remote="origin", refspecs=(), **kwargs):
        pushes.append(tuple(refspecs))
        return CommandResult(
            "local", ("git", "push", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        )

    monkeypatch.setattr(clone.git, "push", fake_push)
    monkeypatch.setattr(
        clone.ssh,
        "run_ssh",
        lambda host, command, **kwargs: CommandResult(
            f"ssh:{kwargs['user']}@{host}",
            ("ssh", host, *command),
            1 if command[:2] == ["test", "-e"] else 0,
            "",
            "",
        ),
    )
    monkeypatch.setattr(
        clone.ssh,
        "run_remote_git",
        lambda host, repo_path, args, **kwargs: CommandResult(
            f"ssh:{kwargs['user']}@{host}", ("ssh", host, "git", *args), 0, "", ""
        ),
    )

    clone.clone_project("myproject")

    assert pushes == [("refs/remotes/origin/main:refs/heads/main",)]


def test_clone_project_pushes_to_windows_cache_with_scp_like_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = build_project_config(
        "myproject",
        origin="git@github.com:example/myproject.git",
        dev_host="devserver",
        dev_user="user",
        dev_os="windows",
        dev_work_path="C:\\Users\\user\\work\\myproject",
        local_repo_path=str(tmp_path / "gateway" / "myproject"),
        dev_cache_path="C:\\Users\\user\\cache repo\\myproject.git",
    )
    monkeypatch.setattr(
        clone, "load_config", lambda: AppConfig(projects={"myproject": project})
    )
    pushes: list[tuple[str, tuple[str, ...]]] = []

    monkeypatch.setattr(
        clone.git,
        "run_git",
        lambda args, **kwargs: CommandResult(
            "local",
            ("git", *args),
            0,
            "main\n" if args == ["branch", "--show-current"] else "",
            "",
            kwargs.get("cwd"),
        ),
    )
    monkeypatch.setattr(
        clone.git,
        "fetch",
        lambda remote="origin", refspecs=(), **kwargs: CommandResult(
            "local", ("git", "fetch", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        ),
    )

    def fake_push(remote="origin", refspecs=(), **kwargs):
        pushes.append((remote, tuple(refspecs)))
        return CommandResult(
            "local", ("git", "push", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        )

    monkeypatch.setattr(clone.git, "push", fake_push)
    monkeypatch.setattr(
        clone.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 1, "", ""
        ),
    )
    monkeypatch.setattr(
        clone.ssh,
        "remote_mkdir",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 0, "", ""
        ),
    )
    monkeypatch.setattr(
        clone.ssh,
        "run_remote_command",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 0, "", ""
        ),
    )
    monkeypatch.setattr(
        clone.ssh,
        "run_remote_git",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 0, "", ""
        ),
    )

    clone.clone_project("myproject")

    assert pushes[0] == (
        "user@devserver:C:/Users/user/cache repo/myproject.git",
        ("refs/remotes/origin/main:refs/heads/main",),
    )


def test_clone_project_cleans_up_created_paths_when_initial_push_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    local_path = Path(config.projects["myproject"].local.repo_path)
    removed_remote_paths: list[str] = []

    monkeypatch.setattr(clone, "load_config", lambda: config)

    def fake_run_git(args, **kwargs):
        if args[0] == "clone":
            local_path.mkdir(parents=True)
        stdout = "main\n" if args == ["branch", "--show-current"] else ""
        return CommandResult("local", ("git", *args), 0, stdout, "", kwargs.get("cwd"))

    def fail_push(remote="origin", refspecs=(), **kwargs):
        raise CommandExecutionError(
            environment="local",
            command=("git", "push", remote, *refspecs),
            returncode=128,
            cwd=kwargs.get("cwd"),
            stderr="push failed\n",
        )

    monkeypatch.setattr(clone.git, "run_git", fake_run_git)
    monkeypatch.setattr(
        clone.git,
        "fetch",
        lambda remote="origin", refspecs=(), **kwargs: CommandResult(
            "local", ("git", "fetch", remote, *refspecs), 0, "", "", kwargs.get("cwd")
        ),
    )
    monkeypatch.setattr(clone.git, "push", fail_push)
    monkeypatch.setattr(
        clone.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 1, "", ""
        ),
    )
    monkeypatch.setattr(
        clone.ssh,
        "remote_mkdir",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 0, "", ""
        ),
    )
    monkeypatch.setattr(
        clone.ssh,
        "run_remote_command",
        lambda *args, **kwargs: CommandResult(
            "ssh:user@devserver", ("ssh", "devserver"), 0, "", ""
        ),
    )

    def fake_remote_remove(host, path, **kwargs):
        removed_remote_paths.append(path)
        return CommandResult(
            f"ssh:{kwargs['user']}@{host}", ("ssh", host, "rm"), 0, "", ""
        )

    monkeypatch.setattr(clone.ssh, "remote_remove", fake_remote_remove)

    with pytest.raises(CommandExecutionError, match="push failed"):
        clone.clone_project("myproject")

    assert not local_path.exists()
    assert removed_remote_paths == [config.projects["myproject"].dev.cache_path]


def test_clone_project_stops_when_local_path_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    Path(config.projects["myproject"].local.repo_path).mkdir(parents=True)
    monkeypatch.setattr(clone, "load_config", lambda: config)

    with pytest.raises(clone.CloneError, match=r"\[local\] path already exists"):
        clone.clone_project("myproject")


def test_clone_project_stops_when_remote_path_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(clone, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(
        clone.ssh,
        "run_ssh",
        lambda host, command, **kwargs: CommandResult(
            f"ssh:{kwargs['user']}@{host}", ("ssh", host, *command), 0, "", ""
        ),
    )

    with pytest.raises(
        clone.CloneError, match=r"\[ssh:user@devserver\] path already exists"
    ):
        clone.clone_project("myproject")


def test_clone_project_reports_unexpected_remote_check_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(clone, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(
        clone.ssh,
        "run_ssh",
        lambda host, command, **kwargs: CommandResult(
            f"ssh:{kwargs['user']}@{host}",
            ("ssh", host, *command),
            255,
            "",
            "ssh failed\n",
        ),
    )

    with pytest.raises(CommandExecutionError, match="ssh failed"):
        clone.clone_project("myproject")
