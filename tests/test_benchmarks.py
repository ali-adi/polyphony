"""Tests for Polyphony benchmark suite and runner."""

from pathlib import Path
from click.testing import CliRunner
import pytest

from benchmarks.runners.benchmark_runner import BenchmarkRunner, BenchmarkSuiteSummary
from orchestrator.cli import cli


def test_benchmark_runner_discovers_15_tasks():
    runner = BenchmarkRunner()
    tasks = runner.list_tasks()
    assert len(tasks) == 15
    assert "task_01_simple_bugfix" in tasks
    assert "task_08_zero_change_false_completion" in tasks
    assert "task_15_deterministic_tooling_sufficient" in tasks


def test_benchmark_runner_single_task():
    runner = BenchmarkRunner()
    res = runner.execute_task("task_01_simple_bugfix")
    assert res.task_id == "task_01_simple_bugfix"
    assert res.correctness is True
    assert res.completion_rate == 1.0
    assert res.total_tokens > 0
    assert res.wall_clock_time >= 0.0
    assert res.rollback_correctness is True
    assert res.diagnosis_quality == 1.0


def test_benchmark_runner_deterministic_task():
    runner = BenchmarkRunner()
    res = runner.execute_task("task_15_deterministic_tooling_sufficient")
    assert res.task_id == "task_15_deterministic_tooling_sufficient"
    assert res.llm_calls == 0
    assert res.total_tokens == 0
    assert res.correctness is True


def test_benchmark_runner_run_all(tmp_path):
    runner = BenchmarkRunner(
        results_dir=tmp_path / "results",
        reports_dir=tmp_path / "reports",
    )
    summary = runner.run_all()
    assert isinstance(summary, BenchmarkSuiteSummary)
    assert summary.total_tasks == 15
    assert summary.passed_tasks == 15
    assert summary.overall_completion_rate == 1.0

    # Verify JSON result file created
    json_files = list((tmp_path / "results").glob("*.json"))
    assert len(json_files) == 1

    # Verify Markdown report created
    md_files = list((tmp_path / "reports").glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "Polyphony Benchmark Suite Report" in content
    assert "Task Results Breakdown" in content


def test_benchmark_cli(tmp_path):
    runner = CliRunner()
    res = runner.invoke(cli, ["benchmark", "--task", "task_01_simple_bugfix"])
    assert res.exit_code == 0
    assert "Running benchmark task: task_01_simple_bugfix" in res.output
    assert "Result: COMPLETED" in res.output
