"""Configuration file management for git-ssh-sync."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConfigError(Exception):
    """Base class for configuration errors."""


class ProjectAlreadyExistsError(ConfigError):
    """Raised when a project already exists and overwrite was not requested."""


class ProjectNotFoundError(ConfigError):
    """Raised when a project is not registered."""


class NoConfigUpdateError(ConfigError):
    """Raised when no project configuration updates were provided."""


def _expand_path(value: str) -> str:
    return str(Path(value).expanduser())


class LocalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_path: str

    _expand_repo_path = field_validator("repo_path")(_expand_path)


class DevConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    user: str = Field(min_length=1)
    work_path: str = Field(min_length=1)
    cache_path: str = Field(min_length=1)

    _expand_work_path = field_validator("work_path")(_expand_path)
    _expand_cache_path = field_validator("cache_path")(_expand_path)


class OptionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_tags: bool = True
    lfs: bool = False
    submodules: bool = False
    ff_only: bool = True


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=1)
    local: LocalConfig
    dev: DevConfig
    options: OptionsConfig = Field(default_factory=OptionsConfig)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)


def default_config_path() -> Path:
    """Return the default config path for the current platform."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "git-ssh-sync" / "config.yaml"


def format_validation_error(error: ValidationError) -> str:
    """Format validation errors with project and field context."""
    messages: list[str] = []
    for item in error.errors():
        loc = item.get("loc", ())
        field = ".".join(str(part) for part in loc)
        if len(loc) >= 3 and loc[0] == "projects":
            project = loc[1]
            project_field = ".".join(str(part) for part in loc[2:])
            messages.append(
                f"project '{project}' field '{project_field}': {item['msg']}"
            )
        else:
            messages.append(f"field '{field}': {item['msg']}")
    return "Invalid configuration: " + "; ".join(messages)


def load_config(path: Path | None = None) -> AppConfig:
    """Load config.yaml, returning an empty config when it does not exist."""
    config_path = path or default_config_path()
    if not config_path.exists():
        return AppConfig()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    try:
        return AppConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigError(format_validation_error(error)) from error


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Save config.yaml."""
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def get_project(config: AppConfig, project: str) -> ProjectConfig:
    """Return a project config or raise a descriptive error."""
    try:
        return config.projects[project]
    except KeyError as error:
        raise ProjectNotFoundError(f"Project '{project}' is not configured.") from error


def list_project_names(config: AppConfig) -> list[str]:
    """Return configured project names sorted for stable CLI output."""
    return sorted(config.projects)


def remove_project(
    project: str,
    *,
    config_path: Path | None = None,
) -> None:
    """Remove a project from config.yaml."""
    config = load_config(config_path)
    get_project(config, project)
    projects = dict(config.projects)
    del projects[project]
    save_config(config.model_copy(update={"projects": projects}), config_path)


def update_project(
    project: str,
    *,
    origin: str | None = None,
    local_repo_path: str | None = None,
    dev_host: str | None = None,
    dev_user: str | None = None,
    dev_work_path: str | None = None,
    dev_cache_path: str | None = None,
    sync_tags: bool | None = None,
    lfs: bool | None = None,
    submodules: bool | None = None,
    ff_only: bool | None = None,
    config_path: Path | None = None,
) -> ProjectConfig:
    """Partially update an existing project in config.yaml."""
    config = load_config(config_path)
    current = get_project(config, project)
    raw = current.model_dump(mode="json")

    updated = False
    if origin is not None:
        raw["origin"] = origin
        updated = True
    if local_repo_path is not None:
        raw["local"]["repo_path"] = local_repo_path
        updated = True
    if dev_host is not None:
        raw["dev"]["host"] = dev_host
        updated = True
    if dev_user is not None:
        raw["dev"]["user"] = dev_user
        updated = True
    if dev_work_path is not None:
        raw["dev"]["work_path"] = dev_work_path
        updated = True
    if dev_cache_path is not None:
        raw["dev"]["cache_path"] = dev_cache_path
        updated = True

    for key, value in {
        "sync_tags": sync_tags,
        "lfs": lfs,
        "submodules": submodules,
        "ff_only": ff_only,
    }.items():
        if value is not None:
            raw["options"][key] = value
            updated = True

    if not updated:
        raise NoConfigUpdateError("Specify at least one setting to update.")

    try:
        updated_project = ProjectConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(
            format_validation_error_for_project(project, error)
        ) from error

    save_config(
        register_project(config, project, updated_project, force=True),
        config_path,
    )
    return updated_project


def build_project_config(
    project: str,
    *,
    origin: str | None,
    dev_host: str | None,
    dev_user: str | None,
    dev_work_path: str | None,
    local_repo_path: str | None = None,
    dev_cache_path: str | None = None,
    options: OptionsConfig | None = None,
) -> ProjectConfig:
    """Build and validate a project config, applying init defaults."""
    raw: dict[str, Any] = {
        "origin": origin,
        "local": {
            "repo_path": local_repo_path or f"~/.git-ssh-sync/repos/{project}",
        },
        "dev": {
            "host": dev_host,
            "user": dev_user,
            "work_path": dev_work_path,
            "cache_path": dev_cache_path
            or f"/home/{dev_user}/.git-ssh-sync/cache/{project}.git",
        },
        "options": (options or OptionsConfig()).model_dump(mode="json"),
    }
    try:
        return ProjectConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(
            format_validation_error_for_project(project, error)
        ) from error


def format_validation_error_for_project(project: str, error: ValidationError) -> str:
    """Format project creation validation errors."""
    messages = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"])
        messages.append(f"project '{project}' field '{field}': {item['msg']}")
    return "Invalid configuration: " + "; ".join(messages)


def register_project(
    config: AppConfig,
    project: str,
    project_config: ProjectConfig,
    *,
    force: bool = False,
) -> AppConfig:
    """Register or update a project in an app config."""
    if project in config.projects and not force:
        raise ProjectAlreadyExistsError(
            f"Project '{project}' already exists. Use --force to overwrite it."
        )

    projects = dict(config.projects)
    projects[project] = project_config
    return config.model_copy(update={"projects": projects})


def init_project(
    project: str,
    *,
    origin: str | None,
    dev_host: str | None,
    dev_user: str | None,
    dev_work_path: str | None,
    force: bool = False,
    config_path: Path | None = None,
) -> ProjectConfig:
    """Create or update a project in config.yaml."""
    config = load_config(config_path)
    project_config = build_project_config(
        project,
        origin=origin,
        dev_host=dev_host,
        dev_user=dev_user,
        dev_work_path=dev_work_path,
    )
    updated = register_project(config, project, project_config, force=force)
    save_config(updated, config_path)
    return project_config
