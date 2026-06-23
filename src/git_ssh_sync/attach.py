"""Attach existing repositories to git-ssh-sync management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.markup import escape
from rich.table import Table

from git_ssh_sync import git, ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.errors import CommandExecutionError
from git_ssh_sync.logging_config import logger

CheckStatus = Literal["ok", "error"]
OperationKind = Literal[
    "create_cache",
    "seed_cache_branch",
    "add_gitsync_remote",
    "update_gitsync_remote",
]


class AttachError(RuntimeError):
    """Raised when existing repositories cannot be attached safely."""


@dataclass(frozen=True)
class AttachCheck:
    """Single attach preflight check."""

    name: str
    status: CheckStatus
    message: str
    next_action: str | None = None


@dataclass(frozen=True)
class AttachOperation:
    """Repair operation that can be applied after preflight."""

    kind: OperationKind
    description: str


@dataclass(frozen=True)
class AttachPlan:
    """Preflight result for attaching a configured project."""

    project: str
    branch: str
    checks: tuple[AttachCheck, ...]
    operations: tuple[AttachOperation, ...]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)


def _ok(name: str, message: str) -> AttachCheck:
    return AttachCheck(name=name, status="ok", message=message)


def _error(name: str, message: str, *, next_action: str) -> AttachCheck:
    return AttachCheck(
        name=name, status="error", message=message, next_action=next_action
    )


def _command_error_message(result: git.CommandResult | CommandExecutionError) -> str:
    detail = result.stderr.strip() or result.stdout.strip()
    if detail:
        return detail
    return f"exit code {result.returncode}"


def _as_command_error(result: git.CommandResult) -> CommandExecutionError:
    return CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _local_current_branch(local_path: Path) -> str:
    result = git.run_git(["branch", "--show-current"], cwd=local_path)
    branch = result.stdout.strip()
    if not branch:
        raise AttachError("Gateway repository is in detached HEAD state.")
    return branch


def _origin_branch_exists(local_path: Path, branch: str) -> bool:
    result = git.run_git(
        ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
        cwd=local_path,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise _as_command_error(result)


def _remote_path_exists(project_config: ProjectConfig, path: str) -> bool:
    result = ssh.remote_path_exists(
        project_config.dev.host,
        path,
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
        path_type="directory",
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise _as_command_error(result)


def _remote_git_check(
    project_config: ProjectConfig, repo_path: str, args: list[str]
) -> git.CommandResult:
    return ssh.run_remote_git(
        project_config.dev.host,
        repo_path,
        args,
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
        check=False,
    )


def inspect_attach(project: str) -> AttachPlan:
    """Inspect existing repositories and return planned attach repairs."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    return inspect_project_attach(project, project_config)


