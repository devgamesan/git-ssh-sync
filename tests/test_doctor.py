from pathlib import Path

import pytest

from git_ssh_sync import doctor
from git_ssh_sync.config import DevConfig, LocalConfig, OptionsConfig, ProjectConfig
from git_ssh_sync.git import CommandResult
from git_ssh_sync.doctor import DoctorError, DoctorReport


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
    command: tuple[str, ...], stdout: str = "", returncode: int = 0, stderr: str = ""
) -> CommandResult:
    return CommandResult(
        environment="test",
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _install_successful_command_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(
        doctor.git, "fetch", lambda *args, **kwargs: _result(("git", "fetch"))
    )

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        command = tuple(args)
        if command == ("lfs", "ls-files"):
            return _result(("git", *args), "")
        if command == ("branch", "--show-current"):
            return _result(("git", *args), "main\n")
        return _result(("git", *args))

    def fake_run_ssh(host: str, command, *, user=None, check=True, **kwargs):
        if tuple(command) == ("sh", "-lc", "command -v git"):
            return _result(("ssh", host), "/usr/bin/git\n")
        return _result(("ssh", host))

    def fake_run_remote_git(
        host: str, repo_path: str, args, *, user=None, check=True, **kwargs
    ):
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
            ("rev-parse", "--is-bare-repository"): "true\n",
            ("status", "--porcelain"): "",
            ("remote", "get-url", "gitsync"): "/home/user/cache repo/myproject.git\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(doctor.git, "run_git", fake_run_git)
    monkeypatch.setattr(doctor.ssh, "run_ssh", fake_run_ssh)
    monkeypatch.setattr(doctor.ssh, "run_remote_git", fake_run_remote_git)


def _by_name(report: DoctorReport, name: str):
    return [check for check in report.checks if check.name == name]


def test_inspect_project_doctor_collects_successful_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_successful_command_fakes(monkeypatch)

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    assert report.has_errors is False
    assert _by_name(report, "git command")[0].status == "ok"
    assert _by_name(report, "ssh command")[0].status == "ok"
    assert _by_name(report, "origin fetch")[0].status == "ok"
    assert _by_name(report, "origin push dry-run")[0].status == "ok"
    assert (
        _by_name(report, "working tree")[0].message
        == "Working tree is clean at abc1234."
    )
    assert _by_name(report, "cache branch fetch")[0].status == "ok"
    assert _by_name(report, "dev branch fetch")[0].status == "ok"
    assert _by_name(report, "origin/cache history")[0].status == "ok"
    assert _by_name(report, "cache/work history")[0].status == "ok"
    assert _by_name(report, "origin/work history")[0].status == "ok"


def test_inspect_project_doctor_warns_for_lfs_and_submodules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".gitattributes").write_text(
        "*.bin filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8"
    )
    (tmp_path / ".gitmodules").write_text("[submodule]\n", encoding="utf-8")
    _install_successful_command_fakes(monkeypatch)

    def fake_run_git(args, *, cwd=None, check=True, **kwargs):
        if tuple(args) == ("lfs", "ls-files"):
            return _result(("git", *args), returncode=1)
        if tuple(args) == ("branch", "--show-current"):
            return _result(("git", *args), "main\n")
        return _result(("git", *args))

    monkeypatch.setattr(doctor.git, "run_git", fake_run_git)

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    lfs = _by_name(report, "Git LFS")[0]
    submodules = _by_name(report, "submodules")[0]
    assert report.has_errors is False
    assert lfs.status == "warning"
    assert "not supported by git-ssh-sync" in (lfs.next_action or "")
    assert submodules.status == "warning"
    assert "not supported by git-ssh-sync" in (submodules.next_action or "")
    assert "separate git-ssh-sync project" in (submodules.next_action or "")


def test_inspect_project_doctor_reports_dirty_worktree_next_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_successful_command_fakes(monkeypatch)

    def fake_run_remote_git(
        host: str, repo_path: str, args, *, user=None, check=True, **kwargs
    ):
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
            ("rev-parse", "--is-bare-repository"): "true\n",
            ("status", "--porcelain"): " M app.py\n",
            ("remote", "get-url", "gitsync"): "/home/user/cache repo/myproject.git\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(doctor.ssh, "run_remote_git", fake_run_remote_git)

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    dirty = _by_name(report, "working tree")[0]
    assert report.has_errors is True
    assert dirty.status == "error"
    assert "abc1234" in dirty.message
    assert "git -C /home/user/work/myproject status --short" in (
        dirty.next_action or ""
    )
    assert "stash push -u" in (dirty.next_action or "")


