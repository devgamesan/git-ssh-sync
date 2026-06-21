from pathlib import Path

import pytest

from git_ssh_sync import status
from git_ssh_sync.config import DevConfig, LocalConfig, OptionsConfig, ProjectConfig
from git_ssh_sync.git import CommandResult
from git_ssh_sync.status import StatusError, StatusReport


def _project_config(local_path: Path) -> ProjectConfig:
    return ProjectConfig(
        origin="git@github.com:example/myproject.git",
        local=LocalConfig(repo_path=str(local_path)),
        dev=DevConfig(
            host="devserver",
            user="user",
            work_path="/home/user/work/myproject",
            cache_path="/home/user/cache repo/myproject.git",
        ),
        options=OptionsConfig(),
    )


def _result(
    command: tuple[str, ...], stdout: str = "", returncode: int = 0
) -> CommandResult:
    return CommandResult(
        environment="test",
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_inspect_project_status_collects_origin_and_development_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, object]] = []

    def fake_fetch(remote: str = "origin", refspecs=(), *, cwd=None, **kwargs):
        calls.append(("fetch", remote, tuple(refspecs), cwd))
        return _result(("git", "fetch"))

    def fake_log_oneline(revision: str = "HEAD", *, cwd=None, **kwargs):
        calls.append(("log", revision, cwd))
        output = {
            "origin/main": "a1b2c3d Update README\n",
            "dev/main": "d4e5f6a Add feature\n",
        }[revision]
        return _result(("git", "log"), output)

    def fake_rev_list(revisions, *, cwd=None, **kwargs):
        calls.append(("rev-list", tuple(revisions), cwd))
        return _result(("git", "rev-list"), "0 2\n")

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        calls.append(("run-git", tuple(args), cwd, check))
        return _result(("git", *args), "")

    def fake_run_ssh(host: str, command, *, user=None, check=True, **kwargs):
        calls.append(("ssh", host, tuple(command), user, check))
        return _result(("ssh", host), returncode=0)

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, **kwargs):
        calls.append(("remote-git", host, repo_path, tuple(args), user))
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("log", "-1", "--format=%h %s"): "d4e5f6a Add feature\n",
            ("status", "--porcelain"): "",
        }
        return _result(("ssh", host), outputs[tuple(args)])

    monkeypatch.setattr(status.git, "fetch", fake_fetch)
    monkeypatch.setattr(status.git, "log_oneline", fake_log_oneline)
    monkeypatch.setattr(status.git, "rev_list", fake_rev_list)
    monkeypatch.setattr(status.git, "run_git", fake_run_git)
    monkeypatch.setattr(status.ssh, "run_ssh", fake_run_ssh)
    monkeypatch.setattr(status.ssh, "run_remote_git", fake_run_remote_git)

    report = status.inspect_project_status("myproject", _project_config(tmp_path))

    assert report.origin_head == "a1b2c3d Update README"
    assert report.dev_head == "d4e5f6a Add feature"
    assert report.dev_working_tree_clean is True
    assert report.origin_ahead == 0
    assert report.dev_ahead == 2
    assert report.uses_lfs is False
    assert report.uses_submodules is False
    assert (
        "fetch",
        "ssh://user@devserver/home/user/work/myproject",
        ("refs/heads/main:refs/remotes/dev/main",),
        tmp_path,
    ) in calls
    assert (
        "rev-list",
        ("--left-right", "--count", "origin/main...dev/main"),
        tmp_path,
    ) in calls


def test_inspect_project_status_detects_dirty_lfs_and_submodules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".gitattributes").write_text(
        "*.bin filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8"
    )
    (tmp_path / ".gitmodules").write_text("[submodule]\n", encoding="utf-8")

    monkeypatch.setattr(
        status.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch"))
    )
    monkeypatch.setattr(
        status.git,
        "log_oneline",
        lambda *args, **kwargs: _result(("git", "log"), "a1 Done\n"),
    )
    monkeypatch.setattr(
        status.git,
        "rev_list",
        lambda *args, **kwargs: _result(("git", "rev-list"), "1 0\n"),
    )
    monkeypatch.setattr(
        status.git,
        "run_git",
        lambda *args, **kwargs: _result(("git", "lfs"), returncode=1),
    )
    monkeypatch.setattr(
        status.ssh, "run_ssh", lambda *args, **kwargs: _result(("ssh", "devserver"))
    )

    def fake_run_remote_git(host: str, repo_path: str, args, *, user=None, **kwargs):
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("log", "-1", "--format=%h %s"): "a1 Done\n",
            ("status", "--porcelain"): " M app.py\n",
        }
        return _result(("ssh", host), outputs[tuple(args)])

    monkeypatch.setattr(status.ssh, "run_remote_git", fake_run_remote_git)

    report = status.inspect_project_status("myproject", _project_config(tmp_path))

    assert report.dev_working_tree_clean is False
    assert report.uses_lfs is True
    assert report.uses_submodules is True


def test_inspect_project_status_reports_missing_gateway_repo(tmp_path: Path) -> None:
    with pytest.raises(StatusError, match="gateway repository does not exist"):
        status.inspect_project_status(
            "myproject", _project_config(tmp_path / "missing")
        )


def test_print_status_outputs_required_sections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = StatusReport(
        project="myproject",
        origin_url="git@github.com:example/myproject.git",
        branch="main",
        origin_head="a1b2c3d Update README",
        dev_host="devserver",
        dev_work_path="/home/user/work/myproject",
        dev_branch="main",
        dev_head="d4e5f6a Add feature",
        dev_working_tree_clean=False,
        origin_ahead=0,
        dev_ahead=2,
        uses_lfs=True,
        uses_submodules=True,
    )

    status.print_status(report)

    output = capsys.readouterr().out
    assert "Project" in output
    assert "Origin" in output
    assert "Development" in output
    assert "State" in output
    assert "Recommendation" in output
    assert "working tree" in output
    assert "dirty" in output
    assert "git-ssh-sync push myproject" not in output
    assert "Commit or stash changes" in output
    assert "Git LFS" in output
    assert "Git submodules" in output


def test_recommendation_includes_required_branch_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = StatusReport(
        project="myproject",
        origin_url="git@github.com:example/myproject.git",
        branch="main",
        origin_head="a1b2c3d Update README",
        dev_host="devserver",
        dev_work_path="/home/user/work/myproject",
        dev_branch="main",
        dev_head="d4e5f6a Add feature",
        dev_working_tree_clean=True,
        origin_ahead=0,
        dev_ahead=2,
        uses_lfs=False,
        uses_submodules=False,
    )

    status.print_status(report)

    output = capsys.readouterr().out
    assert "git-ssh-sync push myproject" in output