def inspect_project_attach(project: str, project_config: ProjectConfig) -> AttachPlan:
    """Inspect existing repositories using an already loaded project configuration."""
    checks: list[AttachCheck] = []
    operations: list[AttachOperation] = []
    local_path = Path(project_config.local.repo_path)
    branch = "unknown"

    if not local_path.exists():
        checks.append(
            _error(
                "gateway repo",
                f"Gateway repository does not exist: {local_path}",
                next_action="Clone the repository locally or update local.repo_path.",
            )
        )
        return AttachPlan(project, branch, tuple(checks), tuple(operations))

    local_git = git.run_git(["rev-parse", "--git-dir"], cwd=local_path, check=False)
    if local_git.returncode != 0:
        checks.append(
            _error(
                "gateway repo",
                f"Gateway repository is not a git repository: {_command_error_message(local_git)}",
                next_action=f"Inspect or replace {local_path}.",
            )
        )
        return AttachPlan(project, branch, tuple(checks), tuple(operations))
    checks.append(_ok("gateway repo", "Gateway repository exists."))

    origin = git.remote(["get-url", "origin"], cwd=local_path, check=False)
    if origin.returncode != 0:
        checks.append(
            _error(
                "origin URL",
                f"Could not read origin URL: {_command_error_message(origin)}",
                next_action="Add or fix the gateway repository origin remote.",
            )
        )
    elif origin.stdout.strip() != project_config.origin:
        checks.append(
            _error(
                "origin URL",
                f"Configured origin does not match gateway origin: {origin.stdout.strip()}",
                next_action="Update the project configuration or gateway origin URL.",
            )
        )
    else:
        checks.append(_ok("origin URL", "Gateway origin matches configuration."))

    branch = _local_current_branch(local_path)
    checks.append(_ok("current branch", f"Gateway current branch: {branch}"))

    git.fetch("origin", cwd=local_path)
    if not _origin_branch_exists(local_path, branch):
        checks.append(
            _error(
                "origin branch",
                f"origin/{branch} does not exist.",
                next_action=f"Push or fetch {branch} on origin before attaching.",
            )
        )
    else:
        checks.append(_ok("origin branch", f"origin/{branch} exists."))

    if _remote_path_exists(project_config, project_config.dev.work_path):
        checks.append(_ok("work repo", "Development work repository exists."))
    else:
        checks.append(
            _error(
                "work repo",
                f"Development work repository does not exist: {project_config.dev.work_path}",
                next_action="Clone the work repository on the development environment.",
            )
        )
        return AttachPlan(project, branch, tuple(checks), tuple(operations))

    work_git = _remote_git_check(
        project_config,
        project_config.dev.work_path,
        ["rev-parse", "--is-inside-work-tree"],
    )
    if work_git.returncode != 0 or work_git.stdout.strip() != "true":
        checks.append(
            _error(
                "work repo git",
                f"Development work path is not a git work tree: {_command_error_message(work_git)}",
                next_action="Inspect or reclone the development work repository.",
            )
        )
        return AttachPlan(project, branch, tuple(checks), tuple(operations))
    checks.append(_ok("work repo git", "Development work path is a git repository."))

    work_branch = _remote_git_check(
        project_config, project_config.dev.work_path, ["branch", "--show-current"]
    )
    if work_branch.returncode != 0 or not work_branch.stdout.strip():
        checks.append(
            _error(
                "work repo branch",
                "Development work repository is in detached HEAD state.",
                next_action="Switch the development work repository to a branch.",
            )
        )
    else:
        checks.append(
            _ok(
                "work repo branch",
                f"Development current branch: {work_branch.stdout.strip()}",
            )
        )

    status = _remote_git_check(
        project_config, project_config.dev.work_path, ["status", "--porcelain"]
    )
    if status.returncode != 0:
        checks.append(
            _error(
                "work repo dirty",
                f"Could not inspect development working tree: {_command_error_message(status)}",
                next_action="Run git status on the development environment.",
            )
        )
    elif status.stdout.strip():
        checks.append(
            _error(
                "work repo dirty",
                "Development working tree is dirty.",
                next_action="Commit or stash changes on the development environment.",
            )
        )
    else:
        checks.append(_ok("work repo dirty", "Development working tree is clean."))

    cache_exists = _remote_path_exists(project_config, project_config.dev.cache_path)
    if not cache_exists:
        checks.append(
            _ok("bare cache repo", "Development cache repository is missing.")
        )
        operations.append(
            AttachOperation(
                "create_cache",
                f"Create bare cache repository at {project_config.dev.cache_path}.",
            )
        )
        operations.append(
            AttachOperation(
                "seed_cache_branch",
                f"Push origin/{branch} to cache branch {branch}.",
            )
        )
    else:
        cache_bare = _remote_git_check(
            project_config,
            project_config.dev.cache_path,
            ["rev-parse", "--is-bare-repository"],
        )
        if cache_bare.returncode != 0 or cache_bare.stdout.strip() != "true":
            checks.append(
                _error(
                    "bare cache repo",
                    f"Cache path is not a bare git repository: {_command_error_message(cache_bare)}",
                    next_action="Move the existing path or configure a bare cache repository path.",
                )
            )
        else:
            checks.append(_ok("bare cache repo", "Cache repository is bare."))
            cache_branch = _remote_git_check(
                project_config,
                project_config.dev.cache_path,
                ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            )
            if cache_branch.returncode == 1:
                operations.append(
                    AttachOperation(
                        "seed_cache_branch",
                        f"Push origin/{branch} to cache branch {branch}.",
                    )
                )
            elif cache_branch.returncode != 0:
                raise _as_command_error(cache_branch)

    gitsync = _remote_git_check(
        project_config, project_config.dev.work_path, ["remote", "get-url", "gitsync"]
    )
    if (
        gitsync.returncode == 0
        and gitsync.stdout.strip() == project_config.dev.cache_path
    ):
        checks.append(_ok("gitsync remote", "gitsync remote matches cache path."))
    elif gitsync.returncode == 0:
        checks.append(
            _ok(
                "gitsync remote",
                f"gitsync remote will be updated from {gitsync.stdout.strip()}.",
            )
        )
        operations.append(
            AttachOperation(
                "update_gitsync_remote",
                f"Set gitsync remote URL to {project_config.dev.cache_path}.",
            )
        )
    else:
        checks.append(_ok("gitsync remote", "gitsync remote is missing."))
        operations.append(
            AttachOperation(
                "add_gitsync_remote",
                f"Add gitsync remote pointing to {project_config.dev.cache_path}.",
            )
        )

    return AttachPlan(project, branch, tuple(checks), tuple(operations))


