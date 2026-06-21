"""Project clone workflow."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from git_ssh_sync import git, ssh
from git_ssh_sync.config import get_project, load_config
from git_ssh_sync.errors import CommandExecutionError


class CloneError(RuntimeError):
    """Raised when the clone workflow would overwrite existing data."""


def _cache_url(*, host: str, user: str, cache_path: str) -> str:
    quoted_path = quote(cache_path, safe="/~")
    return f"ssh://{user}@{host}{quoted_path}"


def _ensure_local_missing(path: Path) -> None:
    if path.exists():
        raise CloneError(f"[local] path already exists: {path}")


def _ensure_remote_missing(*, host: str, user: str, path: str) -> None:
    result = ssh.run_ssh(host, ["test", "-e", path], user=user, check=False)
    if result.returncode == 0:
        raise CloneError(f"[{result.environment}] path already exists: {path}")
    if result.returncode == 1:
        return
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _remote_parent(path: str) -> str:
    return str(Path(path).parent)


def clone_project(project: str) -> None:
    """Clone a configured project and initialize its development repositories."""
    app_config = load_config()
    project_config = get_project(app_config, project)

    local_path = Path(project_config.local.repo_path)
    dev_host = project_config.dev.host
    dev_user = project_config.dev.user
    cache_path = project_config.dev.cache_path
    work_path = project_config.dev.work_path
    branch = project_config.default_branch

    _ensure_local_missing(local_path)
    _ensure_remote_missing(host=dev_host, user=dev_user, path=cache_path)
    _ensure_remote_missing(host=dev_host, user=dev_user, path=work_path)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    git.run_git(["clone", project_config.origin, str(local_path)])
    git.fetch("origin", cwd=local_path)

    ssh.run_ssh(dev_host, ["mkdir", "-p", _remote_parent(cache_path)], user=dev_user)
    ssh.run_ssh(dev_host, ["git", "init", "--bare", cache_path], user=dev_user)

    remote_cache = _cache_url(host=dev_host, user=dev_user, cache_path=cache_path)
    git.push(
        remote_cache,
        [f"refs/remotes/origin/{branch}:refs/heads/{branch}"],
        cwd=local_path,
    )
    if project_config.options.sync_tags:
        git.push(remote_cache, ["--tags"], cwd=local_path)

    ssh.run_ssh(dev_host, ["mkdir", "-p", _remote_parent(work_path)], user=dev_user)
    ssh.run_ssh(dev_host, ["git", "clone", cache_path, work_path], user=dev_user)
    ssh.run_remote_git(
        dev_host, work_path, ["remote", "rename", "origin", "gitsync"], user=dev_user
    )
    ssh.run_remote_git(dev_host, work_path, ["switch", branch], user=dev_user)
