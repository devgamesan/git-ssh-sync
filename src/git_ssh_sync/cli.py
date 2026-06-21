"""Command line interface for git-ssh-sync."""

from typing import Annotated

import typer
from rich.markup import escape

from git_ssh_sync import __version__
from git_ssh_sync.clone import CloneError, clone_project
from git_ssh_sync.config import (
    ConfigError,
    ProjectAlreadyExistsError,
    default_config_path,
    init_project,
)
from git_ssh_sync.console import console
from git_ssh_sync.doctor import DoctorError, doctor_project
from git_ssh_sync.errors import CommandExecutionError
from git_ssh_sync.status import StatusError, status_project
from git_ssh_sync.sync import SyncError, checkout_project, pull_project, push_project

app = typer.Typer(
    name="git-ssh-sync",
    help="Sync Git commits through a local machine over SSH.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"git-ssh-sync {__version__}")
        raise typer.Exit()


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
) -> None:
    """Sync Git commits through a local machine over SSH."""


def _not_implemented(command: str, project: str | None = None) -> None:
    target = f" for project '{project}'" if project else ""
    console.print(
        f"[yellow]{command}[/yellow]{target} is defined, but the sync implementation is not available yet."
    )


def _require_branch(branch: str | None) -> str:
    if branch is None:
        console.print("[red]--branch is required.[/red]")
        raise typer.Exit(code=2)
    return branch


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
    dev_path: Annotated[
        str | None,
        typer.Option(
            "--dev-path", help="Development environment work repository path."
        ),
    ] = None,
    branch: Annotated[
        str,
        typer.Option("--branch", help="Default branch to synchronize."),
    ] = "main",
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing project configuration."),
    ] = False,
) -> None:
    """Create a project configuration."""
    try:
        project_config = init_project(
            project,
            origin=origin,
            default_branch=branch,
            dev_host=dev_host,
            dev_user=dev_user,
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
    console.print(f"default_branch: {project_config.default_branch}")


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


@app.command("pull")
def pull_command(
    project: Annotated[str, typer.Argument(help="Project name to pull.")],
    branch: Annotated[
        str | None,
        typer.Option("--branch", help="Branch to pull."),
    ] = None,
) -> None:
    """Fetch origin changes and fast-forward the development repository."""
    branch = _require_branch(branch)
    try:
        pull_project(project, branch=branch)
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' pulled.")


@app.command("push")
def push_command(
    project: Annotated[str, typer.Argument(help="Project name to push.")],
    branch: Annotated[
        str | None,
        typer.Option("--branch", help="Branch to push."),
    ] = None,
) -> None:
    """Push development commits to origin when it is safe to do so."""
    branch = _require_branch(branch)
    try:
        push_project(project, branch=branch)
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' pushed.")


@app.command("checkout")
def checkout_command(
    project: Annotated[str, typer.Argument(help="Project name to update.")],
    branch: Annotated[
        str, typer.Argument(help="Branch to check out in the development repository.")
    ],
    base_branch: Annotated[
        str | None,
        typer.Option(
            "--base",
            help="Create the branch from this origin branch before checking it out.",
        ),
    ] = None,
) -> None:
    """Switch the development repository to a branch."""
    try:
        checkout_project(project, branch, base_branch=base_branch)
    except (ConfigError, SyncError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Project '{project}' checked out {branch}.")


@app.command("doctor")
def doctor_command(
    project: Annotated[str, typer.Argument(help="Project name to diagnose.")],
) -> None:
    """Check local, SSH, Git, and repository layout prerequisites."""
    try:
        doctor_project(project)
    except (ConfigError, DoctorError, CommandExecutionError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(code=1) from error


def main() -> None:
    app()
