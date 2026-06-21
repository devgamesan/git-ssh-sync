from pathlib import Path
from subprocess import CompletedProcess

import pytest

from git_ssh_sync import git
from git_ssh_sync import ssh
from git_ssh_sync.errors import CommandExecutionError


def test_run_ssh_builds_target_and_quotes_remote_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcess(command, 0, stdout="done\n", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    result = ssh.run_ssh("devserver", ["mkdir", "-p", "/tmp/work repo"], user="alice")

    assert result.environment == "ssh:alice@devserver"
    assert result.stdout == "done\n"
    assert calls[0][0] == ["ssh", "alice@devserver", "mkdir -p '/tmp/work repo'"]


def test_run_remote_git_uses_git_dash_c_over_ssh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    ssh.run_remote_git(
        "devserver",
        Path("/home/alice/work repo"),
        ["status", "--porcelain"],
        user="alice",
    )

    assert calls == [
        [
            "ssh",
            "alice@devserver",
            "git -C '/home/alice/work repo' status --porcelain",
        ]
    ]


def test_run_ssh_raises_contextual_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command, **kwargs):
        return CompletedProcess(
            command, 255, stdout="", stderr="ssh: Could not resolve hostname\n"
        )

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    with pytest.raises(CommandExecutionError) as exc_info:
        ssh.run_ssh("missing-host", ["git", "status"])

    error = exc_info.value

    assert error.environment == "ssh:missing-host"
    assert error.command == ("ssh", "missing-host", "git status")
    assert error.returncode == 255
    assert "Could not resolve hostname" in str(error)
