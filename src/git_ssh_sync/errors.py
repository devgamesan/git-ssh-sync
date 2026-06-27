"""Shared error types for command execution."""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


def format_command(command: Sequence[str]) -> str:
    """Return a shell-readable command string for logs and errors."""
    return shlex.join(str(part) for part in command)


def format_recovery(*steps: str) -> str:
    """Return a terminal-friendly recovery block."""
    lines = ["Recovery:"]
    lines.extend(f"  {index}. {step}" for index, step in enumerate(steps, start=1))
    return "\n".join(lines)


@dataclass(frozen=True)
class CommandExecutionError(RuntimeError):
    """Raised when a local or remote command exits with a non-zero status."""

    environment: str
    command: tuple[str, ...]
    returncode: int
    cwd: Path | None = None
    stdout: str = ""
    stderr: str = ""

    def __str__(self) -> str:
        location = f" in {self.cwd}" if self.cwd is not None else ""
        message = (
            f"[{self.environment}] command failed with exit code {self.returncode}"
            f"{location}: {format_command(self.command)}"
        )
        if self.stderr:
            return f"{message}\nstderr: {self.stderr.rstrip()}"
        if self.stdout:
            return f"{message}\nstdout: {self.stdout.rstrip()}"
        return message
