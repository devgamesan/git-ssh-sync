"""Safe pull and checkout workflows."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from git_ssh_sync import git, ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.errors import CommandExecutionError


class SyncError(RuntimeError):
    """Raised when a sync workflow stops for a recoverable safety reason."""


def _cache_url(*, host: str, user: str, cache_path: str) -> str:
    quoted_path = quote(cache_path, safe="/~")
    return f"ssh://{user}@{host}{quoted_path}"


def _clean_output(value: str) -> str:
    return value.strip()


def _branch_or_default(project_config: ProjectConfig, branch: str | None) -> str:
    return branch or project_config.default_branch


def _ensure_gateway_repo(path: Path) -> None:
    if not path.exists():
        raise SyncError(f"[local] gateway repository does not exist: {path}")


def _ensure_origin_branch(local_path: Path, branch: str) -> None:
    result = git.rev_parse(["--verify", f"refs/remotes/origin/{branch}"], cwd=local_path, check=False)
    if result.returncode == 0:
        return
    if result.returncode == 1:
        raise SyncError(
            f"Origin branch does not exist: {branch}\n\n"
            "Run on the gateway repository:\n\n"
            "  git fetch origin"
        )
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _push_origin_branch_to_cache(project_config: ProjectConfig, local_path: Path, branch: str) -> None:
    remote_cache = _cache_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        cache_path=project_config.dev.cache_path,
    )
    git.push(remote_cache, [f"refs/remotes/origin/{branch}:refs/heads/{branch}"], cwd=local_path)


def _fetch_dev_branch(project_config: ProjectConfig, branch: str) -> None:
    ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["fetch", "gitsync", f"refs/heads/{branch}:refs/remotes/gitsync/{branch}"],
        user=project_config.dev.user,
    )


def _remote_branch_exists(project_config: ProjectConfig, branch: str) -> bool:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["rev-parse", "--verify", f"refs/heads/{branch}"],
        user=project_config.dev.user,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _remote_current_branch(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["branch", "--show-current"],
        user=project_config.dev.user,
    )
    return _clean_output(result.stdout) or "(detached)"


def _remote_short_head(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["rev-parse", "--short", "HEAD"],
        user=project_config.dev.user,
    )
    return _clean_output(result.stdout)


def _remote_status(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["status", "--porcelain"],
        user=project_config.dev.user,
    )
    return _clean_output(result.stdout)


def _dirty_error(project: str, project_config: ProjectConfig) -> SyncError:
    return SyncError(
        "Error: Development working tree is dirty.\n\n"
        f"Project:\n  {project}\n\n"
        "Development:\n"
        f"  host: {project_config.dev.host}\n"
        f"  path: {project_config.dev.work_path}\n"
        f"  branch: {_remote_current_branch(project_config)}\n"
        f"  commit: {_remote_short_head(project_config)}\n\n"
        "Commit or stash changes first."
    )


def _ensure_dev_clean(project: str, project_config: ProjectConfig) -> None:
    if _remote_status(project_config):
        raise _dirty_error(project, project_config)


def _switch_to_branch(project_config: ProjectConfig, branch: str) -> None:
    if _remote_branch_exists(project_config, branch):
        ssh.run_remote_git(
            project_config.dev.host,
            project_config.dev.work_path,
            ["switch", branch],
            user=project_config.dev.user,
        )
        return

    ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["switch", "--track", "-c", branch, f"gitsync/{branch}"],
        user=project_config.dev.user,
    )


def _ensure_fast_forwardable(project: str, project_config: ProjectConfig, branch: str) -> None:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["merge-base", "--is-ancestor", f"refs/heads/{branch}", f"refs/remotes/gitsync/{branch}"],
        user=project_config.dev.user,
        check=False,
    )
    if result.returncode == 0:
        return
    if result.returncode == 1:
        current_branch = _remote_current_branch(project_config)
        current_commit = _remote_short_head(project_config)
        raise SyncError(
            f"Cannot fast-forward {branch}.\n\n"
            f"origin/{branch} and dev/{branch} have diverged.\n\n"
            f"Project:\n  {project}\n\n"
            "Development:\n"
            f"  host: {project_config.dev.host}\n"
            f"  path: {project_config.dev.work_path}\n"
            f"  branch: {current_branch}\n"
            f"  commit: {current_commit}\n\n"
            "Resolve on the development environment:\n\n"
            "  git fetch gitsync\n"
            f"  git merge gitsync/{branch}\n\n"
            "or:\n\n"
            f"  git rebase gitsync/{branch}"
        )
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _load_project(project: str) -> ProjectConfig:
    return get_project(load_config(), project)


def pull_project(project: str, branch: str | None = None) -> None:
    """Fetch origin changes and fast-forward the development repository."""
    project_config = _load_project(project)
    selected_branch = _branch_or_default(project_config, branch)
    local_path = Path(project_config.local.repo_path)

    _ensure_gateway_repo(local_path)
    git.fetch("origin", cwd=local_path)
    _ensure_origin_branch(local_path, selected_branch)
    _push_origin_branch_to_cache(project_config, local_path, selected_branch)
    _fetch_dev_branch(project_config, selected_branch)

    if _remote_branch_exists(project_config, selected_branch):
        _ensure_fast_forwardable(project, project_config, selected_branch)
        _switch_to_branch(project_config, selected_branch)
        ssh.run_remote_git(
            project_config.dev.host,
            project_config.dev.work_path,
            ["merge", "--ff-only", f"gitsync/{selected_branch}"],
            user=project_config.dev.user,
        )
        return

    _ensure_dev_clean(project, project_config)
    _switch_to_branch(project_config, selected_branch)


def checkout_project(project: str, branch: str) -> None:
    """Switch the development repository to a branch from origin."""
    project_config = _load_project(project)
    local_path = Path(project_config.local.repo_path)

    _ensure_gateway_repo(local_path)
    git.fetch("origin", cwd=local_path)
    _ensure_origin_branch(local_path, branch)
    _push_origin_branch_to_cache(project_config, local_path, branch)
    _fetch_dev_branch(project_config, branch)
    _ensure_dev_clean(project, project_config)
    _switch_to_branch(project_config, branch)
