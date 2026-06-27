"""Command line interface for git-ssh-sync."""

from typing import Annotated, Literal

import typer
from rich.markup import escape
from rich.table import Table

from git_ssh_sync import __version__
from git_ssh_sync.attach import AttachError, attach_project
from git_ssh_sync.branch import (
    BranchError,
    branch_delete_project,
    branch_project,
    branch_prune_project,
)
from git_ssh_sync.clone import CloneError, clone_project
from git_ssh_sync.config import (
    build_project_config,
    ConfigError,
    NoConfigUpdateError,
    ProjectAlreadyExistsError,
    register_project,
    get_project,
    list_project_names,
    default_config_path,
    init_project,
    load_config,
    remove_project,
    save_config,
    update_project,
)
from git_ssh_sync.console import console
from git_ssh_sync.dev import (
    DevCommandError,
    dev_diff_project,
    dev_log_project,
    dev_status_project,
)
from git_ssh_sync.doctor import DoctorError, doctor_project
from git_ssh_sync.errors import CommandExecutionError
from git_ssh_sync.logging_config import setup_logging
from git_ssh_sync.status import StatusError, status_project
from git_ssh_sync.sync import (
    SyncError,
    checkout_project,
    pull_project,
    push_project,
    sync_tags_project,
)

app = typer.Typer(
    name="git-ssh-sync",
    help="Sync Git commits through a local machine over SSH.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage registered project configuration.")
dev_app = typer.Typer(help="Inspect the development work repository.")
app.add_typer(config_app, name="config")
app.add_typer(dev_app, name="dev")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"git-ssh-sync {__version__}")
        raise typer.Exit()


def _prompt_required(label: str, value: str | None = None) -> str:
    if value is not None:
        return value
    return typer.prompt(label)


def _prompt_dev_os(default: Literal["posix", "windows"]) -> Literal["posix", "windows"]:
    while True:
        value = typer.prompt("Development OS (posix/windows)", default=default)
        if value in {"posix", "windows"}:
            return value
        console.print("[red]Development OS must be 'posix' or 'windows'.[/red]")


def _init_project_interactive(
    project: str,
    *,
    origin: str | None,
    dev_host: str | None,
    dev_user: str | None,
    dev_os: Literal["posix", "windows"],
    dev_work_path: str | None,
    force: bool,
) -> None:
    origin = _prompt_required("Origin Git URL", origin)
    dev_host = _prompt_required("Development SSH host", dev_host)
    dev_user = _prompt_required("Development SSH user", dev_user)
    dev_os = _prompt_dev_os(dev_os)
    dev_work_path = _prompt_required("Development work path", dev_work_path)

    default_project_config = build_project_config(
        project,
        origin=origin,
        dev_host=dev_host,
        dev_user=dev_user,
        dev_os=dev_os,
        dev_work_path=dev_work_path,
    )
    local_repo_path = typer.prompt(
        "Local gateway repo path", default=default_project_config.local.repo_path
    )
    dev_cache_path = typer.prompt(
        "Development cache repo path", default=default_project_config.dev.cache_path
    )

    project_config = build_project_config(
        project,
        origin=origin,
        dev_host=dev_host,
        dev_user=dev_user,
        dev_os=dev_os,
        dev_work_path=dev_work_path,
        local_repo_path=local_repo_path,
        dev_cache_path=dev_cache_path,
    )

    config_path = default_config_path()
    console.print()
    console.print("Configuration to save:")
    console.print(f"config path: {config_path}")
    console.print(f"project: {project}")
    console.print(f"origin: {project_config.origin}")
    console.print(f"local gateway repo path: {project_config.local.repo_path}")
    console.print(f"development host: {project_config.dev.host}")
    console.print(f"development user: {project_config.dev.user}")
    console.print(f"development OS: {project_config.dev.os}")
    console.print(f"development work path: {project_config.dev.work_path}")
    console.print(f"development cache repo path: {project_config.dev.cache_path}")

    if not typer.confirm("Save this configuration?", default=True):
        console.print("Configuration not saved.")
        raise typer.Exit(code=1)

    config = load_config()
    updated = register_project(config, project, project_config, force=force)
    save_config(updated)
    console.print(f"Project '{project}' saved to {config_path}")
    console.print("Run `git-ssh-sync doctor {}` to check the setup.".format(project))


@app.callback()
def callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the application version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose output (INFO level).",
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            "-d",
            help="Enable debug output (DEBUG level).",
        ),
    ] = False,
    log_file: Annotated[
        str | None,
        typer.Option(
            "--log-file",
            help="Path to log file.",
        ),
    ] = None,
) -> None:
    """Sync Git commits through a local machine over SSH."""
    # Setup logging based on verbosity options
    if debug:
        level = "DEBUG"
    elif verbose:
        level = "INFO"
    else:
        level = "WARNING"

    setup_logging(level=level, log_file=log_file)


