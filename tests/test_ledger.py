"""The outcome ledger: one line per job outcome, kept after the job is discarded."""

import json

import pytest

from polyphony import ledger
from polyphony.config import ProjectConfig
from polyphony.executors import BaseExecutor
from polyphony.jobs import JobError, apply, cancel, create_job, discard
from polyphony.worker import run


class ShellExecutor(BaseExecutor):
    name = "shell"

    def find_binary(self):
        return "/bin/sh"

    def build_argv(self, instruction, mode, cwd, model=None):
        return ["/bin/sh", "-c", instruction]


FAKE = {"shell": ShellExecutor}


def _run_job(store, repo, instruction="echo hi > new.txt", **kw):
    job = create_job(
        store,
        project=ProjectConfig(name="demo", path=repo),
        instruction=instruction,
        executor="shell",
        mode="code",
        **kw,
    )
    run(store.path(job.id), executors=FAKE)
    return store.load(job.id)


def test_apply_then_discard_is_one_applied_outcome(store, repo):
    job = _run_job(store, repo, check="true")
    apply(store, job.id)
    discard(store, job.id)
    entries = ledger.read(store.root)
    assert len(entries) == 1
    e = entries[0]
    assert e["job_id"] == job.id and e["outcome"] == "applied"
    assert e["project"] == "demo" and e["executor"] == "shell" and e["mode"] == "code"
    assert e["state"] == "succeeded" and e["files_changed"] == 1
    assert e["check_passed"] is True
    assert e["elapsed_seconds"] >= 0 and e["recorded_at"] >= e["created_at"]


def test_the_ledger_survives_discard(store, repo):
    job = _run_job(store, repo)
    discard(store, job.id)
    assert not store.path(job.id).exists()
    assert [e["outcome"] for e in ledger.read(store.root)] == ["discarded"]
    assert ledger.path(store.root).parent == store.root


def test_cancel_then_discard_is_one_cancelled_outcome(store, repo):
    job = create_job(store, project=ProjectConfig(name="demo", path=repo),
                     instruction="x", executor="shell", mode="code")
    cancel(store, job.id)
    discard(store, job.id)
    assert [e["outcome"] for e in ledger.read(store.root)] == ["cancelled"]


def test_cancelling_a_finished_job_records_nothing(store, repo):
    job = _run_job(store, repo)
    cancel(store, job.id)
    assert ledger.read(store.root) == []


def test_a_refused_apply_records_nothing(store, repo):
    job = _run_job(store, repo, instruction="exit 1")
    with pytest.raises(JobError):
        apply(store, job.id)
    assert ledger.read(store.root) == []


def test_read_skips_a_torn_line(tmp_path):
    f = ledger.path(tmp_path)
    f.write_text(json.dumps({"job_id": "a", "executor": "agy"}) + "\n{\"job_id\": \"b\n\n")
    assert [e["job_id"] for e in ledger.read(tmp_path)] == ["a"]


def test_read_with_no_ledger(tmp_path):
    assert ledger.read(tmp_path) == []


def _entry(executor, model, state, outcome, elapsed, check_passed=None):
    return {"executor": executor, "model": model, "state": state, "outcome": outcome,
            "elapsed_seconds": elapsed, "check_passed": check_passed}


def test_summarize_per_executor_and_model():
    entries = [
        _entry("agy", None, "succeeded", "applied", 10, True),
        _entry("agy", None, "succeeded", "discarded", 30, False),
        _entry("agy", "fast", "failed", "discarded", 20),
        _entry("cursor", "composer-2.5", "cancelled", "cancelled", 5),
    ]
    summary = ledger.summarize(entries)
    agy, cursor = summary
    assert agy["executor"] == "agy"
    assert (agy["jobs"], agy["succeeded"], agy["applied"], agy["discarded"]) == (3, 2, 1, 2)
    assert agy["cancelled"] == 0
    assert agy["checks"] == 2 and agy["check_pass_rate"] == 0.5
    assert agy["median_elapsed_seconds"] == 20
    by_model = {m["model"]: m for m in agy["models"]}
    assert by_model[None]["jobs"] == 2 and by_model[None]["median_elapsed_seconds"] == 20
    assert by_model["fast"]["check_pass_rate"] is None
    assert cursor["executor"] == "cursor" and cursor["cancelled"] == 1
    assert cursor["models"][0]["model"] == "composer-2.5"


def test_format_summary_is_readable():
    text = ledger.format_summary(ledger.summarize(
        [_entry("agy", None, "succeeded", "applied", 12.0, True)]))
    assert "agy" in text and "1 applied" in text and "100%" in text
    assert ledger.format_summary([]) == "No outcomes recorded."


def test_only_a_jobs_last_line_counts_and_revisions_are_counted(tmp_path):
    lines = [
        {**_entry("agy", None, "cancelled", "cancelled", 5), "job_id": "a", "attempts": 1},
        {**_entry("agy", None, "succeeded", "applied", 50), "job_id": "b", "attempts": 1},
        {**_entry("agy", None, "succeeded", "applied", 40), "job_id": "a", "attempts": 2},
    ]
    ledger.path(tmp_path).write_text("".join(json.dumps(e) + "\n" for e in lines))
    entries = ledger.read(tmp_path)
    assert [(e["job_id"], e["outcome"]) for e in entries] == [("b", "applied"), ("a", "applied")]
    [agy] = ledger.summarize(entries)
    assert (agy["jobs"], agy["applied"], agy["cancelled"], agy["revised"]) == (2, 2, 0, 1)
    assert "1 revised" in ledger.format_summary([agy])
