"""Local Git command execution helpers."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from git_ssh_sync.console import console
from git_ssh_sync.errors import CommandExecutionError, format_command
from git_ssh_sync.logging_config import logger


@dataclass(frozen=True)
class CommandResult:
    """Completed command details for callers that need user-facing output."""

    environment: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    cwd: Path | None = None


def _merged_env(env: Mapping[str, str] | None) -> dict[str, str] | None:
    if env is None:
        return None
    return {**os.environ, **env}


def _run_command(
    command: Sequence[str],
    *,
    environment: str,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    cwd_path = Path(cwd) if cwd is not None else None
    command_tuple = tuple(str(part) for part in command)

    # Log command execution
    logger.debug(f"Executing: {format_command(command_tuple)}")
    logger.debug(f"Working directory: {cwd_path or 'current'}")
    logger.debug(f"Environment: {environment}")

    if verbose:
        console.print(f"$ {format_command(command_tuple)}")

    completed = subprocess.run(
        list(command_tuple),
        cwd=cwd_path,
        env=_merged_env(env),
        capture_output=True,
        text=True,
        check=False,
    )

    # Log command result
    logger.debug(f"Return code: {completed.returncode}")
    if completed.stdout:
        logger.debug(f"Stdout: {completed.stdout.strip()}")
    if completed.stderr:
        logger.debug(f"Stderr: {completed.stderr.strip()}")

    result = CommandResult(
        environment=environment,
        command=command_tuple,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        cwd=cwd_path,
    )
    if check and completed.returncode != 0:
        raise CommandExecutionError(
            environment=environment,
            command=command_tuple,
            returncode=completed.returncode,
            cwd=cwd_path,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return result


def run_git(
    args: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    """Run a local git command using argv arguments."""
    return _run_command(
        ["git", *args],
        environment="local",
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )


def fetch(
    remote: str = "origin",
    refspecs: Sequence[str] = (),
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git fetch`."""
    return run_git(["fetch", remote, *refspecs], cwd=cwd, env=env, verbose=verbose)


def push(
    remote: str = "origin",
    refspecs: Sequence[str] = (),
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git push`."""
    return run_git(["push", remote, *refspecs], cwd=cwd, env=env, verbose=verbose)


def rev_parse(
    revisions: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    """Run `git rev-parse`."""
    return run_git(
        ["rev-parse", *revisions], cwd=cwd, env=env, verbose=verbose, check=check
    )


def log_oneline(
    revision: str = "HEAD",
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git log -1 --format=%h %s` for a revision."""
    return run_git(
        ["log", "-1", "--format=%h %s", revision], cwd=cwd, env=env, verbose=verbose
    )


def status_porcelain(
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git status --porcelain`."""
    return run_git(["status", "--porcelain"], cwd=cwd, env=env, verbose=verbose)


def merge_base(
    left: str,
    right: str,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git merge-base`."""
    return run_git(["merge-base", left, right], cwd=cwd, env=env, verbose=verbose)


def rev_list(
    revisions: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git rev-list`."""
    return run_git(["rev-list", *revisions], cwd=cwd, env=env, verbose=verbose)


def remote(
    args: Sequence[str] = (),
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
) -> CommandResult:
    """Run `git remote`."""
    return run_git(["remote", *args], cwd=cwd, env=env, verbose=verbose)
