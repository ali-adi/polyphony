"""Jobs: create, run, snapshot, detect a dead worker, cancel."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from polyphony.config import ProjectConfig
from polyphony.executors import BaseExecutor
from polyphony.jobs import JobNotFound, cancel, create_job, diff, discard, launch
from polyphony.worker import run
from polyphony.workspace import ProvisionError


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class ShellExecutor(BaseExecutor):
    """Runs the instruction as a shell script, so a test decides what 'the agent' does."""

    name = "shell"

    def find_binary(self):
        return "/bin/sh"

    def build_argv(self, instruction, mode, cwd, model=None):
        return ["/bin/sh", "-c", instruction]


FAKE = {"shell": ShellExecutor}


def _project(repo, provision=()):
    return ProjectConfig(name="demo", path=repo, provision=list(provision))


def _job(store, repo, instruction, mode="code", provision=(), executor="shell"):
    return create_job(
        store,
        project=_project(repo, provision),
        instruction=instruction,
        executor=executor,
        mode=mode,
    )


def test_create_job_records_a_queued_job_outside_the_repo(store, repo):
    job = _job(store, repo, "true")
    wt = Path(job.workdir)
    assert job.state == "queued"
    assert wt.is_dir()
    assert repo not in wt.parents
    assert wt == store.path(job.id) / "repo"
    assert _git("remote", cwd=wt) == ""
    assert job.base_commit == _git("rev-parse", "HEAD", cwd=repo)
    assert store.load(job.id) == job


def test_failed_provisioning_leaves_no_trace(store, repo):
    with pytest.raises(ProvisionError):
        _job(store, repo, "true", provision=[{"path": "missing/", "mode": "clone"}])
    assert store.all() == []
    assert not store.dir.exists() or not any(store.dir.iterdir())
    assert _git("branch", "--list", "polyphony/*", cwd=repo) == ""


def test_successful_run_commits_in_the_copy_only(store, repo):
    base = _git("rev-parse", "HEAD", cwd=repo)
    job = _job(store, repo, "echo hi > new.txt && echo 'did it'")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.exit_code == 0
    assert job.files_changed == ["new.txt"]
    assert "new.txt" in job.diff_stat
    assert "did it" in store.output_path(job.id).read_text()
    assert _git("log", "-1", "--format=%s", cwd=job.workdir) == f"polyphony job {job.id}"
    assert not (repo / "new.txt").exists()
    assert _git("status", "--porcelain", cwd=repo) == ""
    assert _git("rev-parse", "HEAD", cwd=repo) == base


def test_provisioned_paths_never_enter_the_snapshot(store, repo):
    job = _job(
        store, repo, "echo hi > new.txt",
        provision=[{"path": "env/", "mode": "link"}, {"path": "data/", "mode": "clone"}],
    )
    assert (Path(job.workdir) / "env").is_symlink()
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded", job.error
    assert job.files_changed == ["new.txt"]


def test_nonzero_exit_is_a_failed_job_with_partial_work_kept(store, repo):
    job = _job(store, repo, "echo partial > p.txt; exit 3")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "failed"
    assert job.exit_code == 3
    assert job.files_changed == ["p.txt"]


def test_review_with_no_changes_makes_no_commit(store, repo):
    job = _job(store, repo, "echo looks fine", mode="review")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.files_changed == []
    assert _git("rev-parse", "HEAD", cwd=job.workdir) == job.base_commit


def test_worker_bug_is_recorded_and_reraised(store, repo):
    class Broken(ShellExecutor):
        def build_argv(self, *a, **k):
            raise NameError("oops")

    job = _job(store, repo, "true", executor="broken")
    with pytest.raises(NameError):
        run(store.path(job.id), executors={"broken": Broken})
    job = store.load(job.id)
    assert job.state == "failed"
    assert "NameError" in job.error


def test_worker_skips_a_job_cancelled_before_it_started(store, repo):
    job = _job(store, repo, "echo hi > new.txt")
    cancel(store, job.id)
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "cancelled"
    assert job.files_changed == []


def test_refresh_marks_a_vanished_worker_died(store, repo):
    job = _job(store, repo, "true")
    p = subprocess.Popen(["true"])
    p.wait()
    job.state, job.pid = "running", p.pid
    store.save(job)
    assert store.refresh(store.load(job.id)).state == "died"
    assert store.load(job.id).state == "died"


def test_refresh_leaves_a_live_worker_alone(store, repo):
    job = _job(store, repo, "true")
    job.state, job.pid = "running", os.getpid()
    store.save(job)
    assert store.refresh(store.load(job.id)).state == "running"


def test_save_leaves_no_temp_file(store, repo):
    job = _job(store, repo, "true")
    assert not list(store.path(job.id).glob("*.tmp"))


def test_load_unknown_job_raises(store):
    with pytest.raises(JobNotFound):
        store.load("nope")


def test_all_lists_newest_first(store, repo):
    first = _job(store, repo, "true")
    second = _job(store, repo, "true")
    first.created_at, second.created_at = 1.0, 2.0
    store.save(first)
    store.save(second)
    assert [j.id for j in store.all()] == [second.id, first.id]


# --- Real detached launches. A fake `agy` on PATH stands in for the CLI. ---


def test_launch_runs_detached_and_leaves_no_zombie(store, repo, fake_agy, wait_for):
    fake_agy("echo from agy > from_agy.txt; echo done")
    job = _job(store, repo, "x", executor="agy")
    launch(store, job)
    job = wait_for(store, job.id, {"succeeded", "failed", "died"})
    assert job.state == "succeeded", store.output_path(job.id).read_text()
    assert job.files_changed == ["from_agy.txt"]
    # The worker was reparented away from us, so it is not our child to reap.
    with pytest.raises(ChildProcessError):
        os.waitpid(job.pid, os.WNOHANG)


def test_cancel_kills_the_worker_and_its_executor(store, repo, fake_agy, wait_for):
    fake_agy("sleep 30")
    job = _job(store, repo, "x", executor="agy")
    launch(store, job)
    wait_for(store, job.id, {"running"})
    time.sleep(0.5)  # let the executor subprocess start
    job = cancel(store, job.id)
    assert job.state == "cancelled"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(job.pgid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            # macOS answers EPERM for ~0.1s while a killed group is still
            # being reaped, then ESRCH. Keep polling.
            pass
        time.sleep(0.1)
    pytest.fail("worker process group still alive after cancel")


def test_the_repo_is_untouched_until_apply(store, repo):
    def state():
        return {
            str(p.relative_to(repo)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in repo.rglob("*")
            if p.is_file()
        }

    before = state()
    job = _job(store, repo, "echo hi > new.txt && echo 'x = 5' > app.py")
    run(store.path(job.id), executors=FAKE)
    assert "new.txt" in diff(store, job.id)
    discard(store, job.id)
    assert state() == before


def test_job_diff_holds_only_the_agents_work_not_uncommitted_edits(store, repo):
    (repo / "app.py").write_text("x = 2\n")
    (repo / "wip.txt").write_text("mine\n")
    job = _job(store, repo, "echo hi > new.txt")
    assert (Path(job.workdir) / "app.py").read_text() == "x = 2\n"
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.files_changed == ["new.txt"]
    assert "app.py" not in diff(store, job.id)


def test_apply_over_unstaged_edits_leaves_the_change_unstaged(store, repo):
    from polyphony.jobs import apply
    (repo / "app.py").write_text("x = 2\n")
    job = _job(store, repo, "echo 'y = 3' >> app.py")
    run(store.path(job.id), executors=FAKE)
    assert apply(store, job.id) == ["app.py"]
    assert (repo / "app.py").read_text() == "x = 2\ny = 3\n"
    assert store.load(job.id).applied_unstaged
    assert _git("diff", "--cached", "--name-only", cwd=repo) == ""


def test_apply_on_a_clean_file_stages_it(store, repo):
    from polyphony.jobs import apply
    job = _job(store, repo, "echo hi > new.txt")
    run(store.path(job.id), executors=FAKE)
    assert apply(store, job.id) == ["new.txt"]
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "new.txt"
    assert not store.load(job.id).applied_unstaged