def _not_implemented(command: str, project: str | None = None) -> None:
    target = f" for project '{project}'" if project else ""
    console.print(
        f"[yellow]{command}[/yellow]{target} is defined, but the sync implementation is not available yet."
    )


@config_app.command("list")
def config_list_command() -> None:
    """List registered projects."""
    try:
        config = load_config()
    except ConfigError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    names = list_project_names(config)
    if not names:
        console.print("No projects configured.")
        return

    console.print("Configured projects:")
    for name in names:
        project_config = config.projects[name]
        console.print(f"- {escape(name)}")
        console.print(f"  origin: {escape(project_config.origin)}")
        console.print(f"  local repo: {escape(project_config.local.repo_path)}")
        console.print(f"  dev host: {escape(project_config.dev.host)}")
        console.print(f"  dev os: {escape(project_config.dev.os)}")
        console.print(f"  dev path: {escape(project_config.dev.work_path)}")


@config_app.command("show")
def config_show_command(
    project: Annotated[str, typer.Argument(help="Project name to show.")],
) -> None:
    """Show one registered project configuration."""
    try:
        project_config = get_project(load_config(), project)
    except ConfigError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    table = Table(title=f"Project configuration: {escape(project)}")
    table.add_column("Section", overflow="fold")
    table.add_column("Name", overflow="fold")
    table.add_column("Value", overflow="fold")
    table.add_row("project", "name", escape(project))
    table.add_row("origin", "url", escape(project_config.origin))
    table.add_row("local", "repo_path", escape(project_config.local.repo_path))
    table.add_row("dev", "host", escape(project_config.dev.host))
    table.add_row("dev", "user", escape(project_config.dev.user))
    table.add_row("dev", "os", escape(project_config.dev.os))
    table.add_row("dev", "work_path", escape(project_config.dev.work_path))
    table.add_row("dev", "cache_path", escape(project_config.dev.cache_path))
    table.add_row("options", "sync_tags", str(project_config.options.sync_tags))
    table.add_row("options", "lfs", str(project_config.options.lfs))
    table.add_row("options", "submodules", str(project_config.options.submodules))
    table.add_row("options", "ff_only", str(project_config.options.ff_only))
    console.print(table)


@config_app.command("remove")
def config_remove_command(
    project: Annotated[str, typer.Argument(help="Project name to remove.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Remove without confirmation."),
    ] = False,
) -> None:
    """Remove a registered project configuration."""
    if not yes and not typer.confirm(f"Remove project '{project}'?"):
        console.print("Aborted.")
        raise typer.Exit(code=1)

    try:
        remove_project(project)
    except ConfigError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' removed from {default_config_path()}")


