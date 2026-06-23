"""SSH command execution helpers."""

from __future__ import annotations

import shlex
from base64 import b64encode
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import quote

from git_ssh_sync.git import CommandResult, _run_command
from git_ssh_sync.logging_config import logger

RemoteOS = Literal["posix", "windows"]


def _target(host: str, user: str | None) -> str:
    return f"{user}@{host}" if user else host


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
    target = _target(host, user)
    remote_command = shlex.join(str(part) for part in command)

    # Log SSH execution
    logger.debug(f"SSH target: {target}")
    logger.debug(f"SSH command: {remote_command}")

    return _run_command(
        ["ssh", target, remote_command],
        environment=f"ssh:{target}",
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_ssh_command_string(
    host: str,
    remote_command: str,
    *,
    user: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    target = _target(host, user)

    logger.debug(f"SSH target: {target}")
    logger.debug(f"SSH command: {remote_command}")

    return _run_command(
        ["ssh", target, remote_command],
        environment=f"ssh:{target}",
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )


def run_powershell(
    host: str,
    script: str,
    *,
    user: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
) -> CommandResult:
    """Run a PowerShell script on an SSH host."""
    encoded_script = b64encode(script.encode("utf-16le")).decode("ascii")
    remote_command = (
        "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f"-EncodedCommand {encoded_script}"
    )
    return _run_ssh_command_string(
        host,
        remote_command,
        user=user,
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )


def run_remote_command(
    host: str,
    command: Sequence[str],
    *,
    user: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    verbose: bool = False,
    check: bool = True,
    remote_os: RemoteOS = "posix",
) -> CommandResult:
    """Run a command on a remote host using the configured remote shell."""
    if remote_os == "windows":
        if list(command) == ["true"]:
            script = "exit 0"
        else:
            script = "& " + " ".join(_powershell_quote(str(part)) for part in command)
        return run_powershell(
            host,
            script,
            user=user,
            cwd=cwd,
            env=env,
            verbose=verbose,
            check=check,
        )
    return run_ssh(
        host,
        command,
        user=user,
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
    remote_os: RemoteOS = "posix",
) -> CommandResult:
    """Run `git -C <path> ...` on an SSH host."""
    if remote_os == "windows":
        script = " ".join(
            ["& 'git'", "-C", _powershell_quote(str(repo_path))]
            + [_powershell_quote(str(arg)) for arg in args]
        )
        logger.debug(f"Remote git command: {script}")
        return run_powershell(
            host,
            script,
            user=user,
            cwd=cwd,
            env=env,
            verbose=verbose,
            check=check,
        )

    git_args = ["git", "-C", str(repo_path), *args]
    logger.debug(f"Remote git command: {' '.join(git_args)}")

    return run_ssh(
        host,
        git_args,
        user=user,
        cwd=cwd,
        env=env,
        verbose=verbose,
        check=check,
    )


def remote_git_url(*, host: str, user: str, repo_path: str, remote_os: RemoteOS) -> str:
    """Build an SSH Git URL for a remote repository path."""
    if remote_os == "windows":
        normalized_path = repo_path.replace("\\", "/")
        return f"{user}@{host}:{normalized_path}"

    normalized_path = repo_path
    quoted_path = quote(normalized_path, safe="/~:")
    return f"ssh://{user}@{host}{quoted_path}"


def remote_parent(path: str, remote_os: RemoteOS) -> str:
    """Return the parent directory using the remote operating system's path rules."""
    if remote_os == "windows":
        return str(PureWindowsPath(path).parent)
    return str(PurePosixPath(path).parent)


def remote_path_exists(
    host: str,
    path: str,
    *,
    user: str,
    remote_os: RemoteOS,
    path_type: Literal["any", "directory"] = "any",
) -> CommandResult:
    """Check whether a remote path exists, returning 0 for exists and 1 for missing."""
    if remote_os == "windows":
        type_clause = " -PathType Container" if path_type == "directory" else ""
        script = (
            f"if (Test-Path -LiteralPath {_powershell_quote(path)}{type_clause}) "
            "{ exit 0 } else { exit 1 }"
        )
        return run_powershell(host, script, user=user, check=False)

    test_flag = "-d" if path_type == "directory" else "-e"
    return run_ssh(host, ["test", test_flag, path], user=user, check=False)


def remote_mkdir(
    host: str,
    path: str,
    *,
    user: str,
    remote_os: RemoteOS,
) -> CommandResult:
    """Create a remote directory and its parents."""
    if remote_os == "windows":
        script = (
            "New-Item -ItemType Directory -Force -Path "
            f"{_powershell_quote(path)} | Out-Null"
        )
        return run_powershell(host, script, user=user)
    return run_ssh(host, ["mkdir", "-p", path], user=user)


def remote_remove(
    host: str,
    path: str,
    *,
    user: str,
    remote_os: RemoteOS,
) -> CommandResult:
    """Remove a remote path recursively if it exists."""
    if remote_os == "windows":
        script = (
            "Remove-Item -LiteralPath "
            f"{_powershell_quote(path)} -Recurse -Force -ErrorAction SilentlyContinue"
        )
        return run_powershell(host, script, user=user, check=False)
    return run_ssh(host, ["rm", "-rf", "--", path], user=user, check=False)


def remote_command_exists(
    host: str,
    command: str,
    *,
    user: str,
    remote_os: RemoteOS,
) -> CommandResult:
    """Check whether a command is available on the remote host."""
    if remote_os == "windows":
        script = (
            f"if (Get-Command {_powershell_quote(command)} -ErrorAction SilentlyContinue) "
            "{ exit 0 } else { exit 1 }"
        )
        return run_powershell(host, script, user=user, check=False)
    return run_ssh(
        host,
        ["sh", "-lc", f"command -v {shlex.quote(command)}"],
        user=user,
        check=False,
    )
