"""SSH command wrapper for Git protocol commands targeting Windows hosts."""

from __future__ import annotations

import os
import shlex
import sys
from base64 import b64encode

GIT_PROTOCOL_COMMANDS = {"git-receive-pack", "git-upload-pack", "git-upload-archive"}


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _base_ssh_command() -> list[str]:
    command = os.environ.get("GIT_SSH_SYNC_BASE_SSH_COMMAND", "ssh")
    return shlex.split(command)


def _powershell_command(remote_command: str) -> str | None:
    try:
        parts = shlex.split(remote_command, posix=True)
    except ValueError:
        return None
    if len(parts) < 2 or parts[0] not in GIT_PROTOCOL_COMMANDS:
        return None

    script = "& " + " ".join(_powershell_quote(part) for part in parts)
    encoded_script = b64encode(script.encode("utf-16le")).decode("ascii")
    return (
        "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f"-EncodedCommand {encoded_script}"
    )


def main() -> None:
    args = sys.argv[1:]
    base_command = _base_ssh_command()
    if len(args) < 2:
        os.execvp(base_command[0], [*base_command, *args])

    remote_command = _powershell_command(args[-1])
    if remote_command is None:
        os.execvp(base_command[0], [*base_command, *args])

    os.execvp(base_command[0], [*base_command, *args[:-1], remote_command])


if __name__ == "__main__":
    main()
