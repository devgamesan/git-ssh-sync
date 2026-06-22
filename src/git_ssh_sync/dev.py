"""Read-only development repository inspection commands."""

from __future__ import annotations

from collections.abc import Sequence

from rich.markup import escape

from git_ssh_sync import ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.errors import CommandExecutionError


class DevCommandError(RuntimeError):
    """Raised when a development repository command cannot be completed."""


def _ensure_remote_work_repo(project_config: ProjectConfig) -> None:
    result = ssh.remote_path_exists(
        project_config.dev.host,
        project_config.dev.work_path,
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
        path_type="directory",
    )
    if result.returncode == 0:
        return
    if result.returncode == 1:
        raise DevCommandError(
            f"[{result.environment}] work repository does not exist: "
            f"{project_config.dev.work_path}"
        )
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_remote_git(
    project_config: ProjectConfig, args: Sequence[str], *, check: bool = True
):
    return ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        args,
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
        check=check,
    )


def _ensure_current_branch(project_config: ProjectConfig) -> str:
    branch = _run_remote_git(
        project_config, ["branch", "--show-current"]
    ).stdout.strip()
    if not branch:
        raise DevCommandError("Development work repository is in detached HEAD state.")
    return branch


def _load_project(project: str) -> ProjectConfig:
    return get_project(load_config(), project)


def _print_command_output(output: str) -> None:
    if output:
        console.print(escape(output), end="")


def _prepare_project(project: str) -> ProjectConfig:
    project_config = _load_project(project)
    _ensure_remote_work_repo(project_config)
    _ensure_current_branch(project_config)
    return project_config


def dev_status_project(project: str) -> None:
    """Print `git status --short --branch` for the development work repo."""
    project_config = _prepare_project(project)
    result = _run_remote_git(project_config, ["status", "--short", "--branch"])
    _print_command_output(result.stdout)


def dev_diff_project(project: str, *, stat: bool = False, cached: bool = False) -> None:
    """Print uncommitted diff for the development work repo."""
    project_config = _prepare_project(project)
    args = ["diff"]
    if stat:
        args.append("--stat")
    if cached:
        args.append("--cached")
    result = _run_remote_git(project_config, args)
    _print_command_output(result.stdout)


def dev_log_project(project: str, *, max_count: int = 10) -> None:
    """Print recent one-line log entries for the development work repo."""
    if max_count < 1:
        raise DevCommandError("--max-count must be greater than or equal to 1.")

    project_config = _prepare_project(project)
    result = _run_remote_git(
        project_config, ["log", "--oneline", f"--max-count={max_count}"]
    )
    _print_command_output(result.stdout)