def test_inspect_project_doctor_reports_detached_worktree_next_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_successful_command_fakes(monkeypatch)

    def fake_run_remote_git(
        host: str, repo_path: str, args, *, user=None, check=True, **kwargs
    ):
        outputs = {
            ("branch", "--show-current"): "",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
            ("rev-parse", "--is-bare-repository"): "true\n",
            ("status", "--porcelain"): "",
            ("remote", "get-url", "gitsync"): "/home/user/cache repo/myproject.git\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(doctor.ssh, "run_remote_git", fake_run_remote_git)

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    branch = _by_name(report, "work repo branch")[0]
    assert report.has_errors is True
    assert branch.status == "error"
    assert "detached HEAD" in branch.message
    assert "git-ssh-sync checkout myproject <branch>" in (branch.next_action or "")


def test_inspect_project_doctor_reports_gitsync_mismatch_next_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_successful_command_fakes(monkeypatch)

    def fake_run_remote_git(
        host: str, repo_path: str, args, *, user=None, check=True, **kwargs
    ):
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
            ("rev-parse", "--is-bare-repository"): "true\n",
            ("status", "--porcelain"): "",
            ("remote", "get-url", "gitsync"): "/home/user/cache repo/other.git\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(doctor.ssh, "run_remote_git", fake_run_remote_git)

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    gitsync = _by_name(report, "gitsync remote")[0]
    assert report.has_errors is True
    assert gitsync.status == "error"
    assert "recover myproject --yes" in (gitsync.next_action or "")
    assert "remote set-url gitsync" in (gitsync.next_action or "")


def test_inspect_project_doctor_reports_missing_cache_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_successful_command_fakes(monkeypatch)

    def fake_run_remote_git(
        host: str, repo_path: str, args, *, user=None, check=True, **kwargs
    ):
        if tuple(args) == ("show-ref", "--verify", "--quiet", "refs/heads/main"):
            return _result(("ssh", host), returncode=1)
        outputs = {
            ("branch", "--show-current"): "main\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
            ("rev-parse", "--is-bare-repository"): "true\n",
            ("status", "--porcelain"): "",
            ("remote", "get-url", "gitsync"): "/home/user/cache repo/myproject.git\n",
        }
        return _result(("ssh", host), outputs.get(tuple(args), ""))

    monkeypatch.setattr(doctor.ssh, "run_remote_git", fake_run_remote_git)

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    cache_branch = _by_name(report, "cache branch")[0]
    assert report.has_errors is True
    assert cache_branch.status == "error"
    assert "recover myproject --yes" in (cache_branch.next_action or "")


def test_inspect_project_doctor_reports_missing_gateway_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/bin/{command}")

    report = doctor.inspect_project_doctor(
        "myproject", _project_config(tmp_path / "missing")
    )

    gateway = _by_name(report, "gateway repo")[0]
    assert report.has_errors is True
    assert gateway.status == "error"
    assert "does not exist" in gateway.message
    assert gateway.next_action == "Run git-ssh-sync clone for this project."


def test_inspect_project_doctor_stops_when_local_git_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_which(command: str) -> str | None:
        return None if command == "git" else f"/usr/bin/{command}"

    monkeypatch.setattr(doctor.shutil, "which", fake_which)
    monkeypatch.setattr(
        doctor.git,
        "run_git",
        lambda *args, **kwargs: pytest.fail(
            "git should not be executed when it is missing"
        ),
    )

    report = doctor.inspect_project_doctor("myproject", _project_config(tmp_path))

    git_check = _by_name(report, "git command")[0]
    assert report.has_errors is True
    assert git_check.status == "error"
    assert "not found" in git_check.message


def test_print_doctor_outputs_required_sections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = DoctorReport(
        project="myproject",
        branch="main",
        origin_url="git@github.com:example/myproject.git",
        dev_host="devserver",
        dev_work_path="/home/user/work/myproject",
        checks=(
            doctor.DoctorCheck(
                "Development",
                "working tree",
                "error",
                "Development working tree is dirty at abc1234.",
                "ssh:user@devserver",
                "Commit or stash changes on the development environment.",
            ),
        ),
    )

    doctor.print_doctor(report)

    output = capsys.readouterr().out
    assert "Doctor report for" in output
    assert "Development" in output
    assert "working tree" in output
    assert "Commit or stash changes" in output


def test_doctor_project_raises_when_report_has_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = DoctorReport(
        project="myproject",
        branch="main",
        origin_url="git@github.com:example/myproject.git",
        dev_host="devserver",
        dev_work_path="/home/user/work/myproject",
        checks=(
            doctor.DoctorCheck(
                "Local",
                "origin fetch",
                "error",
                "Could not fetch origin.",
                "local",
                "Check origin URL.",
            ),
        ),
    )

    monkeypatch.setattr(doctor, "inspect_doctor", lambda project: report)
    monkeypatch.setattr(doctor, "print_doctor", lambda report: None)

    with pytest.raises(DoctorError):
        doctor.doctor_project("myproject")


def test_doctor_project_runs_repair_before_final_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = [
        DoctorReport(
            project="myproject",
            branch="main",
            origin_url="git@github.com:example/myproject.git",
            dev_host="devserver",
            dev_work_path="/home/user/work/myproject",
            checks=(
                doctor.DoctorCheck(
                    "Development",
                    "gitsync remote",
                    "error",
                    "gitsync remote is missing.",
                    "ssh:user@devserver",
                    "Run git-ssh-sync doctor --repair.",
                ),
            ),
        ),
        DoctorReport(
            project="myproject",
            branch="main",
            origin_url="git@github.com:example/myproject.git",
            dev_host="devserver",
            dev_work_path="/home/user/work/myproject",
            checks=(),
        ),
    ]
    repairs = []
    monkeypatch.setattr(doctor, "inspect_doctor", lambda project: reports.pop(0))
    monkeypatch.setattr(doctor, "print_doctor", lambda report: None)
    monkeypatch.setattr(
        doctor,
        "repair_project",
        lambda project, *, yes=False, confirm=None: repairs.append(
            (project, yes, confirm)
        ),
    )

    doctor.doctor_project("myproject", repair=True, yes=True)

    assert repairs == [("myproject", True, None)]
