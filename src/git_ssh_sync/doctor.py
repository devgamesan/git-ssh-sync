"""Environment diagnosis workflow."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.markup import escape
from rich.table import Table

from git_ssh_sync import git, ssh
from git_ssh_sync.attach import AttachError, repair_project
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.errors import CommandExecutionError
from git_ssh_sync.logging_config import logger
from git_ssh_sync.status import _ssh_repo_url, _uses_lfs, _uses_submodules

CheckStatus = Literal["ok", "warning", "error"]


class DoctorError(RuntimeError):
    """Raised when doctor finds one or more failed checks."""


@dataclass(frozen=True)
class DoctorCheck:
    """Single diagnostic check result."""

    section: str
    name: str
    status: CheckStatus
    message: str
    environment: str
    next_action: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    """Collected diagnostic results for a configured project."""

    project: str
    branch: str
    origin_url: str
    dev_host: str
    dev_work_path: str
    checks: tuple[DoctorCheck, ...]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)


def _ok(section: str, name: str, message: str, *, environment: str) -> DoctorCheck:
    return DoctorCheck(section, name, "ok", message, environment)


def _warning(
    section: str,
    name: str,
    message: str,
    *,
    environment: str,
    next_action: str | None = None,
) -> DoctorCheck:
    return DoctorCheck(section, name, "warning", message, environment, next_action)


def _error(
    section: str,
    name: str,
    message: str,
    *,
    environment: str,
    next_action: str,
) -> DoctorCheck:
    return DoctorCheck(section, name, "error", message, environment, next_action)


def _command_error_message(error: CommandExecutionError) -> str:
    detail = error.stderr.strip() or error.stdout.strip()
    if detail:
        return detail
    return f"exit code {error.returncode}"


def _check_local_commands() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for command in ("git", "ssh"):
        path = shutil.which(command)
        if path:
            checks.append(
                _ok(
                    "Local",
                    f"{command} command",
                    f"{command} found at {path}",
                    environment="local",
                )
            )
        else:
            checks.append(
                _error(
                    "Local",
                    f"{command} command",
                    f"{command} command was not found.",
                    environment="local",
                    next_action=f"Install {command} and make sure it is available on PATH.",
                )
            )
    return checks


def _check_gateway_repo(local_path: Path) -> list[DoctorCheck]:
    if not local_path.exists():
        return [
            _error(
                "Local",
                "gateway repo",
                f"Gateway repository does not exist: {local_path}",
                environment="local",
                next_action="Run git-ssh-sync clone for this project.",
            )
        ]

    result = git.run_git(["rev-parse", "--git-dir"], cwd=local_path, check=False)
    if result.returncode == 0:
        return [
            _ok(
                "Local",
                "gateway repo",
                "Gateway repository exists and is readable.",
                environment="local",
            )
        ]
    return [
        _error(
            "Local",
            "gateway repo",
            f"Gateway repository is not healthy: {_command_error_message(_as_command_error(result))}",
            environment="local",
            next_action=f"Inspect or recreate the gateway repository at {local_path}.",
        )
    ]


def _as_command_error(result: git.CommandResult) -> CommandExecutionError:
    return CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _check_origin(local_path: Path, branch: str) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    try:
        git.fetch("origin", cwd=local_path)
    except CommandExecutionError as error:
        return [
            _error(
                "Local",
                "origin fetch",
                f"Could not fetch origin: {_command_error_message(error)}",
                environment=error.environment,
                next_action="Check origin URL, network access, and SSH credentials on the local machine.",
            )
        ]
    checks.append(
        _ok("Local", "origin fetch", "origin fetch succeeded.", environment="local")
    )

    origin_ref = f"refs/remotes/origin/{branch}"
    branch_result = git.run_git(
        ["show-ref", "--verify", "--quiet", origin_ref], cwd=local_path, check=False
    )
    if branch_result.returncode == 0:
        checks.append(
            _ok(
                "Repository",
                "current branch",
                f"origin/{branch} exists.",
                environment="local",
            )
        )
    else:
        checks.append(
            _error(
                "Repository",
                "current branch",
                f"origin/{branch} does not exist.",
                environment="local",
                next_action=f"Create {branch} on origin or switch to an existing branch.",
            )
        )
        return checks

    dry_run = git.run_git(
        ["push", "--dry-run", "origin", f"{origin_ref}:refs/heads/{branch}"],
        cwd=local_path,
        check=False,
    )
    if dry_run.returncode == 0:
        checks.append(
            _ok(
                "Local",
                "origin push dry-run",
                "origin push dry-run succeeded.",
                environment="local",
            )
        )
    else:
        checks.append(
            _error(
                "Local",
                "origin push dry-run",
                f"origin push dry-run failed: {_command_error_message(_as_command_error(dry_run))}",
                environment="local",
                next_action="Check write permission to origin and branch protection rules.",
            )
        )
    return checks


def _check_remote_path(
    *,
    host: str,
    user: str,
    path: str,
    remote_os: ssh.RemoteOS,
    label: str,
    next_action: str,
) -> DoctorCheck:
    result = ssh.remote_path_exists(
        host, path, user=user, remote_os=remote_os, path_type="directory"
    )
    if result.returncode == 0:
        return _ok(
            "Development", label, f"{path} exists.", environment=result.environment
        )
    if result.returncode == 1:
        return _error(
            "Development",
            label,
            f"{path} does not exist.",
            environment=result.environment,
            next_action=next_action,
        )
    return _error(
        "Development",
        label,
        f"Could not inspect {path}: {_command_error_message(_as_command_error(result))}",
        environment=result.environment,
        next_action="Check SSH access and path permissions on the development environment.",
    )


def _check_development(
    project: str, project_config: ProjectConfig, branch: str
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    host = project_config.dev.host
    user = project_config.dev.user
    remote_os = project_config.dev.os
    work_path = project_config.dev.work_path
    cache_path = project_config.dev.cache_path

    try:
        ssh.run_remote_command(host, ["true"], user=user, remote_os=remote_os)
    except CommandExecutionError as error:
        return [
            _error(
                "Development",
                "SSH connection",
                f"SSH connection failed: {_command_error_message(error)}",
                environment=error.environment,
                next_action="Fix SSH host, user, keys, or network access for the development environment.",
            )
        ]
    checks.append(
        _ok(
            "Development",
            "SSH connection",
            "SSH connection succeeded.",
            environment=f"ssh:{user}@{host}",
        )
    )

    git_result = ssh.remote_command_exists(host, "git", user=user, remote_os=remote_os)
    if git_result.returncode == 0:
        checks.append(
            _ok(
                "Development",
                "git command",
                f"git found at {git_result.stdout.strip() or 'git'}",
                environment=git_result.environment,
            )
        )
    else:
        checks.append(
            _error(
                "Development",
                "git command",
                "git command was not found on the development environment.",
                environment=git_result.environment,
                next_action="Install git on the development environment and make it available on PATH.",
            )
        )

    cache_path_check = _check_remote_path(
        host=host,
        user=user,
        path=cache_path,
        remote_os=remote_os,
        label="bare cache repo",
        next_action=f"Run git-ssh-sync recover {project} --yes to create the cache repository.",
    )
    checks.append(cache_path_check)
    checks.append(
        _check_remote_path(
            host=host,
            user=user,
            path=work_path,
            remote_os=remote_os,
            label="work repo",
            next_action="Run git-ssh-sync clone for this project to create the work repository.",
        )
    )

    if cache_path_check.status == "ok":
        cache_bare = ssh.run_remote_git(
            host,
            cache_path,
            ["rev-parse", "--is-bare-repository"],
            user=user,
            check=False,
            remote_os=remote_os,
        )
        if cache_bare.returncode == 0 and cache_bare.stdout.strip() == "true":
            checks.append(
                _ok(
                    "Development",
                    "cache repo format",
                    "Cache repository is bare.",
                    environment=cache_bare.environment,
                )
            )
        else:
            checks.append(
                _error(
                    "Development",
                    "cache repo format",
                    f"Cache path is not a bare git repository: {_command_error_message(_as_command_error(cache_bare))}",
                    environment=cache_bare.environment,
                    next_action="Move the existing path or configure a bare cache repository path.",
                )
            )
        cache_branch = ssh.run_remote_git(
            host,
            cache_path,
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            user=user,
            check=False,
            remote_os=remote_os,
        )
        if cache_branch.returncode == 0:
            checks.append(
                _ok(
                    "Development",
                    "cache branch",
                    f"Cache branch {branch} exists.",
                    environment=cache_branch.environment,
                )
            )
        elif cache_branch.returncode == 1:
            checks.append(
                _error(
                    "Development",
                    "cache branch",
                    f"Cache branch {branch} is missing.",
                    environment=cache_branch.environment,
                    next_action=f"Run git-ssh-sync recover {project} --yes to seed the cache branch.",
                )
            )
        else:
            checks.append(
                _error(
                    "Development",
                    "cache branch",
                    f"Could not inspect cache branch {branch}: {_command_error_message(_as_command_error(cache_branch))}",
                    environment=cache_branch.environment,
                    next_action=f"Inspect the cache repository with git -C {cache_path} show-ref --heads.",
                )
            )

    branch_result = ssh.run_remote_git(
        host,
        work_path,
        ["branch", "--show-current"],
        user=user,
        check=False,
        remote_os=remote_os,
    )
    if branch_result.returncode == 0 and branch_result.stdout.strip():
        checks.append(
            _ok(
                "Development",
                "work repo branch",
                f"Current branch: {branch_result.stdout.strip()}",
                environment=branch_result.environment,
            )
        )
    elif branch_result.returncode == 0:
        checks.append(
            _error(
                "Development",
                "work repo branch",
                "Development work repository is in detached HEAD state.",
                environment=branch_result.environment,
                next_action=f"Run git-ssh-sync checkout {project} <branch> or run git -C {work_path} switch <branch> on the development environment.",
            )
        )
    else:
        checks.append(
            _error(
                "Development",
                "work repo branch",
                f"Could not get work repo branch: {_command_error_message(_as_command_error(branch_result))}",
                environment=branch_result.environment,
                next_action="Inspect the development work repository with git status.",
            )
        )

    head = ssh.run_remote_git(
        host,
        work_path,
        ["rev-parse", "--short", "HEAD"],
        user=user,
        check=False,
        remote_os=remote_os,
    )
    head_value = head.stdout.strip() if head.returncode == 0 else "unknown"
    status = ssh.run_remote_git(
        host,
        work_path,
        ["status", "--porcelain"],
        user=user,
        check=False,
        remote_os=remote_os,
    )
    if status.returncode == 0 and not status.stdout.strip():
        checks.append(
            _ok(
                "Development",
                "working tree",
                f"Working tree is clean at {head_value}.",
                environment=status.environment,
            )
        )
    elif status.returncode == 0:
        checks.append(
            _error(
                "Development",
                "working tree",
                f"Development working tree is dirty at {head_value}.",
                environment=status.environment,
                next_action=f"Run git -C {work_path} status --short, then commit changes or run git -C {work_path} stash push -u.",
            )
        )
    else:
        checks.append(
            _error(
                "Development",
                "working tree",
                f"Could not get working tree status: {_command_error_message(_as_command_error(status))}",
                environment=status.environment,
                next_action="Inspect the development work repository with git status.",
            )
        )

    gitsync = ssh.run_remote_git(
        host,
        work_path,
        ["remote", "get-url", "gitsync"],
        user=user,
        check=False,
        remote_os=remote_os,
    )
    if gitsync.returncode == 0 and gitsync.stdout.strip() == cache_path:
        checks.append(
            _ok(
                "Development",
                "gitsync remote",
                "gitsync remote matches cache path.",
                environment=gitsync.environment,
            )
        )
    elif gitsync.returncode == 0:
        checks.append(
            _error(
                "Development",
                "gitsync remote",
                "gitsync remote does not match the configured cache path.",
                environment=gitsync.environment,
                next_action=f"Run git-ssh-sync recover {project} --yes or run git -C {work_path} remote set-url gitsync {cache_path} on the development environment.",
            )
        )
    else:
        checks.append(
            _error(
                "Development",
                "gitsync remote",
                "gitsync remote is missing.",
                environment=gitsync.environment,
                next_action=f"Run git-ssh-sync recover {project} --yes or run git -C {work_path} remote add gitsync {cache_path} on the development environment.",
            )
        )

    return checks


def _current_local_branch(local_path: Path) -> str:
    result = git.run_git(["branch", "--show-current"], cwd=local_path)
    branch = result.stdout.strip()
    if not branch:
        raise DoctorError("Gateway repository is in detached HEAD state.")
    return branch


def _check_history_connection(
    *,
    local_path: Path,
    left: str,
    right: str,
    name: str,
    next_action: str,
) -> DoctorCheck:
    connected = git.run_git(["merge-base", left, right], cwd=local_path, check=False)
    if connected.returncode == 0:
        return _ok(
            "Repository",
            name,
            f"{left} and {right} share history.",
            environment="local",
        )
    return _error(
        "Repository",
        name,
        f"{left} and {right} do not appear to share history.",
        environment="local",
        next_action=next_action,
    )


def _check_repository(
    project: str, project_config: ProjectConfig, branch: str
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    local_path = Path(project_config.local.repo_path)

    if _uses_lfs(local_path):
        checks.append(
            _warning(
                "Repository",
                "Git LFS",
                "This repository appears to use Git LFS.",
                environment="local",
                next_action="Git LFS object synchronization is not supported in v0.1.",
            )
        )
    else:
        checks.append(
            _ok(
                "Repository",
                "Git LFS",
                "Git LFS was not detected.",
                environment="local",
            )
        )

    if _uses_submodules(local_path):
        checks.append(
            _warning(
                "Repository",
                "submodules",
                "This repository uses Git submodules.",
                environment="local",
                next_action="Register each submodule as a separate git-ssh-sync project.",
            )
        )
    else:
        checks.append(
            _ok(
                "Repository",
                "submodules",
                "Git submodules were not detected.",
                environment="local",
            )
        )

    dev_repo_url = _ssh_repo_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        repo_path=project_config.dev.work_path,
        remote_os=project_config.dev.os,
    )
    cache_repo_url = ssh.remote_git_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        repo_path=project_config.dev.cache_path,
        remote_os=project_config.dev.os,
    )

    try:
        git.fetch(
            cache_repo_url,
            [f"refs/heads/{branch}:refs/remotes/dev-cache/{branch}"],
            cwd=local_path,
        )
    except CommandExecutionError as error:
        checks.append(
            _error(
                "Repository",
                "cache branch fetch",
                f"Could not fetch dev-cache/{branch}: {_command_error_message(error)}",
                environment=error.environment,
                next_action=f"Run git-ssh-sync recover {project} --yes to repair or seed the cache branch.",
            )
        )
        return checks
    checks.append(
        _ok(
            "Repository",
            "cache branch fetch",
            f"Fetched dev-cache/{branch}.",
            environment="local",
        )
    )

    try:
        git.fetch(
            dev_repo_url,
            [f"refs/heads/{branch}:refs/remotes/dev/{branch}"],
            cwd=local_path,
        )
    except CommandExecutionError as error:
        checks.append(
            _error(
                "Repository",
                "dev branch fetch",
                f"Could not fetch dev/{branch}: {_command_error_message(error)}",
                environment=error.environment,
                next_action="Check the development work repository and its current branches.",
            )
        )
        return checks
    checks.append(
        _ok(
            "Repository",
            "dev branch fetch",
            f"Fetched dev/{branch}.",
            environment="local",
        )
    )

    checks.append(
        _check_history_connection(
            local_path=local_path,
            left=f"origin/{branch}",
            right=f"dev-cache/{branch}",
            name="origin/cache history",
            next_action=f"Run git-ssh-sync recover {project} --yes to reseed the cache branch from origin/{branch}.",
        )
    )
    checks.append(
        _check_history_connection(
            local_path=local_path,
            left=f"dev-cache/{branch}",
            right=f"dev/{branch}",
            name="cache/work history",
            next_action="Verify that the development work repository was cloned from the configured cache repository.",
        )
    )
    checks.append(
        _check_history_connection(
            local_path=local_path,
            left=f"origin/{branch}",
            right=f"dev/{branch}",
            name="origin/work history",
            next_action="Verify that origin and the development repository were cloned from the same project.",
        )
    )
    return checks


def inspect_doctor(project: str) -> DoctorReport:
    """Run diagnosis for a configured project and return a report."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    return inspect_project_doctor(project, project_config)


