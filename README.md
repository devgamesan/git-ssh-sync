[![日本語](https://img.shields.io/badge/lang-日本語-blue)](README.ja.md) [![English](https://img.shields.io/badge/lang-English-brightgreen)](README.md)

# git-ssh-sync

[![CI](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Release](https://img.shields.io/github/v/release/devgamesan/git-ssh-sync)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`git-ssh-sync` is a CLI tool for synchronizing Git commits created in a development environment that cannot directly access GitHub/GitLab to external Git services via a local machine.

This is not a file synchronization tool. It synchronizes Git objects and branches. Source editing, building, testing, and committing are performed in the development environment, while communication with GitHub/GitLab is handled by the local machine.

## Prerequisites

`git-ssh-sync` assumes the following configuration:

```text
GitHub / GitLab
    ↑↓
Local machine
    ↑↓ SSH
Development environment
```

Local machine:

- Can access GitHub / GitLab
- Can SSH to the development environment
- Has `git` and `uv` available
- Uses `git-ssh-sync` for commit synchronization, status checks, and diagnostics between GitHub/GitLab and the development environment

Development environment:

- Can be accessed via SSH from the local machine
- Cannot directly access GitHub / GitLab from the development environment
- Has `git` available
- Performs source editing, building, testing, and committing
- Synchronizes with GitHub/GitLab via the local machine

## Installation

For normal use, install on your local machine using `uv tool install`.

```bash
uv tool install git-ssh-sync
```

For unreleased versions or the latest repository version, install directly from GitHub.

```bash
uv tool install git+https://github.com/devgamesan/git-ssh-sync.git
```

After installation, verify that the command can be executed.

```bash
git-ssh-sync --help
```

## Configuration

First, register the project you want to synchronize.

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject
```

Key parameters:

- `myproject`: Project name for `git-ssh-sync`
- `--origin`: Repository URL on the GitHub / GitLab side
- `--dev-host`: SSH host of the development environment
- `--dev-user`: SSH user of the development environment
- `--dev-path`: Path to the work repository on the development environment

For `--origin`, specify a remote URL that can be used with `git clone` or `git fetch`. Main formats are:

```text
git@github.com:example/myproject.git
git@gitlab.com:example/myproject.git
ssh://git@github.com/example/myproject.git
https://github.com/example/myproject.git
https://gitlab.com/example/myproject.git
```

When using SSH format, prepare SSH keys and authentication settings for connecting to GitHub/GitLab on the local machine. The development environment does not connect directly to GitHub/GitLab.

To overwrite existing configuration, use `--force`.

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject \
  --force
```

## Initial Workflow

For the first time, execute configuration, clone to the development environment, and diagnostics in order.

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject
git-ssh-sync clone myproject
git-ssh-sync doctor myproject
```

`clone` creates a gateway repository on your local machine and deploys cache and work repositories on the development environment.

- Gateway repository: Relay repository on the local machine
- Cache repository: Bare repository on the development environment
- Work repository: Repository where actual editing, building, testing, and committing are performed on the development environment

Afterward, the work repository on the development environment can be used as a normal Git repository.

`doctor` checks the local environment, SSH connection, fetch/push permissions to origin, and repository deployment on the development environment. Run this not only for the first time but also when synchronization is not working properly.

## Daily Development Workflow

For daily development, `pull` from the local machine before starting work, commit normally in the development environment, and finally `push` from the local machine.

Local machine:

```bash
git-ssh-sync pull myproject
```

Development environment:

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Add feature"
```

Local machine:

```bash
git-ssh-sync push myproject
```

`pull` and `push` target the current branch of the work repository on the development environment. To synchronize a different branch, switch the work repository branch with `checkout` first.

## Branch Switching Workflow

To switch to an existing branch, execute `checkout` from the local machine.

Local machine:

```bash
git-ssh-sync checkout myproject feature/foo
```

To create a new branch, use `-b`. Use `--base` together to explicitly specify the starting point.

```bash
git-ssh-sync checkout myproject -b feature/foo --base develop
```

Development environment:

```bash
cd ~/work/myproject
git status
git add .
git commit -m "Implement foo"
```

Local machine:

```bash
git-ssh-sync push myproject
```

`checkout -b feature/foo --base develop` creates `feature/foo` on origin based on `develop` from origin and switches the work repository on the development environment to that branch. If `--base` is omitted, the current branch of the work repository on the development environment is used as the starting point. If a branch with the same name already exists on origin, switch to the existing branch without `-b`.

## Status Check

Use `status` to check synchronization status.

```bash
git-ssh-sync status myproject
```

`status` displays the ahead/behind status between origin and the development environment, and the working tree status for the current branch of the work repository. Follow the displayed recommendation and execute `pull` or `push` as necessary.

To list existence status and ahead/behind for each branch, use `branch`.

```bash
git-ssh-sync branch myproject
```

## Operational Rules

When using `git-ssh-sync`, following these rules makes it easier to understand the state:

- `pull` on the local machine before starting work
- Create commits in the development environment
- `push` on the local machine when work is done
- Check `status` when in doubt before/after synchronization
- Run `doctor` when concerned about connections or repository deployment

Uncommitted changes are not synchronized. If there are uncommitted changes in the working tree of the development environment, the changes themselves are not sent to the local machine or origin. Please `git add` and `git commit` changes you want to synchronize in the development environment.

`pull` updates the development environment branch only when fast-forward is possible. If origin and the development environment have diverged, automatic merge or automatic rebase is not performed.

`push` executes only when the branch on the origin side is an ancestor of the branch on the development environment side. If there are unobtained commits on origin, it stops.

When diverged, automatic resolution is not performed. Execute `pull` on the local machine, follow the displayed instructions to merge or rebase in the development environment, then `push` again.

## Common Commands

```bash
# Display help
git-ssh-sync --help

# Register a project
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject

# Initial clone
git-ssh-sync clone myproject

# Check synchronization status
git-ssh-sync status myproject

# Check branch status
git-ssh-sync branch myproject

# Reflect changes from origin to development environment
git-ssh-sync pull myproject

# Reflect commits from development environment to origin
git-ssh-sync push myproject

# Switch development environment branch
git-ssh-sync checkout myproject feature/foo

# Create and switch to new branch from base branch
git-ssh-sync checkout myproject -b feature/foo --base develop

# Diagnostics
git-ssh-sync doctor myproject
```

## For Developers

To develop this repository itself, install dependencies using `uv sync`.

```bash
uv sync
```

To execute the CLI during development, you can run it via `uv run`.

```bash
uv run git-ssh-sync --help
```

Tests are executed with the following command:

```bash
uv run pytest
```

## Related Documentation

- [Specification](docs/spec.md)
