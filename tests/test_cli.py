from typer.testing import CliRunner

from git_ssh_sync import cli
from git_ssh_sync.cli import app
from git_ssh_sync.clone import CloneError
from git_ssh_sync.config import default_config_path, get_project, load_config
from git_ssh_sync.doctor import DoctorError
from git_ssh_sync.logging_config import setup_logging
from git_ssh_sync.status import StatusError
from git_ssh_sync.sync import SyncError


runner = CliRunner()


def test_top_level_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "git-ssh-sync" in result.output
    for command in (
        "config",
        "init",
        "clone",
        "status",
        "branch",
        "pull",
        "push",
        "checkout",
        "doctor",
    ):
        assert command in result.output


def test_subcommand_help() -> None:
    for command in (
        "config",
        "init",
        "clone",
        "status",
        "branch",
        "pull",
        "push",
        "checkout",
        "doctor",
    ):
        result = runner.invoke(app, [command, "--help"])

        assert result.exit_code == 0
        assert command in result.output


def test_config_list_command_lists_projects(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(
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
        ],
    )

    result = runner.invoke(app, ["config", "list"])

    assert result.exit_code == 0
    assert "myproject" in result.output
    assert "git@github.com" in result.output
    assert "myproject.git" in result.output
    assert "devserver" in result.output


def test_config_list_command_reports_empty_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(app, ["config", "list"])

    assert result.exit_code == 0
    assert "No projects configured." in result.output


def test_config_show_command_prints_project_details(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(
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
        ],
    )

    result = runner.invoke(app, ["config", "show", "myproject"])

    assert result.exit_code == 0
    assert "myproject" in result.output
    assert "cache_path" in result.output
    assert "sync_tags" in result.output


def test_config_show_command_reports_missing_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(app, ["config", "show", "missing"])

    assert result.exit_code == 1
    assert "Project 'missing' is not configured." in result.output


def test_config_remove_command_requires_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(
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
        ],
    )

    result = runner.invoke(app, ["config", "remove", "myproject"], input="n\n")

    assert result.exit_code == 1
    assert "Aborted." in result.output
    assert get_project(load_config(default_config_path()), "myproject")


def test_config_remove_command_removes_with_yes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(
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
        ],
    )

    result = runner.invoke(app, ["config", "remove", "myproject", "--yes"])

    assert result.exit_code == 0
    assert "Project 'myproject' removed" in result.output
    assert load_config(default_config_path()).projects == {}


def test_config_set_command_updates_project(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(
        app,
        [
            "init",
            "myproject",
            "--origin",
            "git@github.com:example/first.git",
            "--dev-host",
            "devserver",
            "--dev-user",
            "user",
            "--dev-path",
            "/home/user/work/myproject",
        ],
    )

    result = runner.invoke(
        app,
        [
            "config",
            "set",
            "myproject",
            "--origin",
            "git@github.com:example/second.git",
            "--dev-host",
            "devbox",
            "--lfs",
        ],
    )

    assert result.exit_code == 0
    project = get_project(load_config(default_config_path()), "myproject")
    assert project.origin == "git@github.com:example/second.git"
    assert project.dev.host == "devbox"
    assert project.options.lfs is True


def test_config_set_command_requires_changes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runner.invoke(
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
        ],
    )

    result = runner.invoke(app, ["config", "set", "myproject"])

    assert result.exit_code == 1
    assert "at least one" in result.output


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
        ],
    )

    assert result.exit_code == 0
    assert "Project 'myproject' saved" in result.output

    project = get_project(load_config(default_config_path()), "myproject")

    assert project.origin == "git@github.com:example/myproject.git"
    assert project.dev.host == "devserver"
    assert project.dev.user == "user"


def test_init_command_requires_force_for_existing_project(
    monkeypatch, tmp_path
) -> None:
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


def test_branch_command_runs_branch_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "branch_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["branch", "myproject"])

    assert result.exit_code == 0
    assert calls == ["myproject"]


def test_doctor_command_runs_doctor_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "doctor_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["doctor", "myproject"])

    assert result.exit_code == 0
    assert calls == ["myproject"]


def test_doctor_command_reports_doctor_error(monkeypatch) -> None:
    def fail(project: str) -> None:
        raise DoctorError("Doctor found errors.")

    monkeypatch.setattr(cli, "doctor_project", fail)

    result = runner.invoke(app, ["doctor", "myproject"])

    assert result.exit_code == 1
    assert "Doctor found errors." in result.output


def test_pull_command_runs_pull_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "pull_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["pull", "myproject"])

    assert result.exit_code == 0
    assert calls == ["myproject"]
    assert "Project 'myproject' pulled." in result.output


