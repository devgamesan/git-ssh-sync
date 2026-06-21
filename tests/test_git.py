from pathlib import Path
from subprocess import CompletedProcess

import pytest

from git_ssh_sync import git
from git_ssh_sync.errors import CommandExecutionError


def test_fetch_runs_git_fetch_with_cwd_and_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    result = git.fetch(
        "origin", ["main"], cwd=tmp_path, env={"GIT_SSH_COMMAND": "ssh -i key"}
    )

    assert result.environment == "local"
    assert result.command == ("git", "fetch", "origin", "main")
    assert result.stdout == "ok\n"
    assert calls[0][0] == ["git", "fetch", "origin", "main"]
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[0][1]["env"]["GIT_SSH_COMMAND"] == "ssh -i key"
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert calls[0][1]["check"] is False


def test_git_wrappers_build_expected_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    git.push("origin", ["HEAD:main"])
    git.rev_parse(["--abbrev-ref", "HEAD"])
    git.log_oneline("origin/main")
    git.status_porcelain()
    git.merge_base("main", "HEAD")
    git.rev_list(["--left-right", "main...HEAD"])
    git.remote(["-v"])

    assert commands == [
        ["git", "push", "origin", "HEAD:main"],
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        ["git", "log", "-1", "--format=%h %s", "origin/main"],
        ["git", "status", "--porcelain"],
        ["git", "merge-base", "main", "HEAD"],
        ["git", "rev-list", "--left-right", "main...HEAD"],
        ["git", "remote", "-v"],
    ]


def test_run_git_raises_contextual_error_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(command, **kwargs):
        return CompletedProcess(
            command, 128, stdout="", stderr="fatal: not a git repository\n"
        )

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    with pytest.raises(CommandExecutionError) as exc_info:
        git.status_porcelain(cwd=tmp_path)

    error = exc_info.value

    assert error.environment == "local"
    assert error.command == ("git", "status", "--porcelain")
    assert error.returncode == 128
    assert error.cwd == tmp_path
    assert "fatal: not a git repository" in str(error)


def test_run_git_can_return_nonzero_result_without_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command, **kwargs):
        return CompletedProcess(command, 1, stdout="", stderr="no match\n")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    result = git.run_git(["rev-parse", "missing"], check=False)

    assert result.returncode == 1
    assert result.stderr == "no match\n"


def test_verbose_prints_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(command, **kwargs):
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    git.fetch(verbose=True)

    assert "$ git fetch origin" in capsys.readouterr().out
