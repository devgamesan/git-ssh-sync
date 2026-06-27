[![日本語](https://img.shields.io/badge/lang-日本語-blue)](README.ja.md) [![English](https://img.shields.io/badge/lang-English-brightgreen)](README.md)

# git-ssh-sync

[![CI](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/devgamesan/git-ssh-sync/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)
![Release](https://img.shields.io/github/v/release/devgamesan/git-ssh-sync)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

`git-ssh-sync` is a CLI tool for synchronizing Git commits created in a development environment that cannot directly access GitHub/GitLab to external Git services via a local machine.

This tool is designed for niche environments where outbound network access is restricted, such as high-security enterprises and projects that only allow limited inbound communication (e.g., SSH, RDP).

## Start here

If you are new to `git-ssh-sync`, read these sections in order:

| Goal | Section |
|---|---|
| Check whether this tool fits your environment | [Who is this for?](#who-is-this-for) |
| Understand the repository layout | [Architecture](#architecture) |
| Install and run the shortest setup | [Quick start](#quick-start) |
| Register a real project | [Configuration](#configuration) |
| Work day to day | [Daily Development Workflow](#daily-development-workflow) |
| Recover from stopped synchronization | [Troubleshooting](#troubleshooting) |

The common path is:

1. Install `git-ssh-sync` on the local machine.
2. Register a project with `init`.
3. Create or attach the development repositories with `clone` or `attach`.
4. Run `pull` before editing and `push` after committing on the development environment.

## Who is this for?

Use `git-ssh-sync` if:

- Your development environment cannot access GitHub / GitLab directly.
- Your local machine can access GitHub / GitLab.
- Your local machine can SSH into the development environment.
- You want to edit, build, test, and commit in the development environment.
- You want to synchronize by Git commits and branches instead of copying files manually.

If your development environment can already access GitHub / GitLab directly, you usually do not need this tool.

This is not a file synchronization tool. It synchronizes Git objects and branches. Source editing, building, testing, and committing are performed in the development environment, while communication with GitHub/GitLab is handled by the local machine.

## Architecture

`git-ssh-sync` keeps GitHub/GitLab access on the local machine and Git work on
the development environment.

```text
origin: GitHub / GitLab
    ↑↓
local gateway repo
    ↑↓ git over SSH
dev bare cache repo
    ↑↓
dev work repo
```

Terms used throughout this document:

| Term | Meaning |
|---|---|
| `origin` | Original remote repository on GitHub / GitLab |
| `local gateway repo` | Relay repository on the local machine |
| `dev bare cache repo` | Bare repository on the development environment |
| `dev work repo` | Repository where you edit, build, test, and commit on the development environment |
| `gitsync remote` | Remote in the dev work repo that points to the dev bare cache repo |

## Current limitations

The following features are not supported yet:

- Git LFS
- Git submodules
- automatic conflict resolution
- synchronizing uncommitted file changes

## Prerequisites

`git-ssh-sync` assumes the following configuration:

```text
GitHub / GitLab
    ↑↓
Local machine
    ↑↓ SSH
Development environment
```

| Place | Requirements |
|---|---|
| Local machine | Can access GitHub / GitLab, can SSH to the development environment, and has `git` and `uv` available |
| Development environment | Can be accessed via SSH from the local machine, has `git` available, and does not need direct GitHub / GitLab access |

For v1.0, `git-ssh-sync` supports Python 3.12 and 3.13. CI runs the full test
suite on both supported versions.

Run `git-ssh-sync` on the local machine. Edit, build, test, and commit on the
development environment. Synchronization between the two sides happens through
Git commits and branches.

## Safety model

`git-ssh-sync` does not:

- Synchronize uncommitted files
- Automatically merge or rebase branches
- Force-push to origin
- Modify a dirty development work tree
- Require GitHub/GitLab credentials on the development environment
- Require direct outbound access from the development environment to GitHub/GitLab

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

## Quick start

After installing `git-ssh-sync`, the shortest path from setup to daily sync is:

```bash
uv tool install git-ssh-sync

git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-path /home/user/work/myproject

git-ssh-sync clone myproject
git-ssh-sync doctor myproject

git-ssh-sync pull myproject

# On the development environment:
# cd ~/work/myproject
# git add .
# git commit -m "Add feature"

git-ssh-sync status myproject
git-ssh-sync push myproject
```

Run `clone` and `doctor` for the first setup. For regular work, run `pull`
before editing, commit on the development environment, then check `status` and
run `push` from the local machine.

## Configuration

First, register the project you want to synchronize.

For guided first-time setup, use interactive mode. It prompts for required
values, shows generated defaults, and asks for confirmation before writing the
configuration.

```bash
git-ssh-sync init myproject --interactive
```

After saving, run `doctor` to check the configuration and connectivity.

```bash
git-ssh-sync doctor myproject
```

You can also provide all values non-interactively.

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
  --dev-path 'C:\Users\user\work\myproject'
```

When running the command from macOS or Linux shells such as `zsh` or `bash`,
quote Windows paths that contain backslashes. Otherwise the shell can remove the
backslashes before `git-ssh-sync` receives the argument. You can also use forward
slashes, for example `C:/Users/user/work/myproject`.

When `--dev-os windows` is used, the default cache path is
`C:\Users\<dev-user>\.git-ssh-sync\cache\<project>.git`. `clone` stops if either
the configured work path or cache path already exists on the development
environment, so remove stale directories or use the attach/recover workflow for
existing repositories.

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

### Configuration file

Project settings are saved as YAML. The default path depends on the local
machine where `git-ssh-sync` runs:

```text
macOS / Linux: ~/.config/git-ssh-sync/config.yaml
Windows:       %APPDATA%\git-ssh-sync\config.yaml
```

A generated configuration looks like this:

```yaml
version: 1

projects:
  myproject:
    origin: git@github.com:example/myproject.git

    local:
      repo_path: ~/.git-ssh-sync/repos/myproject

    dev:
      host: devserver
      user: user
      os: posix
      work_path: /home/user/work/myproject
      cache_path: /home/user/.git-ssh-sync/cache/myproject.git

    options:
      sync_tags: true
      lfs: false
      submodules: false
      ff_only: true
```

Main fields:

- `origin`: GitHub / GitLab repository URL used by the local gateway repository
- `local.repo_path`: Local gateway repository path managed by `git-ssh-sync`
- `dev.host`, `dev.user`, `dev.os`: SSH connection target and remote OS
- `dev.work_path`: Work repository path on the development environment
- `dev.cache_path`: Bare cache repository path on the development environment
- `options.sync_tags`: Enable explicit Git tag synchronization
- `options.lfs`: Reserved option for Git LFS support
- `options.submodules`: Reserved option for submodule support
- `options.ff_only`: Keep synchronization fast-forward only

In normal use, manage this file with `git-ssh-sync init` and
`git-ssh-sync config` commands. If you edit it manually, keep the YAML
structure unchanged and use paths that are valid on the machine or
development environment where each field is used.

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

`clone` creates the local gateway repo and deploys the dev bare cache repo and
dev work repo described above.

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

Use this table to choose between setup diagnostics, wiring repair, and recovery
after an interrupted sync.

| Situation | Command |
|---|---|
| Check initial setup or connectivity | `git-ssh-sync doctor myproject` |
| Repair missing or mismatched `gitsync` remote/cache wiring | `git-ssh-sync doctor myproject --repair` |
| Diagnose after interrupted `pull` / `push` | `git-ssh-sync recover myproject` |
| Apply only safe wiring repairs after interruption | `git-ssh-sync recover myproject --yes` |

If only the `gitsync` remote or cache wiring is missing or mismatched, run
`doctor --repair` to inspect and repair it through the same preflight checks.

```bash
git-ssh-sync doctor myproject --repair
git-ssh-sync doctor myproject --repair --yes
```

After an interrupted `pull` or `push`, use `recover` as the recovery-oriented
entry point. Without `--yes`, it diagnoses origin, gateway, cache, and work
repository state and prints concrete next actions. With `--yes`, it applies only
safe wiring repairs such as creating the cache repository, seeding the cache
branch, or fixing the `gitsync` remote.

```bash
git-ssh-sync recover myproject
git-ssh-sync recover myproject --yes
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

If you are not sure about the current state at the beginning of work, first check synchronization status from the local machine and run `pull` when needed.

```bash
git-ssh-sync status myproject
git-ssh-sync pull myproject
git-ssh-sync dev status myproject
```

If `dev status` shows a dirty working tree on the development environment, uncommitted changes are not synchronized. Inspect the diff on the development environment and commit the changes you want to synchronize before `push`.

```bash
git-ssh-sync dev diff myproject --stat
```

Before pushing, confirm that the development environment changes are committed, then run `status` and `push` from the local machine.

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

Use `--dry-run` to inspect the planned operations and preflight checks before changing refs:

```bash
git-ssh-sync pull myproject --dry-run
git-ssh-sync push myproject --dry-run
```

## Tag Synchronization Workflow

Tags are synchronized explicitly so release refs are not changed during normal
branch `pull` / `push` operations. `sync-tags` only creates missing tags. It
stops when an existing tag name points to a different object, and it does not
delete, overwrite, or force-update tags.

To bring release tags from origin into the development environment:

```bash
git-ssh-sync sync-tags myproject --dry-run
git-ssh-sync sync-tags myproject
```

To publish tags created in the development work repository back to origin:

```bash
git-ssh-sync sync-tags myproject --direction dev-to-origin --dry-run
git-ssh-sync sync-tags myproject --direction dev-to-origin
```

Recommended release flow:

1. Run `git-ssh-sync pull myproject` before release work.
2. Create the release tag in the development work repository.
3. Run `git-ssh-sync sync-tags myproject --direction dev-to-origin --dry-run`.
4. If the dry-run reports only the intended new tag, run the command without
   `--dry-run`.

## Workflow When Push Stops

`push` executes only when the branch on the origin side is an ancestor of the branch on the development environment side. It stops when origin has commits that have not been pulled yet, or when origin and the development environment have diverged.

In that case, run `pull` from the local machine to deliver origin changes to the development environment.

```bash
git-ssh-sync pull myproject
```

If `pull` cannot fast-forward, `git-ssh-sync` does not automatically merge or rebase. Resolve it with normal Git operations on the development environment, using either merge or rebase, then run `push` again from the local machine.

Example using merge:

```bash
cd ~/work/myproject
git fetch gitsync
git merge gitsync/main
# If there are conflicts, edit the files
git status
git add <resolved-files>
git commit
```

Example using rebase:

```bash
cd ~/work/myproject
git fetch gitsync
git rebase gitsync/main
# If there are conflicts, edit the files
git status
git add <resolved-files>
git rebase --continue
```

If the branch is not `main`, replace `gitsync/main` with the target branch. After merge or rebase completes, check status from the local machine and push.

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

After rebase, only rewrite commits that exist only on the development environment and have not been pushed to origin yet. If you want to avoid rewriting history on a shared branch, use merge.

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

To remove a branch after checking the affected refs, use `branch delete`.
The command stops if the development work repo is currently on that branch.

```bash
git-ssh-sync branch delete myproject feature/foo --dry-run
git-ssh-sync branch delete myproject feature/foo
git-ssh-sync branch delete myproject feature/foo --yes
```

To remove cache, work repo, and gateway tracking refs for branches that no longer
exist on origin, use `branch prune`.

```bash
git-ssh-sync branch prune myproject --dry-run
git-ssh-sync branch prune myproject
```

Branch rename is intentionally not automated yet. Rename a branch with normal Git
operations, then use `checkout`, `push`, `branch delete`, or `branch prune` to
bring each repository back into the intended state.

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

When diverged, automatic resolution is not performed. Follow "Workflow When Push Stops", merge or rebase in the development environment, then `push` again.

## Common Commands

| Goal | Command |
|---|---|
| Display help | `git-ssh-sync --help` |
| Register a project | `git-ssh-sync init myproject --origin git@github.com:example/myproject.git --dev-host devserver --dev-user user --dev-path /home/user/work/myproject` |
| List registered project settings | `git-ssh-sync config list` |
| Show registered project settings | `git-ssh-sync config show myproject` |
| Initial clone | `git-ssh-sync clone myproject` |
| Check synchronization status | `git-ssh-sync status myproject` |
| Check branch status | `git-ssh-sync branch myproject` |
| Delete a branch after reviewing affected refs | `git-ssh-sync branch delete myproject feature/foo` |
| Prune refs for branches missing on origin | `git-ssh-sync branch prune myproject` |
| Inspect development work repo status | `git-ssh-sync dev status myproject` |
| Inspect development work repo diff | `git-ssh-sync dev diff myproject --stat` |
| Reflect changes from origin to development environment | `git-ssh-sync pull myproject` |
| Reflect commits from development environment to origin | `git-ssh-sync push myproject` |
| Switch development environment branch | `git-ssh-sync checkout myproject feature/foo` |
| Create and switch to a new branch from a base branch | `git-ssh-sync checkout myproject -b feature/foo --base develop` |
| Diagnostics | `git-ssh-sync doctor myproject` |
| Diagnose after an interrupted sync | `git-ssh-sync recover myproject` |
| Apply safe recovery repairs | `git-ssh-sync recover myproject --yes` |

For commands with many options, prefer the full examples in the workflow
sections above. They are easier to copy safely because each option is shown on
its own line.

## Troubleshooting

Use `status` first when synchronization stops or the current state is unclear.
Use `doctor` for setup, connectivity, and repository wiring problems. Use
`recover` after an interrupted `pull` or `push`.
For a fuller operational guide, see [Troubleshooting](docs/troubleshooting.md).

### push stops because origin has new commits

Cause:
origin has commits that are not included in the development environment branch,
or origin and the development environment branch have diverged.

Check:

```bash
git-ssh-sync status myproject
```

Fix:

```bash
git-ssh-sync pull myproject
# If pull cannot fast-forward, merge or rebase in the development environment.
# See "Workflow When Push Stops" for the detailed recovery flow.
```

### pull cannot fast-forward

Cause:
origin and the development environment branch have diverged. `git-ssh-sync`
does not perform automatic merge or automatic rebase.

Check:

```bash
git-ssh-sync status myproject
git-ssh-sync dev status myproject
```

Fix:

```bash
# On the development environment
cd ~/work/myproject
git fetch gitsync
git merge gitsync/main
# or: git rebase gitsync/main
```

After resolving conflicts and committing or continuing the rebase, run:

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

### Development work repo is dirty

Cause:
the development environment work repo has uncommitted changes. Uncommitted
changes are not synchronized, and repair commands do not commit, stash, merge,
or rebase them automatically.

Check:

```bash
git-ssh-sync dev status myproject
git-ssh-sync dev diff myproject --stat
```

Fix:

```bash
# On the development environment
cd ~/work/myproject
git status
git add <files-to-sync>
git commit
```

Commit changes that should be synchronized, or stash/remove local-only changes
before running `pull`, `push`, `attach`, or `doctor --repair` again.

### gitsync remote is missing or mismatched

Cause:
the `gitsync` remote in the development work repo does not point to the expected
bare cache repo, or the wiring is missing.

Check:

```bash
git-ssh-sync doctor myproject
```

Fix:

```bash
git-ssh-sync doctor myproject --repair
git-ssh-sync doctor myproject --repair --yes
```

### Cache repo or work repo already exists

Cause:
`clone` was asked to create a development work repo or bare cache repo at a path
that already exists.

Check:

```bash
git-ssh-sync doctor myproject
```

Fix:

```bash
git-ssh-sync attach myproject --dev-path /home/user/work/myproject
git-ssh-sync doctor myproject --repair
```

Use `attach` when the existing repositories are intentional. Otherwise choose an
empty path or move the existing directory before running `clone` again.

### Windows path is broken

Cause:
the local shell may consume backslashes in Windows paths before
`git-ssh-sync` receives them, or the project may be configured with the wrong
development OS.

Check:

```bash
git-ssh-sync config show myproject
git-ssh-sync doctor myproject
```

Fix:

```bash
git-ssh-sync init myproject \
  --origin git@github.com:example/myproject.git \
  --dev-host devserver \
  --dev-user user \
  --dev-os windows \
  --dev-path 'C:\Users\user\work\myproject'
```

Quote Windows paths that contain backslashes when running commands from macOS or
Linux shells.

### SSH connection fails

Cause:
the local machine cannot connect to the development environment over SSH, or the
configured host, user, port, or authentication settings are incorrect.

Check:

```bash
git-ssh-sync doctor myproject
ssh user@devserver
```

Fix:

```bash
git-ssh-sync config show myproject
# Update the project config or recreate it with the correct --dev-host,
# --dev-user, --dev-port, and SSH authentication settings.
```

Run `doctor --debug` or use `--log-file` when you need the exact SSH and Git
commands used during diagnosis.

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

Run the same checks enforced by CI with the following commands:

```bash
uv run ruff check src tests manual_tests
uv run ruff format --check src tests manual_tests
uv run pytest
```

Ruff currently checks Python source and tests. If future tooling adds support for documentation formats, include docs in the local and CI checks together.

## Related Documentation

- [Troubleshooting](docs/troubleshooting.md)
- [Specification](docs/spec.md)
