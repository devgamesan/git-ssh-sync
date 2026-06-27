"""Branch state inspection workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape
from rich.table import Table

from git_ssh_sync import git, ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.errors import format_recovery
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


@dataclass(frozen=True)
class BranchDeletion:
    """Single branch ref planned for deletion."""

    location: str
    ref: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class BranchCleanupPlan:
    """Collected branch cleanup operations for a configured project."""

    project: str
    branch: str | None
    mode: str
    current_branch: str
    deletions: tuple[BranchDeletion, ...]


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


def _local_dev_branches(local_path: Path) -> set[str]:
    result = git.run_git(
        ["for-each-ref", "--format=%(refname)", "refs/remotes/dev"],
        cwd=local_path,
    )
    return _branch_names_from_refs(result.stdout, "refs/remotes/dev/") - {"HEAD"}


def _origin_remote_branches(local_path: Path) -> set[str]:
    result = git.run_git(
        ["ls-remote", "--heads", "origin"],
        cwd=local_path,
    )
    names: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            names.add(parts[1].removeprefix("refs/heads/"))
    return names


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


def _detached_head_recovery(project: str) -> str:
    return format_recovery(
        f"`git-ssh-sync branch {project}` to inspect branch refs.",
        f"`git-ssh-sync checkout {project} <branch>` to reattach the development work repo.",
    )


def _missing_gateway_recovery(project: str) -> str:
    return format_recovery(
        f"`git-ssh-sync doctor {project}` for a full diagnosis.",
        f"`git-ssh-sync clone {project}` if the gateway repository needs to be created.",
        f"`git-ssh-sync config set {project} ...` if the configured local path is wrong.",
    )


def _current_branch_delete_recovery(project: str) -> str:
    return format_recovery(
        f"`git-ssh-sync checkout {project} <branch>` to switch to another branch before deletion.",
        f"`git-ssh-sync branch {project}` to inspect branch refs before deleting.",
    )


def _no_delete_refs_recovery(project: str) -> str:
    return format_recovery(
        f"`git-ssh-sync branch {project}` to inspect available refs.",
        "Check the branch name and try the delete command again.",
    )


def _remote_current_branch(project: str, project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["branch", "--show-current"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    branch = _clean_output(result.stdout)
    if not branch:
        raise BranchError(
            "Development work repository is in detached HEAD state.\n\n"
            f"{_detached_head_recovery(project)}"
        )
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
        raise BranchError(
            f"[local] gateway repository does not exist: {local_path}\n\n"
            f"{_missing_gateway_recovery(project)}"
        )

    git.fetch("origin", cwd=local_path)
    current_branch = _remote_current_branch(project, project_config)
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
            env=ssh.git_ssh_environment(project_config.dev.os),
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


def _print_cleanup_plan(plan: BranchCleanupPlan, *, dry_run: bool) -> None:
    mode = "dry-run" if dry_run else "apply"
    console.print(f"Branch cleanup for [bold]{escape(plan.project)}[/bold]")
    console.print(f"Mode: {mode}")
    console.print(f"Current branch: {escape(plan.current_branch)}")
    if plan.branch is not None:
        console.print(f"Target branch: {escape(plan.branch)}")
    console.print()

    if not plan.deletions:
        console.print("No branch refs to delete.")
        return

    table = Table(show_header=True)
    table.add_column("Location", no_wrap=True)
    table.add_column("Ref")
    table.add_column("Command")
    for deletion in plan.deletions:
        table.add_row(
            escape(deletion.location),
            escape(deletion.ref),
            escape(" ".join(deletion.command)),
        )
    console.print(table)


def _delete_origin_branch(local_path: Path, branch: str) -> None:
    git.push("origin", [f":refs/heads/{branch}"], cwd=local_path)


def _delete_gateway_ref(local_path: Path, ref: str) -> None:
    git.run_git(["update-ref", "-d", ref], cwd=local_path)


def _delete_remote_branch(
    project_config: ProjectConfig, repo_path: str, branch: str
) -> None:
    ssh.run_remote_git(
        project_config.dev.host,
        repo_path,
        ["branch", "-D", branch],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )


def _build_delete_plan(
    project: str, project_config: ProjectConfig, branch: str
) -> BranchCleanupPlan:
    local_path = Path(project_config.local.repo_path)
    if not local_path.exists():
        raise BranchError(
            f"[local] gateway repository does not exist: {local_path}\n\n"
            f"{_missing_gateway_recovery(project)}"
        )

    git.fetch("origin", cwd=local_path)
    current_branch = _remote_current_branch(project, project_config)
    if branch == current_branch:
        raise BranchError(
            f"Cannot delete the current development branch: {branch}\n\n"
            f"{_current_branch_delete_recovery(project)}"
        )

    origin_branches = _origin_remote_branches(local_path)
    gateway_origin_branches = _local_origin_branches(local_path)
    gateway_dev_branches = _local_dev_branches(local_path)
    cache_branches = _remote_cache_branches(project_config)
    work_branches = _remote_work_branches(project_config)

    deletions: list[BranchDeletion] = []
    if branch in origin_branches:
        deletions.append(
            BranchDeletion(
                location="origin",
                ref=f"refs/heads/{branch}",
                command=("git", "push", "origin", f":refs/heads/{branch}"),
            )
        )
    if branch in cache_branches:
        deletions.append(
            BranchDeletion(
                location="dev cache",
                ref=f"refs/heads/{branch}",
                command=(
                    "git",
                    "-C",
                    project_config.dev.cache_path,
                    "branch",
                    "-D",
                    branch,
                ),
            )
        )
    if branch in work_branches:
        deletions.append(
            BranchDeletion(
                location="work repo",
                ref=f"refs/heads/{branch}",
                command=(
                    "git",
                    "-C",
                    project_config.dev.work_path,
                    "branch",
                    "-D",
                    branch,
                ),
            )
        )
    if branch in gateway_origin_branches:
        ref = f"refs/remotes/origin/{branch}"
        deletions.append(
            BranchDeletion(
                location="gateway origin ref",
                ref=ref,
                command=("git", "update-ref", "-d", ref),
            )
        )
    if branch in gateway_dev_branches:
        ref = f"refs/remotes/dev/{branch}"
        deletions.append(
            BranchDeletion(
                location="gateway dev ref",
                ref=ref,
                command=("git", "update-ref", "-d", ref),
            )
        )

    if not deletions:
        raise BranchError(
            f"No branch refs found for deletion: {branch}\n\n"
            f"{_no_delete_refs_recovery(project)}"
        )

    return BranchCleanupPlan(
        project=project,
        branch=branch,
        mode="delete",
        current_branch=current_branch,
        deletions=tuple(deletions),
    )


def _build_prune_plan(project: str, project_config: ProjectConfig) -> BranchCleanupPlan:
    local_path = Path(project_config.local.repo_path)
    if not local_path.exists():
        raise BranchError(
            f"[local] gateway repository does not exist: {local_path}\n\n"
            f"{_missing_gateway_recovery(project)}"
        )

    git.fetch("origin", cwd=local_path)
    current_branch = _remote_current_branch(project, project_config)
    origin_branches = _origin_remote_branches(local_path)
    gateway_origin_branches = _local_origin_branches(local_path)
    gateway_dev_branches = _local_dev_branches(local_path)
    cache_branches = _remote_cache_branches(project_config)
    work_branches = _remote_work_branches(project_config)

    stale_cache_branches = cache_branches - origin_branches - {current_branch}
    stale_work_branches = work_branches - origin_branches - {current_branch}
    stale_gateway_origin_branches = (
        gateway_origin_branches - origin_branches - {current_branch}
    )
    stale_gateway_dev_branches = (
        gateway_dev_branches - origin_branches - {current_branch}
    )

    deletions: list[BranchDeletion] = []
    for branch in sorted(stale_cache_branches):
        deletions.append(
            BranchDeletion(
                location="dev cache",
                ref=f"refs/heads/{branch}",
                command=(
                    "git",
                    "-C",
                    project_config.dev.cache_path,
                    "branch",
                    "-D",
                    branch,
                ),
            )
        )
    for branch in sorted(stale_work_branches):
        deletions.append(
            BranchDeletion(
                location="work repo",
                ref=f"refs/heads/{branch}",
                command=(
                    "git",
                    "-C",
                    project_config.dev.work_path,
                    "branch",
                    "-D",
                    branch,
                ),
            )
        )
    for branch in sorted(stale_gateway_origin_branches):
        ref = f"refs/remotes/origin/{branch}"
        deletions.append(
            BranchDeletion(
                location="gateway origin ref",
                ref=ref,
                command=("git", "update-ref", "-d", ref),
            )
        )
    for branch in sorted(stale_gateway_dev_branches):
        ref = f"refs/remotes/dev/{branch}"
        deletions.append(
            BranchDeletion(
                location="gateway dev ref",
                ref=ref,
                command=("git", "update-ref", "-d", ref),
            )
        )

    return BranchCleanupPlan(
        project=project,
        branch=None,
        mode="prune",
        current_branch=current_branch,
        deletions=tuple(deletions),
    )


def _apply_cleanup_plan(plan: BranchCleanupPlan, project_config: ProjectConfig) -> None:
    local_path = Path(project_config.local.repo_path)
    for deletion in plan.deletions:
        if deletion.location == "origin":
            branch = deletion.ref.removeprefix("refs/heads/")
            _delete_origin_branch(local_path, branch)
        elif deletion.location == "dev cache":
            branch = deletion.ref.removeprefix("refs/heads/")
            _delete_remote_branch(project_config, project_config.dev.cache_path, branch)
        elif deletion.location == "work repo":
            branch = deletion.ref.removeprefix("refs/heads/")
            _delete_remote_branch(project_config, project_config.dev.work_path, branch)
        elif deletion.location in {"gateway origin ref", "gateway dev ref"}:
            _delete_gateway_ref(local_path, deletion.ref)
        else:
            raise BranchError(f"Unexpected deletion location: {deletion.location}")


def _cleanup_project(
    project: str,
    plan: BranchCleanupPlan,
    project_config: ProjectConfig,
    *,
    yes: bool,
    dry_run: bool,
    confirm: Callable[[str], bool] | None,
) -> None:
    _print_cleanup_plan(plan, dry_run=dry_run)
    if dry_run or not plan.deletions:
        return
    if not yes:
        if confirm is None or not confirm("Apply branch cleanup?"):
            console.print("Aborted.")
            raise BranchError("Branch cleanup aborted.")
    _apply_cleanup_plan(plan, project_config)
    console.print(f"Project '{escape(project)}' branch cleanup completed.")


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


def branch_delete_project(
    project: str,
    branch: str,
    *,
    yes: bool = False,
    dry_run: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> None:
    """Delete one branch across origin, cache, work repo, and gateway refs."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    plan = _build_delete_plan(project, project_config, branch)
    _cleanup_project(
        project,
        plan,
        project_config,
        yes=yes,
        dry_run=dry_run,
        confirm=confirm,
    )


def branch_prune_project(
    project: str,
    *,
    yes: bool = False,
    dry_run: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> None:
    """Prune refs that no longer exist on origin."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    plan = _build_prune_plan(project, project_config)
    _cleanup_project(
        project,
        plan,
        project_config,
        yes=yes,
        dry_run=dry_run,
        confirm=confirm,
    )
