"""Jobs: create, run, snapshot, detect a dead worker, cancel."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from polyphony.config import ProjectConfig
from polyphony.executors import BaseExecutor
from polyphony.jobs import (
    QUEUE_GRACE_SECONDS, JobNotFound, active_counts, cancel, create_job, diff, discard,
    launch, revise,
)
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


def _job(store, repo, instruction, mode="code", provision=(), executor="shell", **kw):
    return create_job(
        store,
        project=_project(repo, provision),
        instruction=instruction,
        executor=executor,
        mode=mode,
        **kw,
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


def test_a_record_from_before_partial_apply_still_loads(store, repo):
    import json
    job = _job(store, repo, "true")
    f = store.path(job.id) / "job.json"
    record = json.loads(f.read_text())
    del record["applied_paths"]
    f.write_text(json.dumps(record))
    assert store.load(job.id).applied_paths == []


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


def _group_gone(pgid, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            # macOS answers EPERM for ~0.1s while a killed group is still
            # being reaped, then ESRCH. Keep polling.
            pass
        time.sleep(0.1)
    return False


def test_cancel_kills_the_worker_and_its_executor(store, repo, fake_agy, wait_for):
    fake_agy("sleep 30")
    job = _job(store, repo, "x", executor="agy")
    launch(store, job)
    wait_for(store, job.id, {"running"})
    deadline = time.monotonic() + 5
    while store.load(job.id).executor_pgid is None and time.monotonic() < deadline:
        time.sleep(0.05)
    job = cancel(store, job.id)
    assert job.state == "cancelled"
    assert job.executor_pgid and job.executor_pgid != job.pgid
    assert _group_gone(job.pgid), "worker process group still alive after cancel"
    assert _group_gone(job.executor_pgid), "executor process group still alive after cancel"


def test_output_streams_to_disk_while_the_job_runs(store, repo, fake_agy, wait_for):
    fake_agy("echo started; sleep 30")
    job = _job(store, repo, "x", executor="agy")
    launch(store, job)
    wait_for(store, job.id, {"running"})
    out = store.output_path(job.id)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not (out.exists() and "started" in out.read_text()):
        time.sleep(0.1)
    try:
        assert "started" in out.read_text()
        assert store.load(job.id).state == "running"
    finally:
        cancel(store, job.id)


def test_worker_appends_the_error_after_the_streamed_output(store, repo):
    job = _job(store, repo, "echo partial; echo broke >&2; exit 3")
    run(store.path(job.id), executors=FAKE)
    assert store.output_path(job.id).read_text() == "partial\n\n\n--- error ---\nbroke"
    assert store.load(job.id).error == "broke"


def test_a_job_json_from_before_executor_pgid_still_loads(store, repo):
    import json
    job = _job(store, repo, "true")
    f = store.path(job.id) / "job.json"
    data = json.loads(f.read_text())
    del data["executor_pgid"]
    f.write_text(json.dumps(data))
    assert store.load(job.id).executor_pgid is None


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


# --- The check command, run in the job's copy after the executor succeeds. ---


def _gone(pid, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass  # macOS: EPERM while a killed process is still being reaped
        time.sleep(0.1)
    return False


def test_a_passing_check_is_recorded(store, repo):
    job = _job(store, repo, "echo hi > new.txt", check="test -f new.txt && echo all good")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.check_command == "test -f new.txt && echo all good"
    assert job.check_passed is True
    assert job.check_exit_code == 0
    assert "all good" in store.check_path(job.id).read_text()


def test_a_failing_check_leaves_the_job_succeeded(store, repo):
    job = _job(store, repo, "echo hi > new.txt", check="echo broken >&2; exit 3")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.check_passed is False
    assert job.check_exit_code == 3
    assert "broken" in store.check_path(job.id).read_text()


def test_what_the_check_writes_stays_out_of_the_diff(store, repo):
    job = _job(store, repo, "echo hi > new.txt", check="echo junk > check_artifact.txt")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.check_passed is True
    assert job.files_changed == ["new.txt"]
    assert "check_artifact" not in diff(store, job.id)


def test_no_check_after_a_failed_executor(store, repo):
    job = _job(store, repo, "exit 1", check="echo ran")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "failed"
    assert job.check_passed is None and job.check_exit_code is None
    assert not store.check_path(job.id).exists()


def test_no_check_in_review_mode(store, repo):
    job = _job(store, repo, "echo fine", mode="review", check="echo ran")
    assert job.check_command is None
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.check_passed is None
    assert not store.check_path(job.id).exists()


def test_a_check_timeout_fails_the_check_and_kills_its_group(store, repo):
    # The sandbox lets the check write only in its copy and its own $TMPDIR.
    job = _job(store, repo, "true", check='sleep 30 & echo $! > "$TMPDIR/bg.pid"; wait',
               check_timeout_seconds=1)
    pidfile = store.path(job.id) / "tmp" / "bg.pid"
    started = time.monotonic()
    run(store.path(job.id), executors=FAKE)
    assert time.monotonic() - started < 10
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.check_passed is False
    assert job.check_exit_code is None
    assert "timed out after 1s" in store.check_path(job.id).read_text()
    assert _gone(int(pidfile.read_text()))


def test_finished_process_groups_are_forgotten(store, repo):
    # cancel signals every recorded group; a finished one's id may be reused by the OS.
    job = _job(store, repo, "true", check="")
    job.check_command = f'cp "{store.path(job.id) / "job.json"}" "$TMPDIR/seen.json"'
    store.save(job)
    run(store.path(job.id), executors=FAKE)
    seen = json.loads((store.path(job.id) / "tmp" / "seen.json").read_text())
    assert seen["state"] == "running" and seen["executor_pgid"] is None
    assert store.load(job.id).check_pgid is None


def test_cancel_during_the_check_kills_it(store, repo, fake_agy, wait_for):
    fake_agy("true")
    job = _job(store, repo, "x", executor="agy",
               check='sleep 30 & echo $! > "$TMPDIR/bg.pid"; wait')
    pidfile = store.path(job.id) / "tmp" / "bg.pid"
    launch(store, job)
    deadline = time.monotonic() + 20
    while not pidfile.exists() or not pidfile.read_text().strip():
        assert time.monotonic() < deadline, "check never started"
        time.sleep(0.1)
    assert cancel(store, job.id).state == "cancelled"
    assert _gone(int(pidfile.read_text()))


def test_a_job_json_from_before_the_check_fields_still_loads(store, repo):
    import json
    job = _job(store, repo, "true")
    f = store.path(job.id) / "job.json"
    data = json.loads(f.read_text())
    for key in ("check_command", "check_timeout_seconds", "check_exit_code",
                "check_passed", "check_pgid", "outcome"):
        del data[key]
    f.write_text(json.dumps(data))
    loaded = store.load(job.id)
    assert loaded.check_command is None and loaded.outcome is None


# --- revise: a second attempt in the same copy, on top of the first. ---


class PromptExecutor(ShellExecutor):
    """Runs the prompt's first line as shell and records the whole prompt beside the copy.

    The first line is the original instruction, so a test script can look at
    the files to tell which attempt it is on.
    """

    def build_argv(self, instruction, mode, cwd, model=None):
        script = instruction.splitlines()[0] + '; printf "%s" "$1" > ../prompt.txt'
        return ["/bin/sh", "-c", script, "sh", instruction]


PROMPTED = {"shell": PromptExecutor}
TWO_STEP = "if [ -f a.txt ]; then echo two > b.txt; echo second; else echo one > a.txt; echo first; fi"


def test_revise_runs_again_on_top_of_the_previous_attempt(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, TWO_STEP)
    base = job.base_commit
    run(store.path(job.id), executors=PROMPTED)
    first_prompt = (store.path(job.id) / "prompt.txt").read_text()
    assert first_prompt == TWO_STEP

    job = revise(store, job.id, "also add b.txt")
    assert job.state == "queued"
    assert job.attempt == 2
    assert job.feedback == ["also add b.txt"]
    assert (store.path(job.id) / "output-1.txt").read_text().strip() == "first"
    assert not store.output_path(job.id).exists()

    run(store.path(job.id), executors=PROMPTED)
    job = store.load(job.id)
    assert job.state == "succeeded", job.error
    assert job.base_commit == base
    assert job.files_changed == ["a.txt", "b.txt"]
    assert "a.txt" in job.diff_stat and "b.txt" in job.diff_stat
    assert _git("rev-list", "--count", f"{base}..HEAD", cwd=job.workdir) == "2"
    assert store.output_path(job.id).read_text().strip() == "second"
    assert "+one" in diff(store, job.id) and "+two" in diff(store, job.id)

    prompt = (store.path(job.id) / "prompt.txt").read_text()
    assert prompt.startswith(TWO_STEP)
    assert "attempt 2" in prompt
    assert "also add b.txt" in prompt


def test_every_revision_carries_all_feedback_in_order(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, "echo x >> log.txt")
    run(store.path(job.id), executors=PROMPTED)
    revise(store, job.id, "first note")
    run(store.path(job.id), executors=PROMPTED)
    job = revise(store, job.id, "second note")
    assert job.attempt == 3
    run(store.path(job.id), executors=PROMPTED)
    prompt = (store.path(job.id) / "prompt.txt").read_text()
    assert "attempt 3" in prompt
    assert prompt.index("first note") < prompt.index("second note")
    assert (store.path(job.id) / "output-1.txt").exists()
    assert (store.path(job.id) / "output-2.txt").exists()
    assert (Path(store.load(job.id).workdir) / "log.txt").read_text() == "x\nx\nx\n"


def test_revise_resets_the_result_and_the_old_process_ids(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, "echo partial > p.txt; exit 3")
    run(store.path(job.id), executors=FAKE)
    assert store.load(job.id).state == "failed"
    job = revise(store, job.id, "exit cleanly", timeout_seconds=120)
    assert (job.state, job.exit_code, job.error, job.finished_at) == ("queued", None, None, None)
    # A stale process group id would let cancel signal whatever reused it.
    assert job.pid is None and job.pgid is None
    assert job.timeout_seconds == 120
    assert store.load(job.id) == job


def test_revise_keeps_the_timeout_unless_given(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, "true")
    run(store.path(job.id), executors=FAKE)
    assert revise(store, job.id, "again").timeout_seconds == job.timeout_seconds


def test_revise_refuses_an_active_job(store, repo):
    from polyphony.jobs import JobError, revise
    job = _job(store, repo, "true")
    with pytest.raises(JobError, match="queued"):
        revise(store, job.id, "more")


def test_revise_refuses_an_applied_job(store, repo):
    from polyphony.jobs import JobError, apply, revise
    job = _job(store, repo, "echo hi > new.txt")
    run(store.path(job.id), executors=FAKE)
    apply(store, job.id)
    assert store.load(job.id).applied
    with pytest.raises(JobError, match="discard"):
        revise(store, job.id, "more")


def test_revise_refuses_a_job_whose_copy_is_gone(store, repo):
    import shutil

    from polyphony.jobs import JobError, revise
    job = _job(store, repo, "true")
    run(store.path(job.id), executors=FAKE)
    shutil.rmtree(job.workdir)
    with pytest.raises(JobError, match="copy"):
        revise(store, job.id, "more")


def test_revise_refuses_empty_feedback(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, "true")
    run(store.path(job.id), executors=FAKE)
    with pytest.raises(ValueError):
        revise(store, job.id, "   ")


def test_first_attempt_prompt_is_the_instruction_alone(store, repo):
    from polyphony.jobs import prompt
    job = _job(store, repo, "do the thing")
    assert prompt(job) == "do the thing"


def test_a_job_record_from_before_revise_still_loads(store, repo):
    import json
    job = _job(store, repo, "true")
    f = store.path(job.id) / "job.json"
    record = json.loads(f.read_text())
    for key in ("feedback", "attempt"):
        del record[key]
    f.write_text(json.dumps(record))
    loaded = store.load(job.id)
    assert (loaded.feedback, loaded.attempt, loaded.applied) == ([], 1, False)


def test_active_counts_span_projects_and_ignore_dead_workers(store, repo):
    from polyphony.jobs import active_counts
    a = _job(store, repo, "true", executor="agy")
    b = create_job(store, ProjectConfig(name="other", path=repo), "true", "agy", "code")
    _job(store, repo, "true", executor="cursor")
    done = _job(store, repo, "true", executor="cursor")
    done.state = "succeeded"
    store.save(done)
    assert active_counts(store) == {"agy": 2, "cursor": 1}

    p = subprocess.Popen(["true"])
    p.wait()
    b.state, b.pid = "running", p.pid
    store.save(b)
    assert active_counts(store) == {"agy": 1, "cursor": 1}
    assert store.load(a.id).state == "queued"


# --- Partial apply ---


def _two_file_job(store, repo):
    job = _job(store, repo, "echo hi > new.txt && echo 'x = 5' > app.py")
    run(store.path(job.id), executors=FAKE)
    assert sorted(store.load(job.id).files_changed) == ["app.py", "new.txt"]
    return job


def test_partial_apply_stages_only_the_named_paths(store, repo):
    from polyphony.jobs import apply
    job = _two_file_job(store, repo)
    assert apply(store, job.id, paths=["new.txt"]) == ["new.txt"]
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "new.txt"
    assert (repo / "app.py").read_text() == "x = 1\n"
    assert store.load(job.id).applied_paths == ["new.txt"]


def test_full_apply_after_a_partial_one_applies_the_rest(store, repo):
    from polyphony.jobs import apply
    job = _two_file_job(store, repo)
    apply(store, job.id, paths=["new.txt"])
    assert apply(store, job.id) == ["app.py"]
    assert (repo / "app.py").read_text() == "x = 5\n"
    assert sorted(store.load(job.id).applied_paths) == ["app.py", "new.txt"]


def test_partial_apply_over_unstaged_edits_then_the_rest_staged(store, repo):
    from polyphony.jobs import apply
    (repo / "app.py").write_text("x = 2\n")
    job = _job(store, repo, "echo 'y = 3' >> app.py && echo hi > new.txt")
    run(store.path(job.id), executors=FAKE)
    assert apply(store, job.id, paths=["app.py"]) == ["app.py"]
    assert (repo / "app.py").read_text() == "x = 2\ny = 3\n"
    assert store.load(job.id).applied_unstaged
    assert apply(store, job.id) == ["new.txt"]
    assert not store.load(job.id).applied_unstaged
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "new.txt"


def test_applying_a_path_twice_is_refused_without_changing_anything(store, repo):
    from polyphony.jobs import JobError, apply
    job = _two_file_job(store, repo)
    apply(store, job.id, paths=["new.txt"])
    (repo / "new.txt").write_text("mine now\n")
    with pytest.raises(JobError, match="already applied.*new.txt"):
        apply(store, job.id, paths=["new.txt", "app.py"])
    assert (repo / "new.txt").read_text() == "mine now\n"
    assert (repo / "app.py").read_text() == "x = 1\n"
    assert store.load(job.id).applied_paths == ["new.txt"]


def test_full_apply_of_an_already_applied_job_is_refused(store, repo):
    from polyphony.jobs import JobError, apply
    job = _job(store, repo, "echo hi > new.txt")
    run(store.path(job.id), executors=FAKE)
    apply(store, job.id)
    with pytest.raises(JobError, match="already applied"):
        apply(store, job.id)


def test_unknown_paths_are_refused_by_name(store, repo):
    from polyphony.jobs import JobError, apply
    job = _two_file_job(store, repo)
    with pytest.raises(JobError) as e:
        apply(store, job.id, paths=["new.txt", "nope.py", "also/missing"])
    assert "nope.py" in str(e.value) and "also/missing" in str(e.value)
    assert "new.txt" not in str(e.value).split("It changed")[0]
    assert _git("status", "--porcelain", cwd=repo) == ""
    assert store.load(job.id).applied_paths == []


def test_an_empty_path_list_is_refused(store, repo):
    from polyphony.jobs import JobError, apply
    job = _two_file_job(store, repo)
    with pytest.raises(JobError, match="paths"):
        apply(store, job.id, paths=[])
    assert _git("status", "--porcelain", cwd=repo) == ""


@pytest.mark.parametrize("side", ["app.py", "main.py"])
def test_a_rename_is_applied_whole_from_either_side(store, repo, side):
    from polyphony.jobs import apply
    job = _job(store, repo, "git mv app.py main.py && echo hi > new.txt")
    run(store.path(job.id), executors=FAKE)
    apply(store, job.id, paths=[side])
    assert not (repo / "app.py").exists()
    assert (repo / "main.py").read_text() == "x = 1\n"
    assert not (repo / "new.txt").exists()
    job = store.load(job.id)
    assert "new.txt" not in job.applied_paths
    assert apply(store, job.id) == ["new.txt"]


# --- Garbage collection ---


def _finished(store, repo, state="succeeded", age_seconds=0.0, finished=True):
    job = _job(store, repo, "true")
    job.state = state
    job.created_at = time.time() - age_seconds
    job.finished_at = job.created_at if finished else None
    store.save(job)
    return job


def test_gc_removes_only_finished_jobs_older_than_the_threshold(store, repo):
    from polyphony.jobs import gc
    old = _finished(store, repo, "succeeded", age_seconds=10 * 86400)
    old_dead = _finished(store, repo, "died", age_seconds=10 * 86400, finished=False)
    recent = _finished(store, repo, "failed", age_seconds=60)
    queued = _finished(store, repo, "queued", age_seconds=10 * 86400, finished=False)
    running = _finished(store, repo, "running", age_seconds=10 * 86400, finished=False)
    running.pid = os.getpid()
    store.save(running)

    records = gc(store, older_than_seconds=7 * 86400)

    assert sorted(r.job_id for r in records) == sorted([old.id, old_dead.id])
    for r in records:
        assert r.bytes > 0
        assert r.age_seconds >= 10 * 86400 - 5
        assert not store.path(r.job_id).exists()
    assert {r.state for r in records} == {"succeeded", "died"}
    for kept in (recent, queued, running):
        assert store.path(kept.id).exists()


def test_gc_dry_run_deletes_nothing(store, repo):
    from polyphony.jobs import gc
    old = _finished(store, repo, "cancelled", age_seconds=3600)
    records = gc(store, older_than_seconds=60, dry_run=True)
    assert [r.job_id for r in records] == [old.id]
    assert records[0].bytes > 0
    assert store.path(old.id).exists()


def test_gc_does_not_follow_link_mode_symlinks(store, repo):
    from polyphony.jobs import gc
    job = _job(store, repo, "true", provision=[{"path": "env/", "mode": "link"}])
    job.state, job.finished_at = "succeeded", time.time() - 3600
    store.save(job)
    gc(store, older_than_seconds=60)
    assert not store.path(job.id).exists()
    assert (repo / "env" / "marker").read_text() == "venv\n"


def test_gc_with_no_jobs(store):
    from polyphony.jobs import gc
    assert gc(store, older_than_seconds=0) == []


# --- How revise, the check, partial apply, and gc work together. ---


def test_revise_runs_the_check_again_on_the_new_attempt(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, TWO_STEP, check="test -f b.txt && echo has b")
    run(store.path(job.id), executors=PROMPTED)
    job = store.load(job.id)
    assert job.check_passed is False and job.check_exit_code == 1

    job = revise(store, job.id, "add b.txt")
    assert (job.check_passed, job.check_exit_code) == (None, None)
    assert job.executor_pgid is None and job.check_pgid is None
    assert not store.check_path(job.id).exists()
    assert (store.path(job.id) / "check-1.txt").exists()

    run(store.path(job.id), executors=PROMPTED)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.check_passed is True and job.check_exit_code == 0
    assert "has b" in store.check_path(job.id).read_text()


def test_a_failed_revision_does_not_keep_the_old_check_result(store, repo):
    from polyphony.jobs import revise
    job = _job(store, repo, "if [ -f new.txt ]; then exit 1; fi; echo hi > new.txt", check="true")
    run(store.path(job.id), executors=PROMPTED)
    assert store.load(job.id).check_passed is True
    revise(store, job.id, "try again")
    run(store.path(job.id), executors=PROMPTED)  # fails this time, so no check runs
    job = store.load(job.id)
    assert job.state == "failed"
    assert job.check_passed is None and not store.check_path(job.id).exists()


def test_revise_is_refused_after_a_partial_apply(store, repo):
    from polyphony.jobs import JobError, apply, revise
    job = _two_file_job(store, repo)
    apply(store, job.id, paths=["new.txt"])
    with pytest.raises(JobError, match="discard"):
        revise(store, job.id, "fix app.py")


def test_partial_apply_records_applied_once_with_the_count(store, repo):
    from polyphony import ledger
    from polyphony.jobs import apply
    job = _two_file_job(store, repo)
    apply(store, job.id, paths=["new.txt"])
    apply(store, job.id)
    discard(store, job.id)
    [entry] = ledger.read(store.root)
    assert entry["outcome"] == "applied"
    assert (entry["files_changed"], entry["files_applied"]) == (2, 1)


def test_revise_writes_no_ledger_line_and_the_outcome_carries_the_attempts(store, repo):
    from polyphony import ledger
    from polyphony.jobs import apply, revise
    job = _job(store, repo, TWO_STEP)
    run(store.path(job.id), executors=PROMPTED)
    revise(store, job.id, "add b.txt")
    assert ledger.read(store.root) == []
    run(store.path(job.id), executors=PROMPTED)
    apply(store, job.id)
    [entry] = ledger.read(store.root)
    assert (entry["outcome"], entry["attempts"]) == ("applied", 2)


def test_a_cancelled_attempt_that_is_revised_counts_once_by_its_final_outcome(store, repo):
    from polyphony import ledger
    from polyphony.jobs import apply, revise
    job = _job(store, repo, "echo hi > new.txt")
    cancel(store, job.id)
    assert [e["outcome"] for e in ledger.read(store.root)] == ["cancelled"]
    job = revise(store, job.id, "run it after all")
    assert job.outcome is None
    run(store.path(job.id), executors=PROMPTED)
    apply(store, job.id)
    discard(store, job.id)
    assert [(e["job_id"], e["outcome"]) for e in ledger.read(store.root)] == [(job.id, "applied")]


def test_gc_records_a_discard_for_a_job_with_no_outcome(store, repo):
    from polyphony import ledger
    from polyphony.jobs import apply, gc
    applied = _two_file_job(store, repo)
    apply(store, applied.id)
    left = _job(store, repo, "echo x > x.txt")
    run(store.path(left.id), executors=FAKE)

    assert len(gc(store, older_than_seconds=0, dry_run=True)) == 2
    assert [e["outcome"] for e in ledger.read(store.root)] == ["applied"]

    gc(store, older_than_seconds=0)
    entries = {e["job_id"]: e for e in ledger.read(store.root)}
    assert entries[applied.id]["outcome"] == "applied" and "via" not in entries[applied.id]
    assert entries[left.id]["outcome"] == "discarded" and entries[left.id]["via"] == "gc"


# --- Merge blockers: the check's sandbox, its leftovers, quoted paths, gc races. ---


def test_the_check_cannot_write_outside_its_copy(store, repo):
    # The agent only writes a script in its copy; the check runs it.
    agent = (
        "cat > run_tests.sh <<'SH'\n"
        "REPO=$(python3 -c \"import json;print(json.load(open('../job.json'))['repo'])\")\n"
        "echo pwned > \"$REPO/written_by_check.txt\"\n"
        "echo pwned > ../job_dir_write.txt\n"
        "SH"
    )
    job = _job(store, repo, agent, check="sh run_tests.sh")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.check_passed is False
    assert not (Path(repo) / "written_by_check.txt").exists()
    assert not (store.path(job.id) / "job_dir_write.txt").exists()


def test_the_check_cannot_write_to_the_copys_git_dir(store, repo):
    job = _job(store, repo, "true", check='echo x >> "$(git rev-parse --absolute-git-dir)/config"')
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.check_passed is False
    assert "x" not in (Path(job.git_dir) / "config").read_text().split()


def test_the_check_gets_a_private_temp_dir(store, repo):
    job = _job(store, repo, "true",
               check='python3 -c "import tempfile; print(tempfile.mkstemp()[1])"')
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.check_passed is True
    written = store.check_path(job.id).read_text().strip()
    assert Path(written).resolve().is_relative_to((store.path(job.id) / "tmp").resolve())


def test_no_sandbox_means_the_check_does_not_run(store, repo, monkeypatch, tmp_path):
    from polyphony import jobs
    monkeypatch.setattr(jobs, "_sandbox_argv", lambda job, tmp: None)
    marker = tmp_path / "ran"
    job = _job(store, repo, "true", check=f"touch {marker}")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.check_passed is False and job.check_exit_code is None
    assert "sandbox" in store.check_path(job.id).read_text()
    assert not marker.exists()


def test_bwrap_sandbox_argv_binds_only_the_copy_and_tmp(monkeypatch, tmp_path):
    from polyphony import jobs
    monkeypatch.setattr(jobs.sys, "platform", "linux")
    monkeypatch.setattr(jobs.shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    work, tmp = tmp_path / "repo", tmp_path / "tmp"
    work.mkdir()
    tmp.mkdir()
    git_dir = tmp_path / "git"
    git_dir.mkdir()
    job = type("J", (), {"workdir": str(work), "git_dir": str(git_dir)})()
    argv = jobs._sandbox_argv(job, tmp)
    assert argv[0] == "/usr/bin/bwrap"
    joined = " ".join(argv)
    assert "--ro-bind / /" in joined and "--unshare-net" in joined
    assert f"--bind {work.resolve()} {work.resolve()}" in joined
    assert f"--ro-bind {git_dir.resolve()} {git_dir.resolve()}" in joined
    assert f"--bind {tmp.resolve()} {tmp.resolve()}" in joined
    legacy = type("J", (), {"workdir": str(work), "git_dir": None})()
    assert f"--ro-bind {work.resolve() / '.git'}" in " ".join(jobs._sandbox_argv(legacy, tmp))


def test_what_the_check_writes_stays_out_of_a_revised_attempt(store, repo):
    from polyphony.jobs import apply, revise
    job = _job(store, repo, "echo y = 2 > app.py",
               check="echo cov > coverage.out; echo lock >> app.py")
    run(store.path(job.id), executors=PROMPTED)
    assert store.load(job.id).files_changed == ["app.py"]
    revise(store, job.id, "again")
    run(store.path(job.id), executors=PROMPTED)
    job = store.load(job.id)
    assert job.check_passed is True
    assert job.files_changed == ["app.py"]
    apply(store, job.id)
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "app.py"
    assert (Path(repo) / "app.py").read_text() == "y = 2\n"


def test_resetting_after_the_check_keeps_linked_paths(store, repo):
    job = _job(store, repo, "echo hi > new.txt", provision=[{"path": "env/", "mode": "link"}],
               check="echo junk > junk.txt; echo x > env/from_check || true")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    copy = Path(job.workdir)
    assert job.check_passed is True
    assert (copy / "env").is_symlink() and (copy / "env" / "marker").exists()
    assert not (copy / "junk.txt").exists()
    assert not (Path(repo) / "env" / "from_check").exists()  # the link target is read-only
    assert job.files_changed == ["new.txt"]


def test_files_changed_holds_real_names_for_unusual_paths(store, repo):
    from polyphony.jobs import apply
    job = _job(store, repo, "echo a > a.txt; echo b > b.txt; echo h > 'héllo.txt'")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert sorted(job.files_changed) == ["a.txt", "b.txt", "héllo.txt"]
    apply(store, job.id, paths=["a.txt"])
    assert sorted(apply(store, job.id)) == ["b.txt", "héllo.txt"]
    staged = _git("-c", "core.quotepath=false", "diff", "--cached", "--name-only", cwd=repo)
    assert sorted(staged.splitlines()) == ["a.txt", "b.txt", "héllo.txt"]


def test_gc_leaves_a_job_revised_while_it_runs(store, repo, monkeypatch):
    from polyphony import jobs
    older = _job(store, repo, "echo y = 2 > app.py")
    run(store.path(older.id), executors=FAKE)
    newer = _job(store, repo, "echo y = 3 > app.py")
    run(store.path(newer.id), executors=FAKE)
    for jid, t in ((older.id, 1000.0), (newer.id, 2000.0)):
        j = store.load(jid)
        j.created_at = j.finished_at = t
        store.save(j)

    real = jobs.disk_usage
    seen = {}

    def slow_disk_usage(path):
        # gc walks the newer job first; meanwhile a client revises the older one.
        if Path(path).name == newer.id and not seen:
            seen["revised"] = jobs.revise(store, older.id, "fix it").state
        return real(path)

    monkeypatch.setattr(jobs, "disk_usage", slow_disk_usage)
    removed = [r.job_id for r in jobs.gc(store, 60)]
    assert seen["revised"] == "queued"
    assert removed == [newer.id]
    assert store.path(older.id).exists()
    assert store.load(older.id).state == "queued"


def test_gc_takes_the_store_lock_before_deleting(store, repo, monkeypatch):
    from polyphony import jobs
    job = _job(store, repo, "true")
    run(store.path(job.id), executors=FAKE)
    held = []
    real_rmtree = jobs.shutil.rmtree

    def rmtree(path, *a, **kw):
        import fcntl
        with open(store.root / "delegate.lock", "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
                held.append(False)
            except BlockingIOError:
                held.append(True)
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(jobs.shutil, "rmtree", rmtree)
    jobs.gc(store, 0)
    assert held == [True]


# The executor can write anything in its copy. Polyphony's own git commands
# there must never run code the executor planted or reach another repository.

def _objects(repo):
    return _git("count-objects", "-v", cwd=repo), _git("rev-list", "--all", cwd=repo)


def test_the_git_dir_is_kept_outside_the_copy(store, repo):
    job = _job(store, repo, "true")
    git_dir = Path(job.git_dir)
    assert git_dir.is_dir() and not git_dir.is_relative_to(job.workdir)
    assert (Path(job.workdir) / ".git").is_file()


def test_a_hook_the_executor_plants_never_runs(store, repo, tmp_path):
    mark = tmp_path / "pwned"
    job = _job(store, repo, f"""
        hooks="$(git rev-parse --absolute-git-dir)/hooks"
        case "$hooks" in "{store.root}"/*) ;; *) exit 9 ;; esac
        mkdir -p "$hooks"
        for h in post-commit pre-commit post-index-change reference-transaction; do
          printf '#!/bin/sh\\ntouch {mark}\\n' > "$hooks/$h"; chmod +x "$hooks/$h"
        done
        echo new > new.txt""")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded" and job.files_changed == ["new.txt"]
    assert not mark.exists()


def test_git_config_the_executor_plants_is_dropped(store, repo, tmp_path):
    mark = tmp_path / "pwned"
    hooks = tmp_path / "evil-hooks"
    hooks.mkdir()
    (hooks / "post-commit").write_text(f"#!/bin/sh\ntouch {mark}\n")
    (hooks / "post-commit").chmod(0o755)
    included = tmp_path / "evil.gitconfig"
    included.write_text(f"[core]\n\tfsmonitor = touch {mark}\n")
    job = _job(store, repo, f"""
        git config core.fsmonitor 'touch {mark}'
        git config core.hooksPath {hooks}
        git config include.path {included}
        git config filter.x.clean 'touch {mark}; cat'
        echo '*.txt filter=x' > .gitattributes
        echo new > new.txt""")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert "new.txt" in job.files_changed
    assert "evil" not in (Path(job.git_dir) / "config").read_text()
    diff(store, job.id)
    assert not mark.exists()


def test_replacing_dot_git_cannot_point_polyphony_at_another_repo(store, repo):
    before = _objects(repo)
    job = _job(store, repo, f"""
        rm -rf .git; printf 'gitdir: {repo}/.git\\n' > .git
        echo new > new.txt""")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded" and job.files_changed == ["new.txt"]
    assert _objects(repo) == before
    assert (Path(job.workdir) / ".git").read_text().strip() == f"gitdir: {job.git_dir}"


def test_a_commondir_file_cannot_share_another_repos_git_dir(store, repo):
    before = _objects(repo)
    job = _job(store, repo, f"""
        printf '{repo}/.git\\n' > "$(git rev-parse --absolute-git-dir)/commondir"
        echo new > new.txt""")
    run(store.path(job.id), executors=FAKE)
    job = store.load(job.id)
    assert job.state == "succeeded" and job.files_changed == ["new.txt"]
    assert _objects(repo) == before


# Worker races and stuck slots.

def test_a_stale_worker_does_not_run_a_revised_job(store, repo):
    job = _job(store, repo, "echo run >> runs.txt; exit 0")  # exit: the rest of a revised prompt is prose
    job.state = "cancelled"
    store.save(job)
    revise(store, job.id, "again")
    run(store.path(job.id), executors=FAKE, attempt=1)  # the cancelled attempt's worker, late
    assert store.load(job.id).state == "queued"
    run(store.path(job.id), executors=FAKE, attempt=2)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert (Path(job.workdir) / "runs.txt").read_text() == "run\n"


def test_a_queued_job_whose_worker_never_started_stops_holding_a_slot(store, repo):
    stuck = _job(store, repo, "true")
    stuck.queued_at = time.time() - QUEUE_GRACE_SECONDS - 1
    store.save(stuck)
    fresh = _job(store, repo, "true")
    assert store.refresh(store.load(stuck.id)).state == "died"
    assert "never started" in store.load(stuck.id).error
    assert store.refresh(store.load(fresh.id)).state == "queued"
    assert active_counts(store)["shell"] == 1


def test_refresh_under_the_store_lock_does_not_deadlock(store, repo):
    import threading
    stuck = _job(store, repo, "true")
    stuck.queued_at = time.time() - QUEUE_GRACE_SECONDS - 1
    store.save(stuck)
    done = []

    def count():
        with store.lock():
            done.append(active_counts(store)["shell"])

    worker = threading.Thread(target=count, daemon=True)
    worker.start()
    worker.join(timeout=10)
    assert done == [0]


# --- Secrets: withheld files, and environment variables kept from the agent and the check. ---


def test_a_job_records_the_secrets_its_copy_withheld(store, repo):
    (repo / ".env").write_text("API_KEY=real\n")
    (repo / ".env.example").write_text("API_KEY=\n")
    job = _job(store, repo, "true")
    assert job.withheld == [".env"]
    assert not (Path(job.workdir) / ".env").exists()
    assert (Path(job.workdir) / ".env.example").exists()
    assert store.load(job.id).withheld == [".env"]


def test_allow_secrets_from_the_project_reach_the_copy(store, repo):
    (repo / ".env").write_text("API_KEY=real\n")
    project = ProjectConfig(name="demo", path=repo, allow_secrets=[".env"])
    job = create_job(store, project=project, instruction="true", executor="shell", mode="code")
    assert job.withheld == []
    assert (Path(job.workdir) / ".env").exists()


def test_env_scrub_keeps_variables_from_the_executor(store, repo, fake_agy, monkeypatch):
    monkeypatch.setenv("SCRUB_ME_PLEASE", "hidden")
    monkeypatch.setenv("KEEP_ME", "visible")
    fake_agy("env")
    project = ProjectConfig(name="demo", path=repo, env_scrub=["SCRUB_ME_*"])
    job = create_job(store, project=project, instruction="x", executor="agy", mode="code")
    run(store.path(job.id))
    out = store.output_path(job.id).read_text()
    assert store.load(job.id).state == "succeeded", out
    assert "KEEP_ME=visible" in out
    assert "SCRUB_ME_PLEASE" not in out


def test_the_executor_keeps_its_credentials_by_default(store, repo, fake_agy, monkeypatch):
    monkeypatch.setenv("AGY_API_KEY", "needed")
    fake_agy("env")
    job = _job(store, repo, "x", executor="agy")
    run(store.path(job.id))
    assert "AGY_API_KEY=needed" in store.output_path(job.id).read_text()


def test_the_check_loses_credential_variables_but_keeps_path(store, repo, monkeypatch):
    monkeypatch.setenv("FOO_API_KEY", "k")
    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("foo_api_key", "lower")  # names are matched case-sensitively
    monkeypatch.setenv("EXTRA_SCRUB", "e")
    project = ProjectConfig(name="demo", path=repo, env_scrub=["EXTRA_*"])
    job = create_job(store, project=project, instruction="true", executor="shell",
                     mode="code", check="env")
    run(store.path(job.id), executors=FAKE)
    assert store.load(job.id).check_passed is True
    seen = store.check_path(job.id).read_text()
    for gone in ("FOO_API_KEY", "GH_TOKEN", "DB_PASSWORD", "EXTRA_SCRUB"):
        assert f"{gone}=" not in seen, gone
    assert "foo_api_key=lower" in seen
    assert "PATH=" in seen


def test_a_job_json_from_before_the_secrets_fields_still_loads(store, repo):
    job = _job(store, repo, "true")
    f = store.path(job.id) / "job.json"
    data = json.loads(f.read_text())
    del data["withheld"], data["env_scrub"]
    f.write_text(json.dumps(data))
    loaded = store.load(job.id)
    assert loaded.withheld == [] and loaded.env_scrub == []


# --- Lane r2-brief: a task given as a brief file. ---


def test_a_brief_is_copied_and_joined_to_the_instruction(store, repo, tmp_path):
    from polyphony.jobs import prompt, read_brief
    f = tmp_path / "brief.md"
    f.write_text("line one\nline two\n")
    job = _job(store, repo, "Lead in.", brief=read_brief(str(f), repo))
    f.write_text("changed")
    assert job.instruction == "Lead in.\n\nline one\nline two\n"
    assert prompt(store.load(job.id)) == job.instruction
    assert store.brief_copy_path(job.id).read_text() == "line one\nline two\n"
    assert store.load(job.id).brief_path == str(f.resolve())


def test_a_brief_without_an_instruction_is_the_whole_task(store, repo, tmp_path):
    from polyphony.jobs import read_brief
    f = tmp_path / "brief.md"
    f.write_text("brief only")
    assert _job(store, repo, "", brief=read_brief(str(f), repo)).instruction == "brief only"


def test_read_brief_takes_a_relative_path_from_the_base(repo):
    from polyphony.jobs import read_brief
    (repo / "b.md").write_text("hi")
    assert read_brief("b.md", repo) == ((repo / "b.md").resolve(), "hi")


def test_a_job_without_a_brief_has_no_brief_file(store, repo):
    job = _job(store, repo, "true")
    assert job.brief_path is None
    assert not store.brief_copy_path(job.id).exists()


def test_a_job_record_from_before_briefs_still_loads(store, repo):
    job = _job(store, repo, "true")
    f = store.path(job.id) / "job.json"
    record = json.loads(f.read_text())
    del record["brief_path"]
    f.write_text(json.dumps(record))
    assert store.load(job.id).brief_path is None


# --- Report mode: a read-only audit whose findings are a file. ---


class ReportExecutor(PromptExecutor):
    """PromptExecutor that also records the mode it was run in."""

    def build_argv(self, instruction, mode, cwd, model=None):
        argv = super().build_argv(instruction, mode, cwd, model)
        argv[2] += f"; echo {mode.value} > ../mode.txt"
        return argv


REPORTING = {"shell": ReportExecutor}


def test_report_job_runs_in_code_mode_and_saves_its_report(store, repo):
    from polyphony.jobs import REPORT_INSTRUCTION, read_report
    job = _job(store, repo, "printf '# Findings\\n\\nnone\\n' > REPORT.md", mode="report")
    assert job.check_command is None
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "succeeded", job.error
    assert (store.path(job.id) / "mode.txt").read_text().strip() == "code"
    assert REPORT_INSTRUCTION in (store.path(job.id) / "prompt.txt").read_text()
    assert job.report_path == str(store.report_path(job.id))
    assert read_report(store, job.id) == "# Findings\n\nnone\n"
    assert job.files_changed == ["REPORT.md"]
    assert job.stray_changes == []


def test_report_job_records_changes_besides_the_report(store, repo):
    job = _job(store, repo, "echo r > REPORT.md; echo y > app.py", mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "succeeded"
    assert job.stray_changes == ["app.py"]


def test_report_job_that_writes_no_report_fails(store, repo):
    from polyphony.jobs import JobError, read_report
    job = _job(store, repo, "echo all good", mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "failed"
    assert "REPORT.md" in job.error and "output" in job.error
    assert job.report_path is None
    assert "all good" in store.output_path(job.id).read_text()
    with pytest.raises(JobError, match="no report"):
        read_report(store, job.id)


def test_a_failed_report_job_keeps_its_own_error_and_any_report(store, repo):
    job = _job(store, repo, "echo partial > REPORT.md; exit 3", mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "failed" and job.exit_code == 3
    assert "REPORT.md" not in (job.error or "")
    assert store.report_path(job.id).read_text() == "partial\n"


def test_an_unchanged_tracked_report_is_not_this_jobs(store, repo):
    (repo / "REPORT.md").write_text("old findings\n")
    _git("add", "REPORT.md", cwd=repo)
    _git("commit", "-q", "-m", "old report", cwd=repo)
    job = _job(store, repo, "echo nothing new", mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "failed" and job.report_path is None

    job = _job(store, repo, "echo new findings > REPORT.md", mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "succeeded", job.error
    assert store.report_path(job.id).read_text() == "new findings\n"


def test_a_symlinked_report_is_not_read(store, repo, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private\n")
    job = _job(store, repo, f"ln -s {secret} REPORT.md", mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = store.load(job.id)
    assert job.state == "failed" and job.report_path is None
    assert not store.report_path(job.id).exists()


def test_revising_a_report_job_archives_the_report_and_restates_the_rule(store, repo):
    from polyphony.jobs import REPORT_INSTRUCTION, read_report
    script = "if [ -f REPORT.md ]; then echo second > REPORT.md; else echo first > REPORT.md; fi"
    job = _job(store, repo, script, mode="report")
    run(store.path(job.id), executors=REPORTING)
    job = revise(store, job.id, "go deeper")
    assert job.report_path is None and job.stray_changes == []
    assert (store.path(job.id) / "report-1.md").read_text() == "first\n"
    assert not store.report_path(job.id).exists()

    run(store.path(job.id), executors=REPORTING)
    assert read_report(store, job.id) == "second\n"
    prompt = (store.path(job.id) / "prompt.txt").read_text()
    assert REPORT_INSTRUCTION in prompt and "go deeper" in prompt
    assert prompt.index(REPORT_INSTRUCTION) < prompt.index("go deeper")


def test_report_pages_through_the_text(store, repo):
    from polyphony.jobs import report
    job = _job(store, repo, "printf 'abcdefghij' > REPORT.md", mode="report")
    run(store.path(job.id), executors=REPORTING)
    assert report(store, job.id, limit=4) == {
        "job_id": job.id, "total_chars": 10, "offset": 0, "text": "abcd", "more": True,
    }
    last = report(store, job.id, offset=8, limit=4)
    assert last["text"] == "ij" and last["more"] is False
    assert report(store, job.id, offset=20)["text"] == ""
    with pytest.raises(ValueError, match="offset"):
        report(store, job.id, offset=-1)
    with pytest.raises(ValueError, match="limit"):
        report(store, job.id, limit=0)


def test_report_refuses_an_active_or_non_report_job(store, repo):
    from polyphony.jobs import JobError, report
    active = _job(store, repo, "true", mode="report")
    with pytest.raises(JobError, match="still queued"):
        report(store, active.id)
    code = _job(store, repo, "true")
    run(store.path(code.id), executors=FAKE)
    with pytest.raises(JobError, match="only a report job"):
        report(store, code.id)


def test_apply_refuses_a_report_job(store, repo):
    from polyphony.jobs import JobError, apply
    job = _job(store, repo, "echo r > REPORT.md", mode="report")
    run(store.path(job.id), executors=REPORTING)
    with pytest.raises(JobError, match="report"):
        apply(store, job.id)
    assert _git("status", "--porcelain", cwd=repo) == ""


# Lane: workspace review fixes.

def test_the_job_home_is_expanded_and_absolute(tmp_path, monkeypatch):
    """POLYPHONY_HOME=~/.polyphony from an MCP config's env block arrives unexpanded."""
    from polyphony.jobs import JobStore
    monkeypatch.setenv("HOME", str(tmp_path))
    assert JobStore(Path("~/.polyphony")).root == tmp_path / ".polyphony"
    monkeypatch.chdir(tmp_path)
    assert JobStore(Path("rel")).root == tmp_path / "rel"
