"""Branch state inspection workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape
from rich.table import Table

from git_ssh_sync import git, ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.status import _ssh_repo_url


class BranchError(RuntimeError):
    """Raised when branch state cannot be inspected."""


@dataclass(frozen=True)
class BranchRow:
    """Single branch status row."""

    name: str
    in_origin: bool
    in_cache: bool
    in_work: bool
    is_current: bool
    origin_ahead: int | None
    work_ahead: int | None


@dataclass(frozen=True)
class BranchReport:
    """Collected branch status for a configured project."""

    project: str
    current_branch: str
    rows: tuple[BranchRow, ...]


def _clean_output(value: str) -> str:
    return value.strip()


def _split_lines(output: str) -> set[str]:
    return {line.strip() for line in output.splitlines() if line.strip()}


def _branch_names_from_refs(output: str, prefix: str) -> set[str]:
    names: set[str] = set()
    for line in output.splitlines():
        ref = line.strip()
        if ref.startswith(prefix):
            names.add(ref.removeprefix(prefix))
    return names


def _local_origin_branches(local_path: Path) -> set[str]:
    result = git.run_git(
        ["for-each-ref", "--format=%(refname)", "refs/remotes/origin"],
        cwd=local_path,
    )
    return _branch_names_from_refs(result.stdout, "refs/remotes/origin/") - {"HEAD"}


def _remote_cache_branches(project_config: ProjectConfig) -> set[str]:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.cache_path,
        ["for-each-ref", "--format=%(refname)", "refs/heads"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    return _branch_names_from_refs(result.stdout, "refs/heads/")


def _remote_work_branches(project_config: ProjectConfig) -> set[str]:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["for-each-ref", "--format=%(refname)", "refs/heads"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    return _branch_names_from_refs(result.stdout, "refs/heads/")


def _remote_current_branch(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["branch", "--show-current"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    branch = _clean_output(result.stdout)
    if not branch:
        raise BranchError("Development work repository is in detached HEAD state.")
    return branch


def _split_ahead_counts(output: str) -> tuple[int, int]:
    parts = output.split()
    if len(parts) != 2:
        raise BranchError(f"Unexpected rev-list output: {output.strip()}")
    return int(parts[0]), int(parts[1])


def _ahead_counts(local_path: Path, branch: str) -> tuple[int | None, int | None]:
    result = git.rev_list(
        ["--left-right", "--count", f"origin/{branch}...dev/{branch}"],
        cwd=local_path,
    )
    return _split_ahead_counts(result.stdout)


def inspect_branch(project: str) -> BranchReport:
    """Inspect branch state for a configured project."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    return inspect_project_branch(project, project_config)


def inspect_project_branch(project: str, project_config: ProjectConfig) -> BranchReport:
    """Inspect branch state using an already loaded project configuration."""
    local_path = Path(project_config.local.repo_path)
    if not local_path.exists():
        raise BranchError(f"[local] gateway repository does not exist: {local_path}")

    git.fetch("origin", cwd=local_path)
    current_branch = _remote_current_branch(project_config)
    origin_branches = _local_origin_branches(local_path)
    cache_branches = _remote_cache_branches(project_config)
    work_branches = _remote_work_branches(project_config)

    dev_repo_url = _ssh_repo_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        repo_path=project_config.dev.work_path,
        remote_os=project_config.dev.os,
    )
    for branch in sorted(origin_branches & work_branches):
        git.fetch(
            dev_repo_url,
            [f"refs/heads/{branch}:refs/remotes/dev/{branch}"],
            cwd=local_path,
        )

    rows: list[BranchRow] = []
    for branch in sorted(origin_branches | cache_branches | work_branches):
        origin_ahead: int | None = None
        work_ahead: int | None = None
        if branch in origin_branches and branch in work_branches:
            origin_ahead, work_ahead = _ahead_counts(local_path, branch)
        rows.append(
            BranchRow(
                name=branch,
                in_origin=branch in origin_branches,
                in_cache=branch in cache_branches,
                in_work=branch in work_branches,
                is_current=branch == current_branch,
                origin_ahead=origin_ahead,
                work_ahead=work_ahead,
            )
        )
    return BranchReport(
        project=project, current_branch=current_branch, rows=tuple(rows)
    )


def _mark(value: bool) -> str:
    return "yes" if value else "-"


def _ahead(value: int | None) -> str:
    return "-" if value is None else str(value)


def print_branch(report: BranchReport) -> None:
    """Print a Rich-formatted branch report."""
    console.print(f"Branches for [bold]{escape(report.project)}[/bold]")
    console.print(f"Current branch: {escape(report.current_branch)}")
    console.print()

    table = Table(show_header=True)
    table.add_column("Branch", style="bold")
    table.add_column("Current", no_wrap=True)
    table.add_column("Origin", no_wrap=True)
    table.add_column("Dev cache", no_wrap=True)
    table.add_column("Work repo", no_wrap=True)
    table.add_column("Origin ahead", justify="right", no_wrap=True)
    table.add_column("Work ahead", justify="right", no_wrap=True)

    for row in report.rows:
        table.add_row(
            escape(row.name),
            "*" if row.is_current else "",
            _mark(row.in_origin),
            _mark(row.in_cache),
            _mark(row.in_work),
            _ahead(row.origin_ahead),
            _ahead(row.work_ahead),
        )
    console.print(table)


def branch_project(project: str) -> None:
    """Inspect and print branch state for a configured project."""
    print_branch(inspect_branch(project))
