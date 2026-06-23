from base64 import b64decode

from git_ssh_sync import windows_git_ssh


def _decode_powershell_command(command: str) -> str:
    encoded_script = command.rsplit(" ", 1)[1]
    return b64decode(encoded_script).decode("utf-16le")


def test_powershell_command_strips_git_shell_quotes_from_path() -> None:
    command = windows_git_ssh._powershell_command(
        "git-receive-pack 'C:/Users/alice/cache repo/project.git'"
    )

    assert command is not None
    assert _decode_powershell_command(command) == (
        "& 'git-receive-pack' 'C:/Users/alice/cache repo/project.git'"
    )


def test_powershell_command_ignores_non_git_protocol_command() -> None:
    assert windows_git_ssh._powershell_command("git --version") is None