def test_pull_command_rejects_branch_option(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "pull_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["pull", "myproject", "--branch", "main"])

    assert result.exit_code == 2
    assert calls == []


def test_pull_command_reports_sync_error(monkeypatch) -> None:
    def fail(project: str, *, branch: str | None = None) -> None:
        raise SyncError("Cannot fast-forward main.")

    monkeypatch.setattr(cli, "pull_project", fail)

    result = runner.invoke(app, ["pull", "myproject"])

    assert result.exit_code == 1
    assert "Cannot fast-forward main." in result.output


def test_push_command_runs_push_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "push_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["push", "myproject"])

    assert result.exit_code == 0
    assert calls == ["myproject"]
    assert "Project 'myproject' pushed." in result.output


def test_push_command_rejects_branch_option(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "push_project", lambda project: calls.append(project))

    result = runner.invoke(app, ["push", "myproject", "--branch", "main"])

    assert result.exit_code == 2
    assert calls == []


def test_push_command_reports_sync_error(monkeypatch) -> None:
    def fail(project: str, *, branch: str | None = None) -> None:
        raise SyncError("Cannot push main.")

    monkeypatch.setattr(cli, "push_project", fail)

    result = runner.invoke(app, ["push", "myproject"])

    assert result.exit_code == 1
    assert "Cannot push main." in result.output


def test_checkout_command_runs_checkout_workflow(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        cli,
        "checkout_project",
        lambda project, branch, *, create=False, base_branch=None: calls.append(
            (project, branch, create, base_branch)
        ),
    )

    result = runner.invoke(app, ["checkout", "myproject", "feature/foo"])

    assert result.exit_code == 0
    assert calls == [("myproject", "feature/foo", False, None)]
    assert "Project 'myproject' checked out feature/foo." in result.output


def test_checkout_command_passes_base_branch(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        cli,
        "checkout_project",
        lambda project, branch, *, create=False, base_branch=None: calls.append(
            (project, branch, create, base_branch)
        ),
    )

    result = runner.invoke(
        app, ["checkout", "myproject", "-b", "feature/foo", "--base", "develop"]
    )

    assert result.exit_code == 0
    assert calls == [("myproject", "feature/foo", True, "develop")]
    assert "Project 'myproject' checked out feature/foo." in result.output


def test_checkout_command_rejects_base_without_create_branch(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        cli,
        "checkout_project",
        lambda project, branch, *, create=False, base_branch=None: calls.append(
            (project, branch, create, base_branch)
        ),
    )

    result = runner.invoke(
        app, ["checkout", "myproject", "feature/foo", "--base", "develop"]
    )

    assert result.exit_code == 2
    assert calls == []
    assert "--base" in result.output


def test_checkout_command_reports_sync_error(monkeypatch) -> None:
    def fail(
        project: str,
        branch: str,
        *,
        create: bool = False,
        base_branch: str | None = None,
    ) -> None:
        raise SyncError("Development working tree is dirty.")

    monkeypatch.setattr(cli, "checkout_project", fail)

    result = runner.invoke(app, ["checkout", "myproject", "feature/foo"])

    assert result.exit_code == 1
    assert "Development working tree is dirty." in result.output


def test_verbose_option_enables_verbose_logging(monkeypatch) -> None:
    """Test that --verbose option enables INFO level logging."""
    # Track setup_logging calls
    calls = []

    def mock_setup_logging(*, level=None, log_file=None):
        calls.append((level, log_file))

    monkeypatch.setattr(cli, "setup_logging", mock_setup_logging)

    result = runner.invoke(app, ["--verbose", "doctor", "myproject"])

    assert result.exit_code != 0  # Will fail due to missing config, but that's OK
    assert len(calls) == 1
    assert calls[0] == ("INFO", None)


def test_debug_option_enables_debug_logging(monkeypatch) -> None:
    """Test that --debug option enables DEBUG level logging."""
    # Track setup_logging calls
    calls = []

    def mock_setup_logging(*, level=None, log_file=None):
        calls.append((level, log_file))

    monkeypatch.setattr(cli, "setup_logging", mock_setup_logging)

    result = runner.invoke(app, ["--debug", "doctor", "myproject"])

    assert result.exit_code != 0  # Will fail due to missing config, but that's OK
    assert len(calls) == 1
    assert calls[0] == ("DEBUG", None)


def test_log_file_option_sets_log_file(monkeypatch) -> None:
    """Test that --log-file option sets custom log file path."""
    # Track setup_logging calls
    calls = []

    def mock_setup_logging(*, level=None, log_file=None):
        calls.append((level, log_file))

    monkeypatch.setattr(cli, "setup_logging", mock_setup_logging)

    result = runner.invoke(
        app, ["--log-file", "/tmp/test.log", "doctor", "myproject"]
    )

    assert result.exit_code != 0  # Will fail due to missing config, but that's OK
    assert len(calls) == 1
    assert calls[0][1] == "/tmp/test.log"


def test_verbose_and_debug_options_debug_takes_precedence(monkeypatch) -> None:
    """Test that when both --verbose and --debug are provided, --debug takes precedence."""
    calls = []

    def mock_setup_logging(*, level=None, log_file=None):
        calls.append((level, log_file))

    monkeypatch.setattr(cli, "setup_logging", mock_setup_logging)

    result = runner.invoke(app, ["--verbose", "--debug", "doctor", "myproject"])

    assert result.exit_code != 0  # Will fail due to missing config, but that's OK
    assert len(calls) == 1
    assert calls[0] == ("DEBUG", None)
