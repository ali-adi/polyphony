"""The human-facing command line."""

import time
from importlib.metadata import version as pkg_version
from pathlib import Path

import pytest
from click.testing import CliRunner

from polyphony.cli import cli
from polyphony.config import ProjectConfig
from polyphony.jobs import JobStore, create_job


@pytest.fixture
def run(tmp_path):
    def _run(*args):
        return CliRunner().invoke(cli, ["--home", str(tmp_path / "home"), *args])
    return _run


def test_version_comes_from_package_metadata(run):
    result = run("--version")
    assert result.exit_code == 0
    assert pkg_version("polyphony") in result.output


def test_help_lists_exactly_the_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    commands = result.output.split("Commands:")[1].split()
    assert {"mcp", "jobs", "discard", "doctor", "usage", "stats", "gc"} <= set(commands)
    assert "workspace" not in commands


def test_jobs_with_none(run):
    result = run("jobs")
    assert result.exit_code == 0
    assert "No jobs." in result.output


def test_jobs_lists_and_shows_a_job(run, tmp_path, repo):
    store = JobStore(tmp_path / "home")
    job = create_job(
        store,
        project=ProjectConfig(name="demo", path=repo),
        instruction="tidy the imports",
        executor="agy",
        mode="code",
    )
    listed = run("jobs")
    assert listed.exit_code == 0
    assert job.id in listed.output and "queued" in listed.output

    assert "on disk" in listed.output

    shown = run("jobs", job.id)
    assert shown.exit_code == 0
    assert "tidy the imports" in shown.output
    assert job.workdir in shown.output


def test_discard_unknown_job_fails_readably(run):
    result = run("discard", "nope")
    assert result.exit_code != 0
    assert "No job" in result.output


def test_discard_removes_a_finished_job(run, tmp_path, repo):
    store = JobStore(tmp_path / "home")
    job = create_job(
        store,
        project=ProjectConfig(name="demo", path=repo),
        instruction="x",
        executor="agy",
        mode="code",
    )
    job.state = "failed"
    store.save(job)
    result = run("discard", job.id)
    assert result.exit_code == 0, result.output
    assert not store.path(job.id).exists()


def test_doctor_reports_every_executor(run, monkeypatch):
    from polyphony import executors

    # Unavailable stand-ins, because a real cursor's availability check runs the binary.
    stubs = {
        name: type(name, (cls,), {"is_available": lambda self: False})
        for name, cls in executors.EXECUTORS.items()
    }
    monkeypatch.setattr(executors, "EXECUTORS", stubs)
    result = run("doctor")
    assert result.exit_code == 0
    for name in ("agy", "cursor", "claude"):
        assert name in result.output


def test_usage_prints_each_executor(run, monkeypatch):
    from polyphony import usage
    monkeypatch.setattr(usage, "USAGE_CHECKS", {
        "agy": lambda: {"executor": "agy", "ok": True, "credits": 3, "limits": [
            {"models": "Gemini Models", "window": "Weekly Limit",
             "remaining_percent": 89.0, "resets_at": "2026-10-01T02:17:05Z"}]},
        "cursor": lambda: {"executor": "cursor", "ok": False, "error": "timed out"},
    })
    result = run("usage")
    assert result.exit_code == 0
    assert "89% left" in result.output and "credits: 3" in result.output
    assert "ERROR  timed out" in result.output


def test_stats_with_no_outcomes(run):
    result = run("stats")
    assert result.exit_code == 0
    assert "No outcomes recorded." in result.output


def test_stats_summarizes_the_ledger(run, tmp_path, repo):
    store = JobStore(tmp_path / "home")
    job = create_job(
        store,
        project=ProjectConfig(name="demo", path=repo),
        instruction="x",
        executor="agy",
        mode="code",
    )
    job.state = "failed"
    store.save(job)
    assert run("discard", job.id).exit_code == 0
    result = run("stats")
    assert result.exit_code == 0, result.output
    assert "agy" in result.output and "1 discarded" in result.output


