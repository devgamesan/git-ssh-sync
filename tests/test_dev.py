from pathlib import Path

import pytest

from git_ssh_sync import dev
from git_ssh_sync.config import (
    AppConfig,
    DevConfig,
    LocalConfig,
    OptionsConfig,
    ProjectConfig,
)
from git_ssh_sync.git import CommandResult
from git_ssh_sync.dev import DevCommandError


def _project_config(local_path: Path) -> ProjectConfig:
    return ProjectConfig(
        origin="git@github.com:example/myproject.git",
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


def _result(
    command: tuple[str, ...], stdout: str = "", returncode: int = 0
) -> CommandResult:
    return CommandResult(
        environment="test",
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_dev_status_project_runs_remote_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(dev, "load_config", lambda: _app_config(tmp_path))

    def fake_remote_path_exists(host: str, path: str, **kwargs):
        calls.append(("exists", host, path, kwargs))
        return _result(("ssh", host))

    def fake_run_remote_git(host: str, repo_path: str, args, **kwargs):
        calls.append(("remote-git", host, repo_path, tuple(args), kwargs))
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("status", "--short", "--branch"): "## main\n M app.py\n?? notes.txt\n",
        }
        return _result(("ssh", host), outputs[tuple(args)])

    monkeypatch.setattr(dev.ssh, "remote_path_exists", fake_remote_path_exists)
    monkeypatch.setattr(dev.ssh, "run_remote_git", fake_run_remote_git)

    dev.dev_status_project("myproject")

    assert "## main" in capsys.readouterr().out
    assert calls == [
        (
            "exists",
            "devserver",
            "/home/user/work/myproject",
            {"user": "user", "remote_os": "posix", "path_type": "directory"},
        ),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("branch", "--show-current"),
            {"user": "user", "remote_os": "posix", "check": True},
        ),
        (
            "remote-git",
            "devserver",
            "/home/user/work/myproject",
            ("status", "--short", "--branch"),
            {"user": "user", "remote_os": "posix", "check": True},
        ),
    ]


def test_dev_diff_project_runs_remote_diff_with_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(dev, "load_config", lambda: _app_config(tmp_path))
    monkeypatch.setattr(
        dev.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: _result(("ssh", "devserver")),
    )

    def fake_run_remote_git(host: str, repo_path: str, args, **kwargs):
        calls.append(tuple(args))
        if tuple(args) == ("branch", "--show-current"):
            return _result(("ssh", host), "main\n")
        return _result(("ssh", host), " app.py | 2 +-\n")

    monkeypatch.setattr(dev.ssh, "run_remote_git", fake_run_remote_git)

    dev.dev_diff_project("myproject", stat=True, cached=True)

    assert calls == [
        ("branch", "--show-current"),
        ("diff", "--stat", "--cached"),
    ]


def test_dev_log_project_limits_remote_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(dev, "load_config", lambda: _app_config(tmp_path))
    monkeypatch.setattr(
        dev.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: _result(("ssh", "devserver")),
    )

    def fake_run_remote_git(host: str, repo_path: str, args, **kwargs):
        calls.append(tuple(args))
        if tuple(args) == ("branch", "--show-current"):
            return _result(("ssh", host), "main\n")
        return _result(("ssh", host), "abc1234 Commit title\n")

    monkeypatch.setattr(dev.ssh, "run_remote_git", fake_run_remote_git)

    dev.dev_log_project("myproject", max_count=3)

    assert "abc1234 Commit title" in capsys.readouterr().out
    assert calls == [
        ("branch", "--show-current"),
        ("log", "--oneline", "--max-count=3"),
    ]


def test_dev_command_reports_missing_work_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dev, "load_config", lambda: _app_config(tmp_path))
    monkeypatch.setattr(
        dev.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: _result(("ssh", "devserver"), returncode=1),
    )

    with pytest.raises(DevCommandError, match="work repository does not exist"):
        dev.dev_status_project("myproject")


def test_dev_command_reports_detached_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(dev, "load_config", lambda: _app_config(tmp_path))
    monkeypatch.setattr(
        dev.ssh,
        "remote_path_exists",
        lambda *args, **kwargs: _result(("ssh", "devserver")),
    )
    monkeypatch.setattr(
        dev.ssh,
        "run_remote_git",
        lambda *args, **kwargs: _result(("ssh", "devserver"), "\n"),
    )

    with pytest.raises(DevCommandError, match="detached HEAD"):
        dev.dev_status_project("myproject")


def test_dev_log_project_requires_positive_max_count() -> None:
    with pytest.raises(DevCommandError, match="--max-count"):
        dev.dev_log_project("myproject", max_count=0)
