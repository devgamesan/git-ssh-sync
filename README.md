[![日本語](https://img.shields.io/badge/lang-日本語-blue)](README.ja.md) [![English](https://img.shields.io/badge/lang-English-brightgreen)](README.md)

# git-ssh-sync

[![CI](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Release](https://img.shields.io/github/v/release/devgamesan/git-ssh-sync)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`git-ssh-sync` is a CLI tool for synchronizing Git commits created in a development environment that cannot directly access GitHub/GitLab to external Git services via a local machine.

This tool is designed for niche environments where outbound network access is restricted, such as high-security enterprises and projects that only allow limited inbound communication (e.g., SSH, RDP).

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
- `--dev-os`: Development environment OS, either `posix` or `windows` (default: `posix`)
- `--dev-path`: Path to the work repository on the development environment

For a Windows development environment, specify `--dev-os windows` and use Windows
paths. Windows SSH commands are executed through PowerShell.

```powershell
git-ssh-sync init myproject `
  --origin git@github.com:example/myproject.git `
  --dev-host devserver `
  --dev-user user `
  --dev-os windows `
  --dev-path C:\Users\user\work\myproject
```

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

You can inspect and maintain registered projects without opening the config file directly.

```bash
# List registered projects
git-ssh-sync config list

# Show all settings for one project
git-ssh-sync config show myproject

# Update selected settings
git-ssh-sync config set myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-os posix \
  --dev-path /home/user/work/myproject

# Remove a project after confirmation
git-ssh-sync config remove myproject

# Remove a project without an interactive prompt
git-ssh-sync config remove myproject --yes
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

## Attaching Existing Repositories

If the gateway repository, development work repository, or cache repository already
exists, use `attach` instead of `clone`.

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject
git-ssh-sync attach myproject --dry-run
git-ssh-sync attach myproject
git-ssh-sync doctor myproject
```

`attach` inspects the configured origin URL, current branch, development work
tree state, bare cache repository, and `gitsync` remote. Before changing
anything, it prints the operations it will apply. Use `--yes` for non-interactive
execution after reviewing the plan.

```bash
git-ssh-sync attach myproject --yes
```

If only the `gitsync` remote or cache wiring is missing or mismatched, run
`doctor --repair` to inspect and repair it through the same preflight checks.

```bash
git-ssh-sync doctor myproject --repair
git-ssh-sync doctor myproject --repair --yes
```

`attach` and `doctor --repair` do not commit, stash, merge, or rebase existing
work. If the development work tree is dirty, or if a path is not a compatible Git
repository, the command stops and prints the manual recovery action.

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

Use `--dry-run` to inspect the planned operations and preflight checks before changing refs:

```bash
git-ssh-sync pull myproject --dry-run
git-ssh-sync push myproject --dry-run
```

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

To preview a branch switch or branch creation without changing origin, cache, or work repo refs:

```bash
git-ssh-sync checkout myproject feature/foo --dry-run
git-ssh-sync checkout myproject -b feature/foo --base develop --dry-run
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

To inspect the development work repo directly from the local machine, use the
read-only `dev` commands.

```bash
git-ssh-sync dev status myproject
git-ssh-sync dev diff myproject
git-ssh-sync dev diff myproject --stat
git-ssh-sync dev log myproject --max-count 5
```

These commands run `git status`, `git diff`, or `git log` on the development
work repo over SSH. They do not update origin, the local gateway repo, the
development cache repo, or the development work repo refs.

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

# List registered project settings
git-ssh-sync config list

# Show registered project settings
git-ssh-sync config show myproject

# Initial clone
git-ssh-sync clone myproject

# Check synchronization status
git-ssh-sync status myproject

# Check branch status
git-ssh-sync branch myproject

# Inspect development work repo status
git-ssh-sync dev status myproject

# Inspect development work repo diff
git-ssh-sync dev diff myproject --stat

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

## Logging

`git-ssh-sync` supports detailed logging for troubleshooting and monitoring synchronization operations.

### Log Levels

By default, only warnings and errors are displayed. You can increase verbosity using the following options:

- `--verbose`, `-v`: Enable INFO level logging (operation progress, Git/SSH commands)
- `--debug`, `-d`: Enable DEBUG level logging (all debug information, command output, stack traces)

### Log File Output

Logs are automatically saved to `~/.cache/git-ssh-sync/logs/git-ssh-sync.log`. The log file contains all log levels (DEBUG and above) regardless of console output settings.

You can specify a custom log file path using `--log-file`:

```bash
git-ssh-sync pull myproject --log-file /tmp/my-sync.log
```

### Usage Examples

```bash
# Default (warnings and errors only)
git-ssh-sync pull myproject

# Verbose output (operation progress)
git-ssh-sync pull myproject --verbose

# Debug output (all details including command execution)
git-ssh-sync pull myproject --debug

# Verbose with custom log file
git-ssh-sync push myproject --verbose --log-file /tmp/sync.log

# Debug output for diagnostics
git-ssh-sync doctor myproject --debug
```

### Log Content

- **INFO**: Operation progress (pull/push/checkout), success messages
- **DEBUG**: Git/SSH commands executed, return codes, stdout/stderr, working directories
- **WARNING**: Recoverable issues (LFS, submodules detected)
- **ERROR**: Failures, execution errors

Logs are particularly useful when troubleshooting SSH connection issues, Git command failures, or understanding the synchronization flow.

## For Developers

To develop this repository itself, install dependencies using `uv sync`.

```bash
uv sync
```

To install from TestPyPI:

```bash
uv tool install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-best-match \
  git-ssh-sync
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