def inspect_project_doctor(project: str, project_config: ProjectConfig) -> DoctorReport:
    """Run diagnosis using an already loaded project configuration."""
    local_path = Path(project_config.local.repo_path)
    checks: list[DoctorCheck] = []

    logger.info("Running local command checks...")
    command_checks = _check_local_commands()
    checks.extend(command_checks)
    git_available = any(
        check.name == "git command" and check.status == "ok" for check in command_checks
    )
    ssh_available = any(
        check.name == "ssh command" and check.status == "ok" for check in command_checks
    )

    if not git_available:
        return DoctorReport(
            project=project,
            branch="unknown",
            origin_url=project_config.origin,
            dev_host=project_config.dev.host,
            dev_work_path=project_config.dev.work_path,
            checks=tuple(checks),
        )

    logger.info("Checking gateway repository...")
    checks.extend(_check_gateway_repo(local_path))

    branch = "unknown"
    if local_path.exists():
        branch = _current_local_branch(local_path)
        logger.info(f"Current branch: {branch}")

        logger.info("Checking origin...")
        checks.extend(_check_origin(local_path, branch))

        if ssh_available:
            logger.info("Checking development environment...")
            checks.extend(_check_development(project, project_config, branch))

            logger.info("Checking repository configuration...")
            checks.extend(_check_repository(project, project_config, branch))

    return DoctorReport(
        project=project,
        branch=branch,
        origin_url=project_config.origin,
        dev_host=project_config.dev.host,
        dev_work_path=project_config.dev.work_path,
        checks=tuple(checks),
    )


