# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.12 CLI project packaged with `uv`. Runtime code lives in `src/git_ssh_sync/`, with one module per command or domain concern: `cli.py` defines the Typer command surface, while modules such as `sync.py`, `clone.py`, `status.py`, `branch.py`, `doctor.py`, `git.py`, and `ssh.py` contain implementation logic. Tests are in `tests/` and mirror the source modules with names like `test_cli.py` and `test_sync.py`. User documentation is in `README.md`, `README.ja.md`, and `docs/spec.md`.

## Build, Test, and Development Commands

- `uv sync --dev`: install runtime and development dependencies from `pyproject.toml` and `uv.lock`.
- `uv run pytest`: run the full test suite under `tests/`.
- `uv run ruff check src tests`: lint source and tests with the configured Python 3.12 target.
- `uv run ruff format src tests`: format Python files.
- `uv run git-ssh-sync --help`: run the CLI entry point locally.
- `uv build`: build the package using `uv_build`.

## Coding Style & Naming Conventions

Use Ruff defaults for formatting and linting. Keep code typed where practical and follow existing patterns: small functions, explicit domain errors such as `SyncError`, and Typer commands named `*_command`. Python modules and functions use `snake_case`; test functions use `test_<behavior>`. Keep command output routed through `git_ssh_sync.console.console` and escape user-facing error text when rendering Rich markup.

## Testing Guidelines

The project uses `pytest`, configured with `testpaths = ["tests"]` and `pythonpath = ["src"]`. Add or update tests in the matching `tests/test_*.py` file whenever behavior changes. Prefer focused tests around command behavior, git/SSH command construction, and error handling. Use `monkeypatch`, `tmp_path`, and Typer's `CliRunner` as shown in existing tests to avoid real network, SSH, or GitHub dependencies.

## Commit & Pull Request Guidelines

Recent commits use short, imperative subject lines such as `Clarify README operational details` and `Implement current-branch sync flow`. Follow that style: capitalize the subject, omit a trailing period, and keep the first line concise. Pull requests should describe the user-visible change, list tests run, link related issues, and update README or inline documentation when commands, configuration, or workflows change. Screenshots are usually unnecessary unless terminal output formatting changes.

## Security & Configuration Tips

Do not commit real SSH hosts, usernames, private repository URLs, tokens, or generated local configuration. Tests should simulate SSH and Git interactions instead of using live services. Be careful when changing sync logic: `pull` and `push` intentionally avoid unsafe merges and non-fast-forward updates.