def print_attach_plan(plan: AttachPlan) -> None:
    """Print an attach preflight and repair plan."""
    console.print(f"Attach plan for [bold]{escape(plan.project)}[/bold]")
    console.print(f"Branch: {escape(plan.branch)}")
    console.print()

    table = Table(show_header=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Message", overflow="fold")
    table.add_column("Next action", overflow="fold")

    styles = {"ok": "[green]ok[/green]", "error": "[red]error[/red]"}
    for check in plan.checks:
        table.add_row(
            styles[check.status],
            escape(check.name),
            escape(check.message),
            escape(check.next_action or ""),
        )
    console.print(table)

    console.print()
    if plan.operations:
        console.print("[bold]Planned operations[/bold]")
        for operation in plan.operations:
            console.print(f"- {escape(operation.description)}")
    else:
        console.print("No repair operations needed.")


def _apply_operation(
    project_config: ProjectConfig,
    local_path: Path,
    branch: str,
    operation: AttachOperation,
) -> None:
    if operation.kind == "create_cache":
        ssh.remote_mkdir(
            project_config.dev.host,
            ssh.remote_parent(project_config.dev.cache_path, project_config.dev.os),
            user=project_config.dev.user,
            remote_os=project_config.dev.os,
        )
        ssh.run_remote_command(
            project_config.dev.host,
            ["git", "init", "--bare", project_config.dev.cache_path],
            user=project_config.dev.user,
            remote_os=project_config.dev.os,
        )
        return

    if operation.kind == "seed_cache_branch":
        cache_url = ssh.remote_git_url(
            host=project_config.dev.host,
            user=project_config.dev.user,
            repo_path=project_config.dev.cache_path,
            remote_os=project_config.dev.os,
        )
        git.push(
            cache_url,
            [f"refs/remotes/origin/{branch}:refs/heads/{branch}"],
            cwd=local_path,
            env=ssh.git_ssh_environment(project_config.dev.os),
        )
        return

    if operation.kind == "add_gitsync_remote":
        ssh.run_remote_git(
            project_config.dev.host,
            project_config.dev.work_path,
            ["remote", "add", "gitsync", project_config.dev.cache_path],
            user=project_config.dev.user,
            remote_os=project_config.dev.os,
        )
        return

    if operation.kind == "update_gitsync_remote":
        ssh.run_remote_git(
            project_config.dev.host,
            project_config.dev.work_path,
            ["remote", "set-url", "gitsync", project_config.dev.cache_path],
            user=project_config.dev.user,
            remote_os=project_config.dev.os,
        )


def _apply_plan(project_config: ProjectConfig, plan: AttachPlan) -> None:
    local_path = Path(project_config.local.repo_path)
    for operation in plan.operations:
        logger.info(f"Applying attach operation: {operation.kind}")
        _apply_operation(project_config, local_path, plan.branch, operation)


def attach_project(
    project: str,
    *,
    yes: bool = False,
    dry_run: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> None:
    """Inspect and attach existing repositories to a configured project."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    plan = inspect_project_attach(project, project_config)
    print_attach_plan(plan)

    if plan.has_errors:
        raise AttachError("Attach preflight failed. See diagnostics above.")
    if dry_run or not plan.operations:
        return
    if not yes:
        if confirm is None or not confirm(f"Apply attach operations for '{project}'?"):
            raise AttachError("Aborted.")
    _apply_plan(project_config, plan)


def repair_project(
    project: str,
    *,
    yes: bool = False,
    dry_run: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> None:
    """Repair missing or mismatched attach wiring for a configured project."""
    attach_project(project, yes=yes, dry_run=dry_run, confirm=confirm)
