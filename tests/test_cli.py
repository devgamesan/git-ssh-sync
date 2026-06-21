from typer.testing import CliRunner

from git_ssh_sync import cli
from git_ssh_sync.cli import app
from git_ssh_sync.clone import CloneError
from git_ssh_sync.config import default_config_path, get_project, load_config
from git_ssh_sync.status import StatusError


runner = CliRunner()


def test_top_level_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "git-ssh-sync" in result.output
    for command in ("init", "clone", "status", "pull", "push", "checkout", "doctor"):
        assert command in result.output


def test_subcommand_help() -> None:
    for command in ("init", "clone", "status", "pull", "push", "checkout", "doctor"):
        result = runner.invoke(app, [command, "--help"])

        assert result.exit_code == 0
        assert command in result.output


def test_init_command_creates_project_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "init",
            "myproject",
            "--origin",
            "git@github.com:example/myproject.git",
            "--dev-host",
            "devserver",
            "--dev-user",
            "user",
            "--dev-path",
            "/home/user/work/myproject",
            "--branch",
            "main",
        ],
    )

    assert result.exit_code == 0
    assert "Project 'myproject' saved" in result.output

    project = get_project(load_config(default_config_path()), "myproject")

    assert project.origin == "git@github.com:example/myproject.git"
    assert project.default_branch == "main"
    assert project.dev.host == "devserver"
    assert project.dev.user == "user"


def test_init_command_requires_force_for_existing_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    args = [
        "init",
        "myproject",
        "--origin",
        "git@github.com:example/myproject.git",
        "--dev-host",
        "devserver",
        "--dev-user",
        "user",
        "--dev-path",
        "/home/user/work/myproject",
    ]

    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "Use --force" in second.output


def test_clone_command_runs_clone_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "clone_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["clone", "myproject"])

    assert result.exit_code == 0
    assert calls == ["myproject"]
    assert "Project 'myproject' cloned." in result.output


def test_clone_command_reports_clone_error(monkeypatch) -> None:
    def fail(project: str) -> None:
        raise CloneError("[local] path already exists: /tmp/myproject")

    monkeypatch.setattr(cli, "clone_project", fail)

    result = runner.invoke(app, ["clone", "myproject"])

    assert result.exit_code == 1
    assert "[local] path already exists" in result.output


def test_status_command_runs_status_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "status_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["status", "myproject"])

    assert result.exit_code == 0
    assert calls == ["myproject"]


def test_status_command_reports_status_error(monkeypatch) -> None:
    def fail(project: str) -> None:
        raise StatusError("[local] gateway repository does not exist: /tmp/myproject")

    monkeypatch.setattr(cli, "status_project", fail)

    result = runner.invoke(app, ["status", "myproject"])

    assert result.exit_code == 1
    assert "gateway repository does not exist" in result.output
