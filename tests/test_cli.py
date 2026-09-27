"""The human-facing command line."""

from importlib.metadata import version as pkg_version

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
    assert {"mcp", "jobs", "discard", "doctor", "usage"} <= set(commands)
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


def test_doctor_reports_every_executor(run):
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