def _old_job(tmp_path, repo, state="succeeded", age_seconds=10 * 86400):
    store = JobStore(tmp_path / "home")
    job = create_job(
        store,
        project=ProjectConfig(name="demo", path=repo),
        instruction="x",
        executor="agy",
        mode="code",
    )
    job.state = state
    job.finished_at = time.time() - age_seconds
    store.save(job)
    return store, job


def test_gc_requires_older_than(run):
    result = run("gc")
    assert result.exit_code != 0
    assert "--older-than" in result.output


@pytest.mark.parametrize("bad", ["7", "d", "7x", "-1d", "1.5d"])
def test_gc_rejects_a_bad_duration(run, bad):
    result = run("gc", "--older-than", bad)
    assert result.exit_code != 0
    assert "duration" in result.output


def test_gc_dry_run_lists_and_keeps(run, tmp_path, repo):
    store, job = _old_job(tmp_path, repo)
    result = run("gc", "--older-than", "7d", "--dry-run")
    assert result.exit_code == 0, result.output
    assert job.id in result.output and "succeeded" in result.output and "10d" in result.output
    assert "would free" in result.output
    assert store.path(job.id).exists()


def test_gc_removes_old_finished_jobs_and_keeps_recent_ones(run, tmp_path, repo):
    store, old = _old_job(tmp_path, repo, "failed")
    _, recent = _old_job(tmp_path, repo, "succeeded", age_seconds=60)
    result = run("gc", "--older-than", "12h")
    assert result.exit_code == 0, result.output
    assert old.id in result.output and recent.id not in result.output
    assert "freed" in result.output and "1 job(s)" in result.output
    assert not store.path(old.id).exists()
    assert store.path(recent.id).exists()


def test_gc_with_nothing_to_remove(run):
    result = run("gc", "--older-than", "30m")
    assert result.exit_code == 0
    assert "Nothing" in result.output


@pytest.fixture
def no_probes(monkeypatch):
    """Keep doctor from probing real CLIs; these tests are about config."""
    from polyphony import executors
    monkeypatch.setattr(executors, "EXECUTORS", {})
    monkeypatch.setattr("polyphony.config.PROJECTS_DIR", Path("/nonexistent-legacy"))


@pytest.mark.usefixtures("no_probes")
def test_doctor_names_the_repo_config_file(run, repo, monkeypatch):
    (repo / ".polyphony.yaml").write_text("pool: [cursor]\n")
    monkeypatch.chdir(repo / ".")
    result = run("doctor")
    assert result.exit_code == 0, result.output
    assert str(repo.resolve() / ".polyphony.yaml") in result.output


@pytest.mark.usefixtures("no_probes")
def test_doctor_names_a_home_project_file(run, repo, tmp_path, monkeypatch):
    f = tmp_path / "home" / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True)
    f.write_text(f"name: demo\npath: {repo}\n")
    monkeypatch.chdir(repo)
    result = run("doctor")
    assert str(f) in result.output


@pytest.mark.usefixtures("no_probes")
def test_doctor_says_when_no_config_applies(run, repo, monkeypatch):
    monkeypatch.chdir(repo)
    result = run("doctor")
    assert result.exit_code == 0
    assert "no config" in result.output


@pytest.mark.usefixtures("no_probes")
def test_doctor_outside_a_repository(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("doctor")
    assert result.exit_code == 0
    assert "not in a git repository" in result.output


@pytest.mark.usefixtures("no_probes")
def test_doctor_reports_a_malformed_config_without_crashing(run, repo, monkeypatch):
    (repo / ".polyphony.yaml").write_text("pool: [agy\n")
    monkeypatch.chdir(repo)
    result = run("doctor")
    assert result.exit_code != 0
    assert ".polyphony.yaml" in result.output


def test_jobs_shows_attempts_and_applied_files(run, tmp_path, repo):
    store = JobStore(tmp_path / "home")
    job = create_job(store, project=ProjectConfig(name="demo", path=repo),
                     instruction="x", executor="agy", mode="code")
    job.feedback, job.attempt, job.applied_paths = ["add tests"], 2, ["a.py"]
    store.save(job)
    shown = run("jobs", job.id)
    assert shown.exit_code == 0, shown.output
    assert "attempt    2" in shown.output and "add tests" in shown.output
    assert "applied    a.py" in shown.output