def print_doctor(report: DoctorReport) -> None:
    """Print a Rich-formatted doctor report."""
    console.print(f"Doctor report for [bold]{escape(report.project)}[/bold]")
    console.print(f"Branch: {escape(report.branch)}")
    console.print(f"Origin: {escape(report.origin_url)}")
    console.print(
        f"Development: {escape(report.dev_host)} {escape(report.dev_work_path)}"
    )
    console.print()

    table = Table(show_header=True)
    table.add_column("Section", style="bold", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Environment", no_wrap=True)
    table.add_column("Message", overflow="fold")
    table.add_column("Next action", overflow="fold")

    styles = {
        "ok": "[green]ok[/green]",
        "warning": "[yellow]warning[/yellow]",
        "error": "[red]error[/red]",
    }
    for check in report.checks:
        table.add_row(
            escape(check.section),
            styles[check.status],
            escape(check.name),
            escape(check.environment),
            escape(check.message),
            escape(check.next_action or ""),
        )
    console.print(table)

    actionable = [
        check for check in report.checks if check.status != "ok" and check.next_action
    ]
    if actionable:
        console.print()
        console.print("[bold]Actions[/bold]")
        for check in actionable:
            console.print(
                f"- {escape(check.section)} / {escape(check.name)}: {escape(check.next_action or '')}"
            )


def doctor_project(
    project: str,
    *,
    repair: bool = False,
    yes: bool = False,
    confirm=None,
) -> None:
    """Run and print diagnosis for a configured project."""
    logger.info(f"Running doctor for project '{project}'")
    report = inspect_doctor(project)
    print_doctor(report)

    if repair:
        try:
            repair_project(project, yes=yes, confirm=confirm)
        except AttachError as error:
            raise DoctorError(str(error)) from error
        report = inspect_doctor(project)
        print_doctor(report)

    if report.has_errors:
        logger.error(f"Doctor found errors for project '{project}'")
        raise DoctorError("Doctor found errors. See diagnostics above.")
    else:
        logger.info(f"Doctor checks passed for project '{project}'")
