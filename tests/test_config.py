from pathlib import Path

import pytest

from git_ssh_sync.config import (
    ConfigError,
    ProjectAlreadyExistsError,
    build_project_config,
    get_project,
    init_project,
    load_config,
    register_project,
)


def test_init_project_saves_defaults_and_expands_local_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"

    project = init_project(
        "myproject",
        origin="git@github.com:example/myproject.git",
        default_branch="main",
        dev_host="devserver",
        dev_user="user",
        dev_work_path="/home/user/work/myproject",
        config_path=config_path,
    )

    assert project.local.repo_path == str(
        tmp_path / ".git-ssh-sync" / "repos" / "myproject"
    )
    assert project.dev.cache_path == "/home/user/.git-ssh-sync/cache/myproject.git"

    loaded = load_config(config_path)
    loaded_project = get_project(loaded, "myproject")

    assert loaded_project.origin == "git@github.com:example/myproject.git"
    assert loaded_project.default_branch == "main"
    assert loaded_project.options.sync_tags is True
    assert loaded_project.options.lfs is False
    assert loaded_project.options.submodules is False
    assert loaded_project.options.ff_only is True


def test_register_project_requires_force_for_existing_project(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    first = init_project(
        "myproject",
        origin="git@github.com:example/first.git",
        default_branch="main",
        dev_host="devserver",
        dev_user="user",
        dev_work_path="/home/user/work/myproject",
        config_path=config_path,
    )

    config = load_config(config_path)
    with pytest.raises(ProjectAlreadyExistsError, match="Use --force"):
        register_project(config, "myproject", first)


def test_init_project_force_overwrites_existing_project(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    init_project(
        "myproject",
        origin="git@github.com:example/first.git",
        default_branch="main",
        dev_host="devserver",
        dev_user="user",
        dev_work_path="/home/user/work/myproject",
        config_path=config_path,
    )

    init_project(
        "myproject",
        origin="git@github.com:example/second.git",
        default_branch="develop",
        dev_host="devserver",
        dev_user="user",
        dev_work_path="/home/user/work/myproject",
        force=True,
        config_path=config_path,
    )

    project = get_project(load_config(config_path), "myproject")

    assert project.origin == "git@github.com:example/second.git"
    assert project.default_branch == "develop"


def test_missing_required_fields_include_project_and_field_names() -> None:
    with pytest.raises(ConfigError) as exc_info:
        build_project_config(
            "myproject",
            origin=None,
            default_branch="main",
            dev_host=None,
            dev_user="user",
            dev_work_path=None,
        )

    message = str(exc_info.value)

    assert "project 'myproject' field 'origin'" in message
    assert "project 'myproject' field 'dev.host'" in message
    assert "project 'myproject' field 'dev.work_path'" in message


def test_load_config_reports_invalid_project_field(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
version: 1
projects:
  myproject:
    origin: git@github.com:example/myproject.git
    default_branch: main
    local: {}
    dev:
      host: devserver
      user: user
      work_path: /home/user/work/myproject
      cache_path: /home/user/.git-ssh-sync/cache/myproject.git
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="project 'myproject' field 'local.repo_path'"
    ):
        load_config(config_path)
