"""Manual end-to-end tests for the checklist in docs/manual-testing.md.

These tests are intentionally outside the configured pytest testpaths so they
only run when explicitly requested with `uv run pytest manual_tests`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from base64 import b64encode
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RemoteTarget:
    name: str
    project: str
    host: str
    user: str
    os_name: str
    work_path: str
    cache_path: str


@dataclass(frozen=True)
class RemoteLayout:
    work_path: str
    cache_path: str


def _run(
    command: Iterable[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> CommandResult:
    command_list = list(command)
    result = subprocess.run(
        command_list,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    command_result = CommandResult(
        command=command_list,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if check and result.returncode != 0:
        joined = shlex.join(command_list)
        raise AssertionError(
            f"Command failed with exit code {result.returncode}: {joined}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return command_result


def _cli_command(env: dict[str, str], *args: str) -> list[str]:
    command = shlex.split(env.get("GSS_CLI_COMMAND", "uv run git-ssh-sync"))
    return [*command, *args]


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    pytest.skip(f"{name} is required for manual E2E tests")


def _remote_targets(run_id: str) -> list[RemoteTarget]:
    targets: list[RemoteTarget] = []
    linux_host = os.environ.get("GSS_TEST_LINUX_HOST")
    linux_user = os.environ.get("GSS_TEST_LINUX_USER")
    if linux_host and linux_user:
        linux_project = os.environ.get(
            "GSS_TEST_LINUX_PROJECT", f"manual-linux-{run_id}"
        )
        targets.append(
            RemoteTarget(
                name="linux",
                project=linux_project,
                host=linux_host,
                user=linux_user,
                os_name="posix",
                work_path=os.environ.get(
                    "GSS_TEST_LINUX_WORK_PATH",
                    f"/home/{linux_user}/work/git-ssh-sync-manual-{run_id}",
                ),
                cache_path=os.environ.get(
                    "GSS_TEST_LINUX_CACHE_PATH",
                    f"/home/{linux_user}/.git-ssh-sync/cache/{linux_project}.git",
                ),
            )
        )

    windows_host = os.environ.get("GSS_TEST_WINDOWS_HOST")
    windows_user = os.environ.get("GSS_TEST_WINDOWS_USER")
    if windows_host and windows_user:
        windows_project = os.environ.get(
            "GSS_TEST_WINDOWS_PROJECT", f"manual-windows-{run_id}"
        )
        targets.append(
            RemoteTarget(
                name="windows",
                project=windows_project,
                host=windows_host,
                user=windows_user,
                os_name="windows",
                work_path=os.environ.get(
                    "GSS_TEST_WINDOWS_WORK_PATH",
                    f"C:\\Users\\{windows_user}\\work\\git-ssh-sync-manual-{run_id}",
                ),
                cache_path=os.environ.get(
                    "GSS_TEST_WINDOWS_CACHE_PATH",
                    f"C:\\Users\\{windows_user}\\.git-ssh-sync\\cache\\{windows_project}.git",
                ),
            )
        )

    if not targets:
        pytest.skip(
            "Set GSS_TEST_LINUX_HOST/GSS_TEST_LINUX_USER and/or "
            "GSS_TEST_WINDOWS_HOST/GSS_TEST_WINDOWS_USER."
        )
    return targets


def _ssh_target(target: RemoteTarget) -> str:
    return f"{target.user}@{target.host}"


def _remote_command(
    target: RemoteTarget, command: str, *, check: bool = True
) -> CommandResult:
    return _run(["ssh", _ssh_target(target), command], check=check)


def _powershell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _remote_shell(
    target: RemoteTarget, command: str, *, check: bool = True
) -> CommandResult:
    if target.os_name == "windows":
        encoded = b64encode(command.encode("utf-16le")).decode("ascii")
        return _remote_command(
            target,
            f"powershell -NoProfile -EncodedCommand {encoded}",
            check=check,
        )
    return _remote_command(target, command, check=check)


def _cleanup_remote(target: RemoteTarget) -> None:
    if target.os_name == "windows":
        work = _powershell_single_quote(target.work_path)
        cache = _powershell_single_quote(target.cache_path)
        _remote_shell(
            target,
            (
                f"Remove-Item -LiteralPath {work} -Recurse -Force -ErrorAction SilentlyContinue; "
                f"Remove-Item -LiteralPath {cache} -Recurse -Force -ErrorAction SilentlyContinue"
            ),
            check=False,
        )
        return

    _remote_shell(
        target,
        f"rm -rf {shlex.quote(target.work_path)} {shlex.quote(target.cache_path)}",
        check=False,
    )


def _cleanup_remote_layout(target: RemoteTarget, layout: RemoteLayout) -> None:
    layout_target = RemoteTarget(
        name=target.name,
        project=target.project,
        host=target.host,
        user=target.user,
        os_name=target.os_name,
        work_path=layout.work_path,
        cache_path=layout.cache_path,
    )
    _cleanup_remote(layout_target)


def _remote_git(target: RemoteTarget, *args: str, check: bool = True) -> CommandResult:
    if target.os_name == "windows":
        work_path = _powershell_single_quote(target.work_path)
        quoted_args = " ".join(_powershell_single_quote(arg) for arg in args)
        return _remote_shell(target, f"& git -C {work_path} {quoted_args}", check=check)

    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    return _remote_shell(
        target,
        f"git -C {shlex.quote(target.work_path)} {quoted_args}",
        check=check,
    )


def _remote_git_at(
    target: RemoteTarget, repo_path: str, *args: str, check: bool = True
) -> CommandResult:
    repo_target = RemoteTarget(
        name=target.name,
        project=target.project,
        host=target.host,
        user=target.user,
        os_name=target.os_name,
        work_path=repo_path,
        cache_path=target.cache_path,
    )
    return _remote_git(repo_target, *args, check=check)


def _remote_parent_path(target: RemoteTarget, path: str) -> str:
    if target.os_name == "windows":
        result = _remote_shell(
            target,
            f"Split-Path -Parent {_powershell_single_quote(path)}",
        )
        return result.stdout.strip()

    return str(Path(path).parent)


def _remote_git_url(target: RemoteTarget, repo_path: str) -> str:
    if target.os_name == "windows":
        normalized_path = repo_path.replace("\\", "/")
        return f"{target.user}@{target.host}:{normalized_path}"
    return f"ssh://{target.user}@{target.host}{repo_path}"


def _git_ssh_env(target: RemoteTarget) -> dict[str, str] | None:
    if target.os_name != "windows":
        return None

    env = os.environ.copy()
    if existing_command := env.get("GIT_SSH_COMMAND"):
        env["GIT_SSH_SYNC_BASE_SSH_COMMAND"] = existing_command
    env["GIT_SSH_COMMAND"] = (
        f"{shlex.quote(sys.executable)} -m git_ssh_sync.windows_git_ssh"
    )
    return env


def _remote_init_work_repo(target: RemoteTarget, work_path: str) -> None:
    if target.os_name == "windows":
        parent = _powershell_single_quote(_remote_parent_path(target, work_path))
        destination = _powershell_single_quote(work_path)
        _remote_shell(
            target,
            f"New-Item -ItemType Directory -Force -Path {parent}; "
            f"& git init {destination}; "
            f"& git -C {destination} config receive.denyCurrentBranch updateInstead",
        )
        return

    _remote_shell(
        target,
        (
            f"mkdir -p {shlex.quote(_remote_parent_path(target, work_path))} && "
            f"git init {shlex.quote(work_path)} && "
            f"git -C {shlex.quote(work_path)} config receive.denyCurrentBranch updateInstead"
        ),
    )


def _remote_seed_work_repo(
    target: RemoteTarget, local_path: Path, work_path: str, branch: str
) -> None:
    _remote_init_work_repo(target, work_path)
    _run(
        [
            "git",
            "push",
            _remote_git_url(target, work_path),
            f"HEAD:refs/heads/{branch}",
        ],
        cwd=local_path,
        env=_git_ssh_env(target),
    )
    _remote_git_at(target, work_path, "checkout", branch)


def _remote_append_and_commit(
    target: RemoteTarget, filename: str, text: str, message: str
) -> None:
    _remote_git(target, "config", "user.email", "manual-test@example.invalid")
    _remote_git(target, "config", "user.name", "git-ssh-sync manual test")
    if target.os_name == "windows":
        work_path = _powershell_single_quote(target.work_path)
        file_path = _powershell_single_quote(filename)
        value = _powershell_single_quote(text)
        message_arg = _powershell_single_quote(message)
        _remote_shell(
            target,
            (
                f"Set-Location -LiteralPath {work_path}; "
                f"Add-Content -LiteralPath {file_path} -Value {value}; "
                f"& git add {file_path}; "
                f"& git commit -m {message_arg}"
            ),
        )
        return

    _remote_shell(
        target,
        (
            f"cd {shlex.quote(target.work_path)} && "
            f"printf '%s\\n' {shlex.quote(text)} >> {shlex.quote(filename)} && "
            f"git add {shlex.quote(filename)} && "
            f"git commit -m {shlex.quote(message)}"
        ),
    )


def _remote_create_dirty_file(target: RemoteTarget) -> None:
    if target.os_name == "windows":
        work_path = _powershell_single_quote(target.work_path)
        _remote_shell(
            target,
            (
                f"Set-Location -LiteralPath {work_path}; "
                "Add-Content -LiteralPath 'dirty.txt' -Value 'dirty windows'"
            ),
        )
        return

    _remote_shell(
        target,
        f"cd {shlex.quote(target.work_path)} && printf 'dirty linux\\n' >> dirty.txt",
    )


def _remote_remove_dirty_file(target: RemoteTarget) -> None:
    if target.os_name == "windows":
        work_path = _powershell_single_quote(target.work_path)
        _remote_shell(
            target,
            (
                f"Set-Location -LiteralPath {work_path}; "
                "& git checkout -- dirty.txt 2>$null; "
                "Remove-Item -LiteralPath 'dirty.txt' -Force -ErrorAction SilentlyContinue"
            ),
            check=False,
        )
        return

    _remote_shell(
        target,
        (
            f"cd {shlex.quote(target.work_path)} && "
            "git checkout -- dirty.txt 2>/dev/null || rm -f dirty.txt"
        ),
        check=False,
    )


def _detect_default_branch(origin_url: str) -> str:
    result = _run(["git", "ls-remote", "--symref", origin_url, "HEAD"])
    for line in result.stdout.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split()[1].removeprefix("refs/heads/")
    return os.environ.get("GSS_TEST_BASE_BRANCH", "main")


def _origin_clone(origin_url: str, path: Path) -> None:
    _run(["git", "clone", origin_url, str(path)])
    _run(["git", "config", "user.email", "manual-test@example.invalid"], cwd=path)
    _run(["git", "config", "user.name", "git-ssh-sync manual test"], cwd=path)


def _origin_commit_and_push(
    repo: Path, branch: str, filename: str, text: str, message: str
) -> None:
    _run(["git", "switch", branch], cwd=repo)
    (repo / filename).write_text(text + "\n", encoding="utf-8")
    _run(["git", "add", filename], cwd=repo)
    _run(["git", "commit", "-m", message], cwd=repo)
    _run(["git", "push", "origin", branch], cwd=repo)


def _delete_origin_branch(origin_url: str, branch: str) -> None:
    _run(["git", "push", origin_url, "--delete", branch], check=False)


def _assert_cli_failure(
    env: dict[str, str], expected_returncode: int, *args: str
) -> CommandResult:
    result = _run(_cli_command(env, *args), env=env, check=False)
    assert result.returncode == expected_returncode
    return result


def _create_attach_fixture(
    env: dict[str, str],
    tmp_path: Path,
    origin_url: str,
    target: RemoteTarget,
    project: str,
    layout: RemoteLayout,
) -> Path:
    local_path = tmp_path / f"gateway-{project}"
    _origin_clone(origin_url, local_path)
    branch = _run(["git", "branch", "--show-current"], cwd=local_path).stdout.strip()
    _remote_seed_work_repo(target, local_path, layout.work_path, branch)
    _run(
        _cli_command(
            env,
            "init",
            project,
            "--origin",
            origin_url,
            "--dev-host",
            target.host,
            "--dev-user",
            target.user,
            "--dev-os",
            target.os_name,
            "--dev-path",
            layout.work_path,
        ),
        env=env,
    )
    _run(
        _cli_command(
            env,
            "config",
            "set",
            project,
            "--local-repo-path",
            str(local_path),
            "--dev-cache-path",
            layout.cache_path,
        ),
        env=env,
    )
    return local_path


def _run_attach_checks(
    env: dict[str, str],
    tmp_path: Path,
    origin_url: str,
    run_id: str,
    target: RemoteTarget,
) -> None:
    attach_project = f"manual-attach-{target.name}-{run_id}"
    attach_layout = RemoteLayout(
        work_path=(
            f"C:\\Users\\{target.user}\\work\\git-ssh-sync-attach-{run_id}"
            if target.os_name == "windows"
            else f"/home/{target.user}/work/git-ssh-sync-attach-{run_id}"
        ),
        cache_path=(
            f"C:\\Users\\{target.user}\\.git-ssh-sync\\cache\\{attach_project}.git"
            if target.os_name == "windows"
            else f"/home/{target.user}/.git-ssh-sync/cache/{attach_project}.git"
        ),
    )
    dirty_project = f"manual-attach-dirty-{target.name}-{run_id}"
    dirty_layout = RemoteLayout(
        work_path=(
            f"C:\\Users\\{target.user}\\work\\git-ssh-sync-attach-dirty-{run_id}"
            if target.os_name == "windows"
            else f"/home/{target.user}/work/git-ssh-sync-attach-dirty-{run_id}"
        ),
        cache_path=(
            f"C:\\Users\\{target.user}\\.git-ssh-sync\\cache\\{dirty_project}.git"
            if target.os_name == "windows"
            else f"/home/{target.user}/.git-ssh-sync/cache/{dirty_project}.git"
        ),
    )

    for layout in (attach_layout, dirty_layout):
        _cleanup_remote_layout(target, layout)

    try:
        _create_attach_fixture(
            env, tmp_path, origin_url, target, attach_project, attach_layout
        )
        dry_run = _run(
            _cli_command(env, "attach", attach_project, "--dry-run"), env=env
        )
        assert "Planned operations" in dry_run.stdout
        _run(_cli_command(env, "attach", attach_project, "--yes"), env=env)
        _run(_cli_command(env, "doctor", attach_project), env=env)
        gitsync = _remote_git_at(
            target, attach_layout.work_path, "remote", "get-url", "gitsync"
        )
        assert gitsync.stdout.strip() == attach_layout.cache_path

        _create_attach_fixture(
            env, tmp_path, origin_url, target, dirty_project, dirty_layout
        )
        dirty_target = RemoteTarget(
            name=target.name,
            project=dirty_project,
            host=target.host,
            user=target.user,
            os_name=target.os_name,
            work_path=dirty_layout.work_path,
            cache_path=dirty_layout.cache_path,
        )
        _remote_create_dirty_file(dirty_target)
        dirty_attach = _assert_cli_failure(env, 1, "attach", dirty_project, "--dry-run")
        assert "dirty" in (dirty_attach.stdout + dirty_attach.stderr).lower()
        missing_gitsync = _remote_git_at(
            target,
            dirty_layout.work_path,
            "remote",
            "get-url",
            "gitsync",
            check=False,
        )
        assert missing_gitsync.returncode != 0
    finally:
        for project in (attach_project, dirty_project):
            _run(
                _cli_command(env, "config", "remove", project, "--yes"),
                env=env,
                check=False,
            )
        for layout in (attach_layout, dirty_layout):
            _cleanup_remote_layout(target, layout)


def test_manual_checklist_e2e(tmp_path: Path) -> None:
    origin_url = _required_env("GSS_TEST_ORIGIN_URL")
    run_id = uuid4().hex[:8]
    targets = _remote_targets(run_id)
    default_branch = _detect_default_branch(origin_url)
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg-config")

    created_branches: list[str] = []
    for target in targets:
        _cleanup_remote(target)

    try:
        help_result = _run(_cli_command(env, "--help"), env=env)
        assert "git-ssh-sync" in help_result.stdout
        _run(_cli_command(env, "--version"), env=env)

        for target in targets:
            _run_attach_checks(env, tmp_path, origin_url, run_id, target)

            _run(
                _cli_command(
                    env,
                    "init",
                    target.project,
                    "--origin",
                    origin_url,
                    "--dev-host",
                    target.host,
                    "--dev-user",
                    target.user,
                    "--dev-os",
                    target.os_name,
                    "--dev-path",
                    target.work_path,
                ),
                env=env,
            )
            _run(
                _cli_command(
                    env,
                    "config",
                    "set",
                    target.project,
                    "--dev-cache-path",
                    target.cache_path,
                ),
                env=env,
            )
            show_result = _run(
                _cli_command(env, "config", "show", target.project), env=env
            )
            assert target.host in show_result.stdout
            assert target.work_path in show_result.stdout

            list_result = _run(_cli_command(env, "config", "list"), env=env)
            assert target.project in list_result.stdout

            _run(
                _cli_command(env, "config", "set", target.project, "--no-sync-tags"),
                env=env,
            )
            _run(
                _cli_command(env, "config", "set", target.project, "--sync-tags"),
                env=env,
            )
            _run(_cli_command(env, "clone", target.project), env=env)
            _run(_cli_command(env, "doctor", target.project), env=env)
            _remote_git(target, "status", "--short", "--branch")
            remotes = _remote_git(target, "remote", "-v")
            assert "gitsync" in remotes.stdout

            _run(_cli_command(env, "status", target.project), env=env)
            _run(_cli_command(env, "branch", target.project), env=env)
            _run(_cli_command(env, "dev", "status", target.project), env=env)
            _run(_cli_command(env, "dev", "diff", target.project), env=env)
            _run(_cli_command(env, "dev", "diff", target.project, "--stat"), env=env)
            _run(_cli_command(env, "dev", "diff", target.project, "--cached"), env=env)
            _run(
                _cli_command(env, "dev", "log", target.project, "--max-count", "5"),
                env=env,
            )
            log_file = tmp_path / f"{target.name}-git-ssh-sync.log"
            _run(_cli_command(env, "--verbose", "status", target.project), env=env)
            _run(_cli_command(env, "--debug", "status", target.project), env=env)
            _run(
                _cli_command(
                    env,
                    "--log-file",
                    str(log_file),
                    "status",
                    target.project,
                ),
                env=env,
            )
            assert log_file.exists()

            branch = f"manual/{run_id}/{target.name}"
            new_branch = f"manual/{run_id}/{target.name}-new"
            created_branches.extend([branch, new_branch])
            origin_repo = tmp_path / f"origin-{target.name}"
            _origin_clone(origin_url, origin_repo)
            _run(
                ["git", "switch", "-c", branch, f"origin/{default_branch}"],
                cwd=origin_repo,
            )
            _origin_commit_and_push(
                origin_repo,
                branch,
                f"{target.name}-branch.txt",
                f"{target.name} existing branch",
                f"Add {target.name} manual branch",
            )

            _run(
                _cli_command(env, "checkout", target.project, branch, "--dry-run"),
                env=env,
            )
            _run(_cli_command(env, "checkout", target.project, branch), env=env)
            status_after_checkout = _remote_git(target, "status", "--short", "--branch")
            assert branch in status_after_checkout.stdout

            _origin_commit_and_push(
                origin_repo,
                branch,
                f"{target.name}-origin-update.txt",
                f"{target.name} origin update",
                f"Add {target.name} origin manual update",
            )
            _run(_cli_command(env, "pull", target.project, "--dry-run"), env=env)
            _run(_cli_command(env, "pull", target.project), env=env)

            _remote_append_and_commit(
                target,
                f"{target.name}-remote-update.txt",
                f"{target.name} remote update",
                f"Add {target.name} remote manual update",
            )
            _run(_cli_command(env, "push", target.project, "--dry-run"), env=env)
            _run(_cli_command(env, "push", target.project), env=env)

            _remote_create_dirty_file(target)
            dirty_status = _run(
                _cli_command(env, "dev", "status", target.project), env=env
            )
            assert "dirty.txt" in dirty_status.stdout
            _run(_cli_command(env, "dev", "diff", target.project, "--stat"), env=env)
            _remote_remove_dirty_file(target)

            _run(
                _cli_command(
                    env,
                    "checkout",
                    target.project,
                    "-b",
                    new_branch,
                    "--base",
                    branch,
                    "--dry-run",
                ),
                env=env,
            )
            _run(
                _cli_command(
                    env,
                    "checkout",
                    target.project,
                    "-b",
                    new_branch,
                    "--base",
                    branch,
                ),
                env=env,
            )

            ahead_branch = f"manual/{run_id}/{target.name}-ahead"
            diverged_branch = f"manual/{run_id}/{target.name}-diverged"
            created_branches.extend([ahead_branch, diverged_branch])
            _run(["git", "switch", "-c", ahead_branch, branch], cwd=origin_repo)
            _origin_commit_and_push(
                origin_repo,
                ahead_branch,
                f"{target.name}-ahead-start.txt",
                f"{target.name} ahead start",
                f"Add {target.name} ahead branch",
            )
            _run(_cli_command(env, "checkout", target.project, ahead_branch), env=env)
            _origin_commit_and_push(
                origin_repo,
                ahead_branch,
                f"{target.name}-ahead-origin.txt",
                f"{target.name} origin ahead",
                f"Add {target.name} origin ahead update",
            )
            origin_ahead_push = _assert_cli_failure(env, 1, "push", target.project)
            assert "not included in dev" in (
                origin_ahead_push.stdout + origin_ahead_push.stderr
            )
            _run(_cli_command(env, "pull", target.project), env=env)

            _run(["git", "switch", "-c", diverged_branch, branch], cwd=origin_repo)
            _origin_commit_and_push(
                origin_repo,
                diverged_branch,
                f"{target.name}-diverged-start.txt",
                f"{target.name} diverged start",
                f"Add {target.name} diverged branch",
            )
            _run(
                _cli_command(env, "checkout", target.project, diverged_branch), env=env
            )
            _origin_commit_and_push(
                origin_repo,
                diverged_branch,
                f"{target.name}-diverged-origin.txt",
                f"{target.name} diverged origin",
                f"Add {target.name} diverged origin update",
            )
            _remote_append_and_commit(
                target,
                f"{target.name}-diverged-remote.txt",
                f"{target.name} diverged remote",
                f"Add {target.name} diverged remote update",
            )
            diverged_push = _assert_cli_failure(env, 1, "push", target.project)
            assert "not included in dev" in (
                diverged_push.stdout + diverged_push.stderr
            )
            diverged_pull = _assert_cli_failure(env, 1, "pull", target.project)
            assert "have diverged" in (diverged_pull.stdout + diverged_pull.stderr)
            _remote_git(target, "reset", "--hard", f"gitsync/{diverged_branch}")

            invalid_checkout = _run(
                _cli_command(
                    env, "checkout", target.project, branch, "--base", default_branch
                ),
                env=env,
                check=False,
            )
            assert invalid_checkout.returncode == 2
            assert "--base can only be used with -b/--create-branch." in (
                invalid_checkout.stdout + invalid_checkout.stderr
            )

            _run(
                _cli_command(env, "doctor", target.project, "--repair", "--yes"),
                env=env,
            )
            _run(_cli_command(env, "recover", target.project, "--yes"), env=env)
            _run(
                _cli_command(env, "config", "remove", target.project, "--yes"), env=env
            )
    finally:
        for target in targets:
            _cleanup_remote(target)
        for branch in created_branches:
            _delete_origin_branch(origin_url, branch)
