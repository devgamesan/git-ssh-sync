"""Project status inspection workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from rich.markup import escape
from rich.table import Table

from git_ssh_sync import git, ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.errors import CommandExecutionError


class StatusError(RuntimeError):
    """Raised when project status cannot be inspected."""


@dataclass(frozen=True)
class StatusReport:
    """Collected synchronization status for a configured project."""

    project: str
    origin_url: str
    branch: str
    origin_head: str
    dev_host: str
    dev_work_path: str
    dev_branch: str
    dev_head: str
    dev_working_tree_clean: bool
    origin_ahead: int
    dev_ahead: int
    uses_lfs: bool
    uses_submodules: bool


def _ssh_repo_url(*, host: str, user: str, repo_path: str) -> str:
    quoted_path = quote(repo_path, safe="/~")
    return f"ssh://{user}@{host}{quoted_path}"


def _clean_output(value: str) -> str:
    return value.strip()


def _ensure_remote_work_repo(*, host: str, user: str, path: str) -> None:
    result = ssh.run_ssh(host, ["test", "-d", path], user=user, check=False)
    if result.returncode == 0:
        return
    if result.returncode == 1:
        raise StatusError(f"[{result.environment}] work repository does not exist: {path}")
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _split_ahead_counts(output: str) -> tuple[int, int]:
    parts = output.split()
    if len(parts) != 2:
        raise StatusError(f"Unexpected rev-list output: {output.strip()}")
    return int(parts[0]), int(parts[1])


def _uses_lfs(local_path: Path) -> bool:
    result = git.run_git(["lfs", "ls-files"], cwd=local_path, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return True

    attributes_path = local_path / ".gitattributes"
    if not attributes_path.exists():
        return False
    return "filter=lfs" in attributes_path.read_text(encoding="utf-8")


def _uses_submodules(local_path: Path) -> bool:
    return (local_path / ".gitmodules").exists()


def inspect_status(project: str) -> StatusReport:
    """Inspect configured origin and development repository status."""
    app_config = load_config()
    project_config = get_project(app_config, project)
    return inspect_project_status(project, project_config)


def inspect_project_status(project: str, project_config: ProjectConfig) -> StatusReport:
    """Inspect a project using an already loaded configuration."""
    local_path = Path(project_config.local.repo_path)
    branch = project_config.default_branch
    dev_host = project_config.dev.host
    dev_user = project_config.dev.user
    dev_work_path = project_config.dev.work_path

    if not local_path.exists():
        raise StatusError(f"[local] gateway repository does not exist: {local_path}")

    git.fetch("origin", cwd=local_path)
    ssh.run_ssh(dev_host, ["true"], user=dev_user)
    _ensure_remote_work_repo(host=dev_host, user=dev_user, path=dev_work_path)

    dev_repo_url = _ssh_repo_url(host=dev_host, user=dev_user, repo_path=dev_work_path)
    git.fetch(dev_repo_url, [f"refs/heads/{branch}:refs/remotes/dev/{branch}"], cwd=local_path)

    origin_ref = f"origin/{branch}"
    dev_ref = f"dev/{branch}"
    origin_head = _clean_output(git.log_oneline(origin_ref, cwd=local_path).stdout)
    dev_head = _clean_output(git.log_oneline(dev_ref, cwd=local_path).stdout)

    dev_branch = _clean_output(
        ssh.run_remote_git(dev_host, dev_work_path, ["branch", "--show-current"], user=dev_user).stdout
    )
    remote_head = _clean_output(
        ssh.run_remote_git(dev_host, dev_work_path, ["log", "-1", "--format=%h %s"], user=dev_user).stdout
    )
    remote_status = ssh.run_remote_git(dev_host, dev_work_path, ["status", "--porcelain"], user=dev_user)
    origin_ahead, dev_ahead = _split_ahead_counts(
        git.rev_list(["--left-right", "--count", f"{origin_ref}...{dev_ref}"], cwd=local_path).stdout
    )

    return StatusReport(
        project=project,
        origin_url=project_config.origin,
        branch=branch,
        origin_head=origin_head,
        dev_host=dev_host,
        dev_work_path=dev_work_path,
        dev_branch=dev_branch,
        dev_head=remote_head or dev_head,
        dev_working_tree_clean=not remote_status.stdout.strip(),
        origin_ahead=origin_ahead,
        dev_ahead=dev_ahead,
        uses_lfs=_uses_lfs(local_path),
        uses_submodules=_uses_submodules(local_path),
    )


def _recommendation(report: StatusReport) -> str:
    if not report.dev_working_tree_clean:
        return "Commit or stash changes on the development environment."
    if report.origin_ahead and report.dev_ahead:
        return f"git-ssh-sync pull {report.project} --branch {report.branch}, then resolve divergence on the development environment."
    if report.origin_ahead:
        return f"git-ssh-sync pull {report.project} --branch {report.branch}"
    if report.dev_ahead:
        return f"git-ssh-sync push {report.project} --branch {report.branch}"
    return "No action needed."


def _state_lines(report: StatusReport) -> list[str]:
    lines = [
        f"dev is ahead of origin by {report.dev_ahead} commits",
        f"origin is ahead of dev by {report.origin_ahead} commits",
    ]
    if not report.dev_working_tree_clean:
        lines.append("development working tree is dirty")
    return lines


def print_status(report: StatusReport) -> None:
    """Print a Rich-formatted status report."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("section", style="bold")
    table.add_column("field")
    table.add_column("value")

    table.add_row("Project", "name", escape(report.project))
    table.add_row("", "", "")
    table.add_row("Origin", "url", escape(report.origin_url))
    table.add_row("", "branch", escape(report.branch))
    table.add_row("", "head", escape(report.origin_head))
    table.add_row("", "", "")
    table.add_row("Development", "host", escape(report.dev_host))
    table.add_row("", "work path", escape(report.dev_work_path))
    table.add_row("", "branch", escape(report.dev_branch))
    table.add_row("", "head", escape(report.dev_head))
    table.add_row("", "working tree", "clean" if report.dev_working_tree_clean else "[yellow]dirty[/yellow]")
    table.add_row("", "", "")
    for index, line in enumerate(_state_lines(report)):
        table.add_row("State" if index == 0 else "", "", escape(line))
    table.add_row("", "", "")
    table.add_row("Recommendation", "", escape(_recommendation(report)))
    console.print(table)

    if report.uses_lfs or report.uses_submodules:
        console.print()
    if report.uses_lfs:
        console.print("[yellow]This repository appears to use Git LFS.[/yellow]")
        console.print("Git LFS object synchronization is not supported in v0.1.")
        console.print("Normal Git commits may sync, but LFS file contents may be missing.")
    if report.uses_submodules:
        console.print("[yellow]This repository uses Git submodules.[/yellow]")
        console.print("Submodule synchronization is not supported in v0.1.")
        console.print("Register each submodule as a separate git-ssh-sync project.")


def status_project(project: str) -> None:
    """Inspect and print status for a configured project."""
    print_status(inspect_status(project))
