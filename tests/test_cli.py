from typer.testing import CliRunner

from git_ssh_sync.cli import app


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
