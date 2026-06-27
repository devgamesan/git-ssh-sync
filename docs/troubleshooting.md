# Troubleshooting

This guide explains how to inspect and recover common operational problems with
`git-ssh-sync`.

The examples assume a Linux/macOS shell. Run `git-ssh-sync` commands on the
local machine. Run plain `git` commands in the development environment or local
gateway repo only when the step explicitly says so.

## First checks

Use these commands before changing repository state:

```bash
git-ssh-sync status myproject
git-ssh-sync dev status myproject
git-ssh-sync branch myproject
git-ssh-sync doctor myproject
```

Command selection:

| Situation | Command |
|---|---|
| You need the current branch sync state | `git-ssh-sync status myproject` |
| You need uncommitted file status in the development work repo | `git-ssh-sync dev status myproject` |
| You need branch existence and ahead/behind state across origin, cache, and work repo | `git-ssh-sync branch myproject` |
| You suspect setup, SSH, origin permissions, or repository wiring problems | `git-ssh-sync doctor myproject` |
| A previous `pull` or `push` was interrupted | `git-ssh-sync recover myproject` |

`git-ssh-sync` does not automatically commit, stash, merge, rebase, resolve
conflicts, force-push, or synchronize uncommitted file changes. Do those actions
manually in the development environment after inspecting the state.

Some command failures include a `Recovery:` block. Follow those numbered steps
from the local machine unless the message explicitly says to run a plain `git`
command in the development environment or local gateway repo.

## Clone stops because a path already exists

Cause:
`git-ssh-sync clone` found an existing local gateway path, development cache
path, or development work path. It stops before overwriting existing data.

If the existing repositories should be reused, preview attach wiring:

```bash
git-ssh-sync attach myproject --dry-run
```

If the configured path is wrong, update the project configuration instead of
deleting data:

```bash
git-ssh-sync config set myproject ...
```

Only move or delete the existing path when you intentionally want to recreate
the repositories from scratch.

## Development work repo is dirty

Cause:
the development work repo has uncommitted changes. `git-ssh-sync` synchronizes
commits and branches, not uncommitted file changes.

Check from the local machine:

```bash
git-ssh-sync dev status myproject
git-ssh-sync dev diff myproject --stat
```

Inspect and resolve in the development environment:

```bash
cd ~/work/myproject
git status
git diff
git add <files-to-sync>
git commit
```

If the changes are local-only, stash or remove them instead:

```bash
cd ~/work/myproject
git stash push -m "local work before git-ssh-sync recovery"
# or remove only files you intentionally want to discard
git restore <path>
```

After the work tree is clean, retry from the local machine:

```bash
git-ssh-sync status myproject
git-ssh-sync pull myproject
# or
git-ssh-sync push myproject
```

## Branch has diverged or cannot fast-forward

Cause:
origin and the development work repo both have commits that the other side does
not have, or `pull` cannot update the development branch by fast-forward.

Check from the local machine:

```bash
git-ssh-sync status myproject
git-ssh-sync dev status myproject
```

Resolve in the development environment. Replace `main` with the branch reported
by `git-ssh-sync status`:

```bash
cd ~/work/myproject
git fetch gitsync
git status
git merge gitsync/main
# or, if rewriting unpublished development-only commits is acceptable:
git rebase gitsync/main
```

If conflicts occur, resolve them with normal Git commands, then finish the merge
or rebase:

```bash
git status
git add <resolved-files>
git commit
# or, during rebase:
git rebase --continue
```

Then push the resolved branch from the local machine:

```bash
git-ssh-sync status myproject
git-ssh-sync push myproject
```

## Development work repo is detached HEAD

Cause:
the development work repo is not currently on a branch. `git-ssh-sync pull` and
`push` operate on the current development branch, so a detached HEAD must be
attached to a branch before synchronization.

Check from the local machine:

```bash
git-ssh-sync dev status myproject
git-ssh-sync branch myproject
```

Inspect in the development environment:

```bash
cd ~/work/myproject
git status
git branch --show-current
git log --oneline --decorate -5
```

If the detached commit should become work on a new branch:

```bash
cd ~/work/myproject
git switch -c recover/detached-work
git status
```

If you only need to return to an existing branch:

```bash
cd ~/work/myproject
git switch main
```

