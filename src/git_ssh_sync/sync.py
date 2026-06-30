"""Safe pull and checkout workflows."""

from __future__ import annotations

from pathlib import Path

from git_ssh_sync import git, ssh
from git_ssh_sync.config import ProjectConfig, get_project, load_config
from git_ssh_sync.console import console
from git_ssh_sync.errors import CommandExecutionError, format_recovery
from git_ssh_sync.logging_config import logger


class SyncError(RuntimeError):
    """Raised when a sync workflow stops for a recoverable safety reason."""


def _print_dry_run_plan(
    *,
    project: str,
    branch: str,
    direction: str,
    preflight: list[str],
    operations: list[str],
) -> None:
    console.print(f"Project: {project}")
    console.print(f"Branch: {branch}")
    console.print(f"Direction: {direction}")
    console.print("Mode: dry-run")
    console.print("Preflight:")
    for item in preflight:
        console.print(f"  - {item}")
    console.print("Planned operations:")
    for item in operations:
        console.print(f"  - {item}")


def _cache_url(
    *, host: str, user: str, cache_path: str, remote_os: ssh.RemoteOS
) -> str:
    return ssh.remote_git_url(
        host=host, user=user, repo_path=cache_path, remote_os=remote_os
    )


def _work_url(project_config: ProjectConfig) -> str:
    return ssh.remote_git_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        repo_path=project_config.dev.work_path,
        remote_os=project_config.dev.os,
    )


def _clean_output(value: str) -> str:
    return value.strip()


def _ensure_gateway_repo(path: Path) -> None:
    if not path.exists():
        raise SyncError(f"[local] gateway repository does not exist: {path}")


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
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _ensure_origin_branch(local_path: Path, branch: str) -> None:
    if not _origin_branch_exists(local_path, branch):
        raise SyncError(
            f"Origin branch does not exist: {branch}\n\n"
            "Run on the gateway repository:\n\n"
            "  git fetch origin"
        )


def _origin_branch_exists_on_remote(local_path: Path, branch: str) -> bool:
    result = git.run_git(
        ["ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=local_path,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _ensure_origin_branch_on_remote(local_path: Path, branch: str) -> None:
    if not _origin_branch_exists_on_remote(local_path, branch):
        raise SyncError(f"Origin branch does not exist: {branch}")


def _ensure_origin_branch_missing(project: str, local_path: Path, branch: str) -> None:
    if _origin_branch_exists(local_path, branch):
        raise SyncError(
            f"Origin branch already exists: {branch}\n\n"
            "Run checkout without --base to use the existing branch:\n\n"
            f"  git-ssh-sync checkout {project} {branch}"
        )


def _ensure_origin_branch_missing_on_remote(
    project: str, local_path: Path, branch: str
) -> None:
    if _origin_branch_exists_on_remote(local_path, branch):
        raise SyncError(
            f"Origin branch already exists: {branch}\n\n"
            "Run checkout without --base to use the existing branch:\n\n"
            f"  git-ssh-sync checkout {project} {branch}"
        )


def _create_origin_branch(local_path: Path, branch: str, base_branch: str) -> None:
    git.push(
        "origin",
        [f"refs/remotes/origin/{base_branch}:refs/heads/{branch}"],
        cwd=local_path,
    )
    git.fetch(
        "origin", [f"refs/heads/{branch}:refs/remotes/origin/{branch}"], cwd=local_path
    )


def _push_origin_branch_to_cache(
    project_config: ProjectConfig, local_path: Path, branch: str
) -> None:
    remote_cache = _cache_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        cache_path=project_config.dev.cache_path,
        remote_os=project_config.dev.os,
    )
    git.push(
        remote_cache,
        [f"refs/remotes/origin/{branch}:refs/heads/{branch}"],
        cwd=local_path,
        env=ssh.git_ssh_environment(project_config.dev.os),
    )


def _fetch_dev_branch(project_config: ProjectConfig, branch: str) -> None:
    ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["fetch", "gitsync", f"refs/heads/{branch}:refs/remotes/gitsync/{branch}"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )


def _remote_branch_exists(project_config: ProjectConfig, branch: str) -> bool:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        user=project_config.dev.user,
        check=False,
        remote_os=project_config.dev.os,
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
        remote_os=project_config.dev.os,
    )
    return _clean_output(result.stdout) or "(detached)"