@config_app.command("set")
def config_set_command(
    project: Annotated[str, typer.Argument(help="Project name to update.")],
    origin: Annotated[
        str | None,
        typer.Option("--origin", help="Origin Git URL."),
    ] = None,
    local_repo_path: Annotated[
        str | None,
        typer.Option("--local-repo-path", help="Local gateway repository path."),
    ] = None,
    dev_host: Annotated[
        str | None,
        typer.Option("--dev-host", help="Development environment SSH host."),
    ] = None,
    dev_user: Annotated[
        str | None,
        typer.Option("--dev-user", help="Development environment SSH user."),
    ] = None,
    dev_os: Annotated[
        Literal["posix", "windows"] | None,
        typer.Option("--dev-os", help="Development environment OS: posix or windows."),
    ] = None,
    dev_path: Annotated[
        str | None,
        typer.Option(
            "--dev-path", help="Development environment work repository path."
        ),
    ] = None,
    dev_cache_path: Annotated[
        str | None,
        typer.Option("--dev-cache-path", help="Development cache repository path."),
    ] = None,
    sync_tags: Annotated[
        bool | None,
        typer.Option("--sync-tags/--no-sync-tags", help="Enable or disable tag sync."),
    ] = None,
    lfs: Annotated[
        bool | None,
        typer.Option("--lfs/--no-lfs", help="Enable or disable Git LFS handling."),
    ] = None,
    submodules: Annotated[
        bool | None,
        typer.Option(
            "--submodules/--no-submodules",
            help="Enable or disable submodule handling.",
        ),
    ] = None,
    ff_only: Annotated[
        bool | None,
        typer.Option("--ff-only/--no-ff-only", help="Enable or disable ff-only sync."),
    ] = None,
) -> None:
    """Update one or more fields in a registered project configuration."""
    try:
        update_project(
            project,
            origin=origin,
            local_repo_path=local_repo_path,
            dev_host=dev_host,
            dev_user=dev_user,
            dev_os=dev_os,
            dev_work_path=dev_path,
            dev_cache_path=dev_cache_path,
            sync_tags=sync_tags,
            lfs=lfs,
            submodules=submodules,
            ff_only=ff_only,
        )
    except (ConfigError, NoConfigUpdateError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' updated in {default_config_path()}")


@app.command("init")
def init_command(
    project: Annotated[str, typer.Argument(help="Project name to register.")],
    origin: Annotated[
        str | None,
        typer.Option(
            "--origin", help="Origin Git URL, such as git@github.com:org/repo.git."
        ),
    ] = None,
    dev_host: Annotated[
        str | None,
        typer.Option("--dev-host", help="Development environment SSH host."),
    ] = None,
    dev_user: Annotated[
        str | None,
        typer.Option("--dev-user", help="Development environment SSH user."),
    ] = None,
    dev_os: Annotated[
        Literal["posix", "windows"],
        typer.Option("--dev-os", help="Development environment OS: posix or windows."),
    ] = "posix",
    dev_path: Annotated[
        str | None,
        typer.Option(
            "--dev-path", help="Development environment work repository path."
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing project configuration."),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive", help="Prompt for setup values before saving config."
        ),
    ] = False,
) -> None:
    """Create a project configuration."""
    try:
        if interactive:
            _init_project_interactive(
                project,
                origin=origin,
                dev_host=dev_host,
                dev_user=dev_user,
                dev_os=dev_os,
                dev_work_path=dev_path,
                force=force,
            )
            return

        project_config = init_project(
            project,
            origin=origin,
            dev_host=dev_host,
            dev_user=dev_user,
            dev_os=dev_os,
            dev_work_path=dev_path,
            force=force,
        )
    except ProjectAlreadyExistsError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    except ConfigError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' saved to {default_config_path()}")
    console.print(f"origin: {project_config.origin}")


@app.command("clone")
def clone_command(
    project: Annotated[str, typer.Argument(help="Project name to clone.")],
) -> None:
    """Clone the project locally and initialize the development environment."""
    try:
        clone_project(project)
    except (ConfigError, CloneError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' cloned.")


@app.command("attach")
def attach_command(
    project: Annotated[str, typer.Argument(help="Project name to attach.")],
    yes: Annotated[
        bool,
        typer.Option(
            "--yes", "-y", help="Apply planned operations without confirmation."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Show the attach plan without changing repositories."
        ),
    ] = False,
) -> None:
    """Attach existing repositories to git-ssh-sync management."""
    try:
        attach_project(
            project,
            yes=yes,
            dry_run=dry_run,
            confirm=lambda message: typer.confirm(message),
        )
    except (ConfigError, AttachError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    if dry_run:
        console.print(f"Project '{project}' attach dry-run completed.")
    else:
        console.print(f"Project '{project}' attached.")


@app.command("status")
def status_command(
    project: Annotated[str, typer.Argument(help="Project name to inspect.")],
) -> None:
    """Show synchronization state for origin, gateway, and development repositories."""
    try:
        status_project(project)
    except (ConfigError, StatusError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@app.command("branch")
def branch_command(
    project_or_action: Annotated[
        str,
        typer.Argument(help="Project name, or delete/prune cleanup action."),
    ],
    project: Annotated[str | None, typer.Argument(help="Project name.")] = None,
    branch: Annotated[str | None, typer.Argument(help="Branch to delete.")] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Apply cleanup without confirmation."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show planned cleanup without changing refs."),
    ] = False,
) -> None:
    """List or clean branch refs across origin, cache, and work repo."""
    try:
        if project_or_action == "delete":
            if project is None or branch is None:
                console.print(
                    "[red]Usage: git-ssh-sync branch delete <project> <branch>[/red]"
                )
                raise typer.Exit(code=2)
            branch_delete_project(
                project,
                branch,
                yes=yes,
                dry_run=dry_run,
                confirm=lambda message: typer.confirm(message),
            )
            return
        if project_or_action == "prune":
            if project is None or branch is not None:
                console.print("[red]Usage: git-ssh-sync branch prune <project>[/red]")
                raise typer.Exit(code=2)
            branch_prune_project(
                project,
                yes=yes,
                dry_run=dry_run,
                confirm=lambda message: typer.confirm(message),
            )
            return
        if project is not None or branch is not None:
            console.print("[red]Usage: git-ssh-sync branch <project>[/red]")
            raise typer.Exit(code=2)
        branch_project(project_or_action)
    except (ConfigError, BranchError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@app.command("pull")
def pull_command(
    project: Annotated[str, typer.Argument(help="Project name to pull.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show the planned pull without changing refs."),
    ] = False,
) -> None:
    """Fetch origin changes and fast-forward the current development branch."""
    try:
        pull_project(project, dry_run=dry_run)
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    if dry_run:
        console.print(f"Project '{project}' pull dry-run completed.")
    else:
        console.print(f"Project '{project}' pulled.")


@app.command("push")
def push_command(
    project: Annotated[str, typer.Argument(help="Project name to push.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show the planned push without changing refs."),
    ] = False,
) -> None:
    """Push current development branch commits to origin when it is safe to do so."""
    try:
        push_project(project, dry_run=dry_run)
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    if dry_run:
        console.print(f"Project '{project}' push dry-run completed.")
    else:
        console.print(f"Project '{project}' pushed.")


@app.command("sync-tags")
def sync_tags_command(
    project: Annotated[str, typer.Argument(help="Project name to synchronize tags.")],
    direction: Annotated[
        Literal["origin-to-dev", "dev-to-origin"],
        typer.Option(
            "--direction",
            help="Tag sync direction: origin-to-dev or dev-to-origin.",
        ),
    ] = "origin-to-dev",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Show the planned tag sync without changing refs."
        ),
    ] = False,
) -> None:
    """Synchronize Git tags without deleting or overwriting existing tags."""
    try:
        sync_tags_project(project, direction=direction, dry_run=dry_run)
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    if dry_run:
        console.print(f"Project '{project}' tag sync dry-run completed.")
    else:
        console.print(f"Project '{project}' tags synchronized.")


@app.command("checkout")
def checkout_command(
    project: Annotated[str, typer.Argument(help="Project name to update.")],
    branch: Annotated[
        str | None,
        typer.Argument(help="Branch to check out in the development repository."),
    ] = None,
    create_branch: Annotated[
        str | None,
        typer.Option(
            "-b",
            "--create-branch",
            help="Create and check out a new branch.",
        ),
    ] = None,
    base_branch: Annotated[
        str | None,
        typer.Option("--base", help="Create the branch from this branch."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show the planned checkout without changing refs or branches.",
        ),
    ] = False,
) -> None:
    """Switch the development repository to a branch."""
    target_branch = create_branch or branch
    if target_branch is None:
        console.print("[red]Specify a branch or -b <branch>.[/red]")
        raise typer.Exit(code=2)
    if base_branch is not None and create_branch is None:
        console.print("[red]--base can only be used with -b/--create-branch.[/red]")
        raise typer.Exit(code=2)
    try:
        checkout_project(
            project,
            target_branch,
            create=create_branch is not None,
            base_branch=base_branch,
            dry_run=dry_run,
        )
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    if dry_run:
        console.print(
            f"Project '{project}' checkout dry-run completed for {target_branch}."
        )
    else:
        console.print(f"Project '{project}' checked out {target_branch}.")


@app.command("doctor")
def doctor_command(
    project: Annotated[str, typer.Argument(help="Project name to diagnose.")],
    repair: Annotated[
        bool,
        typer.Option("--repair", help="Repair missing or mismatched gitsync wiring."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes", "-y", help="Apply repair operations without confirmation."
        ),
    ] = False,
) -> None:
    """Check local, SSH, Git, and repository layout prerequisites."""
    try:
        doctor_project(
            project,
            repair=repair,
            yes=yes,
            confirm=lambda message: typer.confirm(message),
        )
    except (ConfigError, DoctorError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@app.command("recover")
def recover_command(
    project: Annotated[str, typer.Argument(help="Project name to recover.")],
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Apply automatic repair operations without confirmation.",
        ),
    ] = False,
) -> None:
    """Diagnose sync failures and optionally repair safe repository wiring."""
    try:
        doctor_project(
            project,
            repair=yes,
            yes=yes,
            confirm=lambda message: typer.confirm(message),
        )
    except (ConfigError, DoctorError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@dev_app.command("status")
def dev_status_command(
    project: Annotated[str, typer.Argument(help="Project name to inspect.")],
) -> None:
    """Show `git status --short --branch` from the development work repo."""
    try:
        dev_status_project(project)
    except (ConfigError, DevCommandError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@dev_app.command("diff")
def dev_diff_command(
    project: Annotated[str, typer.Argument(help="Project name to inspect.")],
    stat: Annotated[
        bool,
        typer.Option("--stat", help="Show diffstat instead of the full diff."),
    ] = False,
    cached: Annotated[
        bool,
        typer.Option("--cached", help="Show staged changes."),
    ] = False,
) -> None:
    """Show uncommitted diff from the development work repo."""
    try:
        dev_diff_project(project, stat=stat, cached=cached)
    except (ConfigError, DevCommandError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


@dev_app.command("log")
def dev_log_command(
    project: Annotated[str, typer.Argument(help="Project name to inspect.")],
    max_count: Annotated[
        int,
        typer.Option(
            "--max-count",
            min=1,
            help="Maximum number of commits to show.",
        ),
    ] = 10,
) -> None:
    """Show recent one-line log entries from the development work repo."""
    try:
        dev_log_project(project, max_count=max_count)
    except (ConfigError, DevCommandError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


def main() -> None:
    app()