Then inspect from the local machine:

```bash
git-ssh-sync status myproject
git-ssh-sync branch myproject
```

## SSH connection fails

Cause:
the local machine cannot connect to the development environment, or the project
configuration contains the wrong host, user, port, path, or authentication
settings.

Check from the local machine:

```bash
git-ssh-sync config show myproject
git-ssh-sync doctor myproject
ssh user@devserver
```

If a custom port is configured:

```bash
ssh -p 2222 user@devserver
```

Use debug output to see the exact SSH and Git commands:

```bash
git-ssh-sync doctor myproject --debug
git-ssh-sync doctor myproject --log-file git-ssh-sync-doctor.log
```

Fix the SSH configuration or recreate/update the project configuration with the
correct `--dev-host`, `--dev-user`, `--dev-port`, `--dev-os`, and `--dev-path`
values. After connectivity works, run:

```bash
git-ssh-sync doctor myproject
```

## Origin fetch fails

Cause:
the local machine cannot fetch from origin, origin is unavailable, the URL is
wrong, or credentials do not allow read access.

Check from the local machine:

```bash
git-ssh-sync config show myproject
git-ssh-sync doctor myproject
```

If `doctor` reports an origin fetch failure, inspect the configured local
gateway repo:

```bash
cd /path/to/local/gateway/repo
git remote -v
git fetch origin
```

Fix the origin URL or local credentials using normal Git configuration. For
example:

```bash
git remote set-url origin git@github.com:example/myproject.git
git fetch origin
git-ssh-sync doctor myproject
```

Do not add GitHub or GitLab credentials to the development environment for this
tool. Origin access is intentionally handled by the local machine.

## Origin push fails

Cause:
origin has commits that have not been pulled, the branch has diverged, the local
machine does not have write permission, or branch protection rejects the push.

Check from the local machine:

```bash
git-ssh-sync status myproject
git-ssh-sync doctor myproject
```

If `doctor` reports an origin push failure, inspect the configured local gateway
repo. Replace `main` with the branch reported by `git-ssh-sync status`:

```bash
cd /path/to/local/gateway/repo
git push --dry-run origin HEAD:main
```

If origin has new commits, update and resolve through the development
environment:

```bash
git-ssh-sync pull myproject
```

If the branch diverged, follow the diverged branch section above. If permissions
or branch protection block the push, fix repository access or push to an allowed
branch and open a pull request.

`git-ssh-sync` does not force-push to origin. Resolve non-fast-forward and
protected-branch failures explicitly.

## gitsync remote or cache wiring is wrong

Cause:
the development work repo `gitsync` remote is missing, points to the wrong bare
cache repo, or local gateway refs no longer match the configured repositories.

Check from the local machine:

```bash
git-ssh-sync doctor myproject
```

Preview and apply safe repairs:

```bash
git-ssh-sync doctor myproject --repair
git-ssh-sync doctor myproject --repair --yes
```

Repair does not commit, stash, merge, rebase, or discard existing development
work. Clean or save the development work tree first if `doctor` reports it as
dirty.

## Git LFS and submodules are not supported

`git-ssh-sync` currently transfers Git commits, branches, and tags through the
gateway/cache workflow. It does not provide dedicated Git LFS or submodule
support.

If a repository uses Git LFS, verify that required LFS objects are available in
the environment where you build or test:

```bash
git lfs status
git lfs pull
```

If a repository uses submodules, update them with normal Git commands in an
environment that has access to the submodule remotes:

```bash
git submodule status
git submodule update --init --recursive
```

For restricted development environments, prefer avoiding LFS/submodule-dependent
workflows until explicit support exists, or mirror the required objects and
submodule repositories through an approved internal path.

## What must be done manually

Run these operations yourself after inspecting the repository state:

- Commit or stash dirty development work tree changes
- Resolve merge or rebase conflicts
- Choose whether a diverged branch should be merged or rebased
- Reattach detached HEAD work to a branch
- Fix SSH host/user/port/authentication settings
- Fix origin credentials, branch protection, or repository permissions
- Fetch Git LFS objects or initialize submodules when the project requires them

After manual recovery, run:

```bash
git-ssh-sync doctor myproject
git-ssh-sync status myproject
```