def _remote_gitsync_url(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["remote", "get-url", "gitsync"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    return _clean_output(result.stdout)


def _ensure_gitsync_remote_matches(project: str, project_config: ProjectConfig) -> None:
    actual_url = _remote_gitsync_url(project_config)
    expected_url = project_config.dev.cache_path
    if actual_url == expected_url:
        return
    raise SyncError(
        "Development work repository gitsync remote does not match the configured cache path.\n\n"
        f"Project:\n  {project}\n\n"
        "Development:\n"
        f"  host: {project_config.dev.host}\n"
        f"  path: {project_config.dev.work_path}\n\n"
        f"Configured cache path:\n  {expected_url}\n\n"
        f"Actual gitsync remote:\n  {actual_url}\n\n"
        "Update the work repo remote or recreate the project clone:\n\n"
        f"  git -C {project_config.dev.work_path} remote set-url gitsync {expected_url}"
    )


def _detached_head_recovery(project: str) -> str:
    return format_recovery(
        f"`git-ssh-sync doctor {project}` for a full diagnosis.",
        f"`git-ssh-sync checkout {project} <branch>` to reattach the development work repo.",
    )


def _dirty_worktree_recovery(project: str) -> str:
    return format_recovery(
        f"`git-ssh-sync dev status {project}` to inspect the development worktree.",
        f"`git-ssh-sync dev diff {project} --stat` to review the pending changes.",
        "Commit or stash changes on the development environment before retrying.",
    )


def _origin_push_recovery(project: str) -> str:
    return format_recovery(
        "Check branch protection and your origin repository permissions.",
        f"`git-ssh-sync pull {project}` if origin has newer commits.",
        "Inspect the origin URL and local Git credentials if authentication failed.",
    )


def _require_remote_current_branch(project: str, project_config: ProjectConfig) -> str:
    branch = _remote_current_branch(project_config)
    if branch == "(detached)":
        raise SyncError(
            "Development work repository is in detached HEAD state.\n\n"
            f"{_detached_head_recovery(project)}"
        )
    return branch


def _remote_short_head(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["rev-parse", "--short", "HEAD"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    return _clean_output(result.stdout)


def _remote_status(project_config: ProjectConfig) -> str:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["status", "--porcelain"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    return _clean_output(result.stdout)


def _fetch_dev_branch_to_local(
    project_config: ProjectConfig, local_path: Path, branch: str
) -> None:
    git.fetch(
        _work_url(project_config),
        [f"refs/heads/{branch}:refs/remotes/dev/{branch}"],
        cwd=local_path,
        env=ssh.git_ssh_environment(project_config.dev.os),
    )


def _parse_tag_refs(output: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        object_id, refname = line.split(maxsplit=1)
        if refname.endswith("^{}"):
            continue
        if refname.startswith("refs/tags/"):
            refname = refname.removeprefix("refs/tags/")
        tags[refname] = object_id
    return tags


def _list_local_tags(local_path: Path) -> dict[str, str]:
    result = git.run_git(
        ["for-each-ref", "refs/tags", "--format=%(objectname) %(refname)"],
        cwd=local_path,
    )
    return _parse_tag_refs(result.stdout)


def _list_origin_remote_tags(local_path: Path) -> dict[str, str]:
    result = git.run_git(["ls-remote", "--tags", "origin"], cwd=local_path)
    return _parse_tag_refs(result.stdout)


def _list_remote_tags(project_config: ProjectConfig, repo_path: str) -> dict[str, str]:
    result = ssh.run_remote_git(
        project_config.dev.host,
        repo_path,
        ["for-each-ref", "refs/tags", "--format=%(objectname) %(refname)"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )
    return _parse_tag_refs(result.stdout)


def _format_tag_names(tag_names: list[str]) -> str:
    if not tag_names:
        return "(none)"
    return ", ".join(tag_names)


def _ensure_tag_sync_enabled(project: str, project_config: ProjectConfig) -> None:
    if project_config.options.sync_tags:
        return
    raise SyncError(
        f"Tag synchronization is disabled for project '{project}'.\n\n"
        "Enable it first:\n\n"
        f"  git-ssh-sync config set {project} --sync-tags"
    )


def _conflicting_tags(
    source_tags: dict[str, str], target_tags: dict[str, str]
) -> list[str]:
    return sorted(
        tag
        for tag, object_id in source_tags.items()
        if tag in target_tags and target_tags[tag] != object_id
    )


def _ensure_no_tag_conflicts(
    *,
    project: str,
    direction: str,
    source_label: str,
    source_tags: dict[str, str],
    targets: dict[str, dict[str, str]],
) -> None:
    conflicts = {
        label: _conflicting_tags(source_tags, tags) for label, tags in targets.items()
    }
    conflicts = {label: tags for label, tags in conflicts.items() if tags}
    if not conflicts:
        return

    details = "\n".join(
        f"  {label}: {_format_tag_names(tags)}" for label, tags in conflicts.items()
    )
    raise SyncError(
        "Cannot synchronize tags because existing tag names point to different objects.\n\n"
        f"Project:\n  {project}\n\n"
        f"Direction:\n  {direction}\n\n"
        f"Source:\n  {source_label}\n\n"
        "Conflicting tags:\n"
        f"{details}\n\n"
        "Resolve the tag mismatch manually. git-ssh-sync does not delete, overwrite, "
        "or force-update tags."
    )


def _missing_tags(
    source_tags: dict[str, str], target_tags: dict[str, str]
) -> list[str]:
    return sorted(tag for tag in source_tags if tag not in target_tags)


def _print_tag_plan(
    *,
    project: str,
    direction: str,
    dry_run: bool,
    source_tags: dict[str, str],
    target_actions: dict[str, list[str]],
) -> None:
    console.print(f"Project: {project}")
    console.print("Refs: tags")
    console.print(f"Direction: {direction}")
    if dry_run:
        console.print("Mode: dry-run")
    console.print(f"Source tags: {len(source_tags)}")
    console.print("Tag differences:")
    for label, tags in target_actions.items():
        console.print(f"  - {label}: {_format_tag_names(tags)}")


def sync_tags_project(
    project: str,
    *,
    direction: str = "origin-to-dev",
    dry_run: bool = False,
) -> None:
    """Synchronize tags without deleting or overwriting existing tag refs."""
    project_config = _load_project(project)
    local_path = Path(project_config.local.repo_path)

    _ensure_tag_sync_enabled(project, project_config)
    _ensure_gateway_repo(local_path)
    _ensure_gitsync_remote_matches(project, project_config)

    cache_url = _cache_url(
        host=project_config.dev.host,
        user=project_config.dev.user,
        cache_path=project_config.dev.cache_path,
        remote_os=project_config.dev.os,
    )

    if direction == "origin-to-dev":
        source_tags = _list_origin_remote_tags(local_path)
        gateway_tags = _list_local_tags(local_path)
        cache_tags = _list_remote_tags(project_config, project_config.dev.cache_path)
        work_tags = _list_remote_tags(project_config, project_config.dev.work_path)
        _ensure_no_tag_conflicts(
            project=project,
            direction="origin -> development",
            source_label="origin",
            source_tags=source_tags,
            targets={
                "gateway repository": gateway_tags,
                "development cache": cache_tags,
                "development work repo": work_tags,
            },
        )
        tags_to_cache = _missing_tags(source_tags, cache_tags)
        tags_to_work = _missing_tags(source_tags, work_tags)
        _print_tag_plan(
            project=project,
            direction="origin -> development",
            dry_run=dry_run,
            source_tags=source_tags,
            target_actions={
                "push to development cache": tags_to_cache,
                "fetch into development work repo": tags_to_work,
            },
        )
        if dry_run:
            logger.info(f"Dry-run tag sync completed for project '{project}'")
            return

        git.fetch("origin", ["--tags"], cwd=local_path)
        if tags_to_cache:
            git.push(
                cache_url,
                [f"refs/tags/{tag}:refs/tags/{tag}" for tag in tags_to_cache],
                cwd=local_path,
                env=ssh.git_ssh_environment(project_config.dev.os),
            )
        if tags_to_work:
            ssh.run_remote_git(
                project_config.dev.host,
                project_config.dev.work_path,
                [
                    "fetch",
                    "gitsync",
                    *[f"refs/tags/{tag}:refs/tags/{tag}" for tag in tags_to_work],
                ],
                user=project_config.dev.user,
                remote_os=project_config.dev.os,
            )
        logger.info(f"Successfully synchronized tags for project '{project}'")
        return

    if direction == "dev-to-origin":
        source_tags = _list_remote_tags(project_config, project_config.dev.work_path)
        origin_tags = _list_origin_remote_tags(local_path)
        gateway_tags = _list_local_tags(local_path)
        cache_tags = _list_remote_tags(project_config, project_config.dev.cache_path)
        _ensure_no_tag_conflicts(
            project=project,
            direction="development -> origin",
            source_label="development work repo",
            source_tags=source_tags,
            targets={
                "origin": origin_tags,
                "gateway repository": gateway_tags,
                "development cache": cache_tags,
            },
        )
        tags_to_origin = _missing_tags(source_tags, origin_tags)
        tags_to_gateway = _missing_tags(
            {tag: source_tags[tag] for tag in tags_to_origin}, gateway_tags
        )
        _print_tag_plan(
            project=project,
            direction="development -> origin",
            dry_run=dry_run,
            source_tags=source_tags,
            target_actions={
                "fetch into gateway repository": tags_to_gateway,
                "push to origin": tags_to_origin,
            },
        )
        if dry_run:
            logger.info(f"Dry-run tag sync completed for project '{project}'")
            return

        if tags_to_gateway:
            git.fetch(
                _work_url(project_config),
                [f"refs/tags/{tag}:refs/tags/{tag}" for tag in tags_to_gateway],
                cwd=local_path,
                env=ssh.git_ssh_environment(project_config.dev.os),
            )
        if tags_to_origin:
            git.push(
                "origin",
                [f"refs/tags/{tag}:refs/tags/{tag}" for tag in tags_to_origin],
                cwd=local_path,
            )
        logger.info(f"Successfully synchronized tags for project '{project}'")
        return

    raise SyncError(f"Unsupported tag sync direction: {direction}")


def _dirty_error(project: str, project_config: ProjectConfig) -> SyncError:
    return SyncError(
        "Error: Development working tree is dirty.\n\n"
        f"Project:\n  {project}\n\n"
        "Development:\n"
        f"  host: {project_config.dev.host}\n"
        f"  path: {project_config.dev.work_path}\n"
        f"  branch: {_remote_current_branch(project_config)}\n"
        f"  commit: {_remote_short_head(project_config)}\n\n"
        f"{_dirty_worktree_recovery(project)}"
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
            remote_os=project_config.dev.os,
        )
        return

    ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["switch", "--track", "-c", branch, f"gitsync/{branch}"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )


def _ensure_fast_forwardable(
    project: str, project_config: ProjectConfig, branch: str
) -> None:
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        [
            "merge-base",
            "--is-ancestor",
            f"refs/heads/{branch}",
            f"refs/remotes/gitsync/{branch}",
        ],
        user=project_config.dev.user,
        check=False,
        remote_os=project_config.dev.os,
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


def _ensure_pushable(
    project: str, project_config: ProjectConfig, local_path: Path, branch: str
) -> None:
    result = git.run_git(
        [
            "merge-base",
            "--is-ancestor",
            f"refs/remotes/origin/{branch}",
            f"refs/remotes/dev/{branch}",
        ],
        cwd=local_path,
        check=False,
    )
    if result.returncode == 0:
        return
    if result.returncode == 1:
        current_branch = _remote_current_branch(project_config)
        current_commit = _remote_short_head(project_config)
        raise SyncError(
            f"Cannot push {branch}.\n\n"
            f"origin/{branch} has commits that are not included in dev/{branch}.\n\n"
            f"Project:\n  {project}\n\n"
            "Development:\n"
            f"  host: {project_config.dev.host}\n"
            f"  path: {project_config.dev.work_path}\n"
            f"  branch: {current_branch}\n"
            f"  commit: {current_commit}\n\n"
            "Run:\n\n"
            f"  git-ssh-sync pull {project}\n\n"
            "Then resolve the branch on the development environment before pushing again."
        )
    raise CommandExecutionError(
        environment=result.environment,
        command=result.command,
        returncode=result.returncode,
        cwd=result.cwd,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _ensure_pushable_from_development(
    project: str, project_config: ProjectConfig, local_path: Path, branch: str
) -> None:
    origin_head = git.rev_parse([f"refs/remotes/origin/{branch}"], cwd=local_path)
    origin_commit = origin_head.stdout.strip()
    result = ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["merge-base", "--is-ancestor", origin_commit, f"refs/heads/{branch}"],
        user=project_config.dev.user,
        check=False,
        remote_os=project_config.dev.os,
    )
    if result.returncode == 0:
        return
    if result.returncode == 1:
        current_branch = _remote_current_branch(project_config)
        current_commit = _remote_short_head(project_config)
        raise SyncError(
            f"Cannot push {branch}.\n\n"
            f"origin/{branch} has commits that are not included in dev/{branch}.\n\n"
            f"Project:\n  {project}\n\n"
            "Development:\n"
            f"  host: {project_config.dev.host}\n"
            f"  path: {project_config.dev.work_path}\n"
            f"  branch: {current_branch}\n"
            f"  commit: {current_commit}\n\n"
            "Run:\n\n"
            f"  git-ssh-sync pull {project}\n\n"
            "Then resolve the branch on the development environment before pushing again."
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


def pull_project(project: str, *, dry_run: bool = False) -> None:
    """Fetch origin changes and fast-forward the current development branch."""
    project_config = _load_project(project)
    local_path = Path(project_config.local.repo_path)

    _ensure_gateway_repo(local_path)
    _ensure_gitsync_remote_matches(project, project_config)
    selected_branch = _require_remote_current_branch(project, project_config)

    logger.info(f"Pulling project '{project}' branch '{selected_branch}'")

    if dry_run:
        git.run_git(["fetch", "--dry-run", "origin"], cwd=local_path)
        _ensure_origin_branch(local_path, selected_branch)
        _ensure_fast_forwardable(project, project_config, selected_branch)
        _print_dry_run_plan(
            project=project,
            branch=selected_branch,
            direction="origin -> development",
            preflight=[
                "gateway repository exists",
                "development gitsync remote matches configuration",
                "development work repo is on a branch",
                f"origin/{selected_branch} exists in the gateway repository",
                f"development {selected_branch} can fast-forward to gitsync/{selected_branch}",
            ],
            operations=[
                "fetch origin in the gateway repository",
                f"push origin/{selected_branch} to the development cache",
                f"fetch gitsync/{selected_branch} in the development work repo",
                f"merge --ff-only gitsync/{selected_branch} in the development work repo",
            ],
        )
        logger.info(f"Dry-run pull completed for project '{project}'")
        return

    console.print(f"Project: {project}")
    console.print(f"Branch: {selected_branch}")
    console.print("Direction: origin -> development")

    git.fetch("origin", cwd=local_path)
    _ensure_origin_branch(local_path, selected_branch)
    _push_origin_branch_to_cache(project_config, local_path, selected_branch)
    _fetch_dev_branch(project_config, selected_branch)

    _ensure_fast_forwardable(project, project_config, selected_branch)
    ssh.run_remote_git(
        project_config.dev.host,
        project_config.dev.work_path,
        ["merge", "--ff-only", f"gitsync/{selected_branch}"],
        user=project_config.dev.user,
        remote_os=project_config.dev.os,
    )

    logger.info(f"Successfully pulled project '{project}'")


def checkout_project(
    project: str,
    branch: str,
    *,
    create: bool = False,
    base_branch: str | None = None,
    dry_run: bool = False,
) -> None:
    """Switch the development repository to a branch from origin."""
    project_config = _load_project(project)
    local_path = Path(project_config.local.repo_path)

    action = "Creating and checking out" if create else "Checking out"
    logger.info(f"{action} branch '{branch}' for project '{project}'")

    _ensure_gateway_repo(local_path)
    _ensure_gitsync_remote_matches(project, project_config)
    if dry_run:
        git.run_git(["fetch", "--dry-run", "origin"], cwd=local_path)
        preflight = [
            "gateway repository exists",
            "development gitsync remote matches configuration",
        ]
        operations = ["fetch origin in the gateway repository"]
        if create:
            base = base_branch or _require_remote_current_branch(
                project, project_config
            )
            _ensure_origin_branch_on_remote(local_path, base)
            _ensure_origin_branch_missing_on_remote(project, local_path, branch)
            preflight.extend(
                [
                    f"origin/{base} exists on origin",
                    f"origin/{branch} does not exist on origin",
                ]
            )
            operations.extend(
                [
                    f"create origin/{branch} from origin/{base}",
                    f"fetch origin/{branch} into the gateway repository",
                ]
            )
        else:
            _ensure_origin_branch_on_remote(local_path, branch)
        _ensure_dev_clean(project, project_config)
        branch_exists = _remote_branch_exists(project_config, branch)
        preflight.extend(
            [
                f"origin/{branch} exists on origin",
                "development work tree is clean",
            ]
        )
        operations.extend(
            [
                f"push origin/{branch} to the development cache",
                f"fetch gitsync/{branch} in the development work repo",
                f"switch to existing development branch {branch}"
                if branch_exists
                else f"create and track development branch {branch} from gitsync/{branch}",
            ]
        )
        _print_dry_run_plan(
            project=project,
            branch=branch,
            direction="origin -> development checkout",
            preflight=preflight,
            operations=operations,
        )
        logger.info(f"Dry-run checkout completed for project '{project}'")
        return

    git.fetch("origin", cwd=local_path)
    if create:
        base = base_branch or _require_remote_current_branch(project, project_config)
        _ensure_origin_branch(local_path, base)
        _ensure_origin_branch_missing(project, local_path, branch)
        _create_origin_branch(local_path, branch, base)
    _ensure_origin_branch(local_path, branch)
    _push_origin_branch_to_cache(project_config, local_path, branch)
    _fetch_dev_branch(project_config, branch)
    _ensure_dev_clean(project, project_config)
    _switch_to_branch(project_config, branch)

    logger.info(f"Successfully checked out branch '{branch}' for project '{project}'")


def push_project(project: str, *, dry_run: bool = False) -> None:
    """Push current development branch commits to origin when it has not diverged."""
    project_config = _load_project(project)
    local_path = Path(project_config.local.repo_path)

    _ensure_gateway_repo(local_path)
    _ensure_gitsync_remote_matches(project, project_config)
    selected_branch = _require_remote_current_branch(project, project_config)

    logger.info(f"Pushing project '{project}' branch '{selected_branch}'")

    if dry_run:
        git.run_git(["fetch", "--dry-run", "origin"], cwd=local_path)
        _ensure_origin_branch(local_path, selected_branch)
        _ensure_pushable_from_development(
            project, project_config, local_path, selected_branch
        )
        _print_dry_run_plan(
            project=project,
            branch=selected_branch,
            direction="development -> origin",
            preflight=[
                "gateway repository exists",
                "development gitsync remote matches configuration",
                "development work repo is on a branch",
                f"origin/{selected_branch} exists in the gateway repository",
                f"origin/{selected_branch} is an ancestor of dev/{selected_branch}",
            ],
            operations=[
                "fetch origin in the gateway repository",
                f"fetch development {selected_branch} into the gateway repository",
                f"push dev/{selected_branch} to origin/{selected_branch}",
            ],
        )
        logger.info(f"Dry-run push completed for project '{project}'")
        return

    console.print(f"Project: {project}")
    console.print(f"Branch: {selected_branch}")
    console.print("Direction: development -> origin")

    git.fetch("origin", cwd=local_path)
    _ensure_origin_branch(local_path, selected_branch)
    _fetch_dev_branch_to_local(project_config, local_path, selected_branch)
    _ensure_pushable(project, project_config, local_path, selected_branch)

    try:
        git.push(
            "origin",
            [f"refs/remotes/dev/{selected_branch}:refs/heads/{selected_branch}"],
            cwd=local_path,
        )
        logger.info(f"Successfully pushed project '{project}'")
    except CommandExecutionError as error:
        logger.error(f"Failed to push project '{project}': {error}")
        raise SyncError(
            f"Failed to push {selected_branch} to origin.\n\n"
            f"Project:\n  {project}\n\n"
            f"Origin push failed:\n{error}\n\n"
            f"{_origin_push_recovery(project)}"
        ) from error
