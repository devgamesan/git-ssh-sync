"""Project clone workflow."""

from __future__ import annotations

import shutil
from pathlib import Path

from git_ssh_sync import git, ssh
from git_ssh_sync.config import get_project, load_config
from git_ssh_sync.errors import CommandExecutionError, format_recovery
from git_ssh_sync.logging_config import logger


class CloneError(RuntimeError):
    """Raised when the clone workflow would overwrite existing data."""


def _path_exists_recovery(project: str) -> str:
    return format_recovery(
        f"Run `git-ssh-sync attach {project} --dry-run` if the existing repositories should be reused.",
        "Move or delete the existing path if you want to recreate the project from scratch.",
        f"Run `git-ssh-sync config set {project} ...` if the configured path is wrong.",
    )


def _ensure_local_missing(project: str, path: Path) -> None:
    if path.exists():
        raise CloneError(
            f"[local] path already exists: {path}\n\n{_path_exists_recovery(project)}"
        )


def _ensure_remote_missing(
    *, project: str, host: str, user: str, path: str, remote_os: ssh.RemoteOS
) -> None:
    result = ssh.remote_path_exists(
        host, path, user=user, remote_os=remote_os, path_type="any"
    )
    if result.returncode == 0:
        raise CloneError(
            f"[{result.environment}] path already exists: {path}\n\n"
            f"{_path_exists_recovery(project)}"
        )
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


def _local_current_branch(local_path: Path) -> str:
    result = git.run_git(["branch", "--show-current"], cwd=local_path)
    branch = result.stdout.strip()
    if not branch:
        raise CloneError("Could not determine the cloned repository's current branch.")
    return branch


def _cleanup_local_path(path: Path) -> None:
    if not path.exists():
        return
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
            return
        path.unlink()
    except OSError as error:
        logger.debug("Failed to clean up local path %s: %s", path, error)


def _cleanup_remote_path(
    *, host: str, user: str, path: str, remote_os: ssh.RemoteOS
) -> None:
    result = ssh.remote_remove(host, path, user=user, remote_os=remote_os)
    if result.returncode != 0:
        logger.debug(
            "Failed to clean up remote path %s on %s: %s",
            path,
            result.environment,
            result.stderr.strip(),
        )


def clone_project(project: str) -> None:
    """Clone a configured project and initialize its development repositories."""
    app_config = load_config()
    project_config = get_project(app_config, project)

    local_path = Path(project_config.local.repo_path)
    dev_host = project_config.dev.host
    dev_user = project_config.dev.user
    dev_os = project_config.dev.os
    cache_path = project_config.dev.cache_path
    work_path = project_config.dev.work_path

    _ensure_local_missing(project, local_path)
    _ensure_remote_missing(
        project=project,
        host=dev_host,
        user=dev_user,
        path=cache_path,
        remote_os=dev_os,
    )
    _ensure_remote_missing(
        project=project,
        host=dev_host,
        user=dev_user,
        path=work_path,
        remote_os=dev_os,
    )

    local_started = False
    cache_started = False
    work_started = False
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_started = True
        git.run_git(["clone", project_config.origin, str(local_path)])
        git.fetch("origin", cwd=local_path)
        branch = _local_current_branch(local_path)

        ssh.remote_mkdir(
            dev_host,
            ssh.remote_parent(cache_path, dev_os),
            user=dev_user,
            remote_os=dev_os,
        )
        cache_started = True
        ssh.run_remote_command(
            dev_host,
            ["git", "init", "--bare", cache_path],
            user=dev_user,
            remote_os=dev_os,
        )

        remote_cache = ssh.remote_git_url(
            host=dev_host, user=dev_user, repo_path=cache_path, remote_os=dev_os
        )
        git.push(
            remote_cache,
            [f"refs/remotes/origin/{branch}:refs/heads/{branch}"],
            cwd=local_path,
            env=ssh.git_ssh_environment(dev_os),
        )
        if project_config.options.sync_tags:
            git.push(
                remote_cache,
                ["--tags"],
                cwd=local_path,
                env=ssh.git_ssh_environment(dev_os),
            )

        ssh.remote_mkdir(
            dev_host,
            ssh.remote_parent(work_path, dev_os),
            user=dev_user,
            remote_os=dev_os,
        )
        work_started = True
        ssh.run_remote_command(
            dev_host,
            ["git", "clone", cache_path, work_path],
            user=dev_user,
            remote_os=dev_os,
        )
        ssh.run_remote_git(
            dev_host,
            work_path,
            ["remote", "rename", "origin", "gitsync"],
            user=dev_user,
            remote_os=dev_os,
        )
        ssh.run_remote_git(
            dev_host, work_path, ["switch", branch], user=dev_user, remote_os=dev_os
        )
    except Exception:
        if work_started:
            _cleanup_remote_path(
                host=dev_host, user=dev_user, path=work_path, remote_os=dev_os
            )
        if cache_started:
            _cleanup_remote_path(
                host=dev_host, user=dev_user, path=cache_path, remote_os=dev_os
            )
        if local_started:
            _cleanup_local_path(local_path)
        raise
