"""SSH command execution helpers."""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

from git_ssh_sync.git import CommandResult, _run_command


def run_ssh(
    host: str,
    command: Sequence[str],
    *,
    user: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    """Run a command on an SSH host."""
    target = f"{user}@{host}" if user else host
    remote_command = shlex.join(str(part) for part in command)
    return _run_command(
        ["ssh", target, remote_command],
        environment=f"ssh:{target}",
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )


def run_remote_git(
    host: str,
    repo_path: str | Path,
    args: Sequence[str],
    *,
    user: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    """Run `git -C <path> ...` on an SSH host."""
    return run_ssh(
        host,
        ["git", "-C", str(repo_path), *args],
        user=user,
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )
