"""Tests for DeterministicEngine (Section 18: Deterministic Work Should Not Consume LLM Tokens)."""

import os
import tempfile
from pathlib import Path
import pytest

from orchestrator.deterministic import (
    DeterministicDecision,
    DeterministicEngine,
    DeterministicResult,
)


def test_calculate_metrics():
    engine = DeterministicEngine()
    empty = engine.calculate_metrics([])
    assert empty["count"] == 0

    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    metrics = engine.calculate_metrics(vals)
    assert metrics["count"] == 5.0
    assert metrics["mean"] == 30.0
    assert metrics["median"] == 30.0
    assert metrics["min"] == 10.0
    assert metrics["max"] == 50.0
    assert metrics["p95"] == 50.0
    assert metrics["std_dev"] > 0


def test_aggregate_benchmarks():
    engine = DeterministicEngine()
    records = [
        {"duration_seconds": 1.2, "total_tokens": 1500, "correctness": True},
        {"duration_seconds": 1.4, "total_tokens": 1600, "correctness": True},
        {"duration_seconds": 1.1, "total_tokens": 1400, "correctness": True},
    ]
    agg = engine.aggregate_benchmarks(records)
    assert agg["total_runs"] == 3
    assert agg["pass_rate"] == 1.0
    assert agg["durations"]["mean"] > 1.0
    assert agg["tokens"]["mean"] == 1500.0


def test_file_hashing_and_json():
    engine = DeterministicEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        f = tmp_path / "sample.txt"
        f.write_text("hello world", encoding="utf-8")
        h = engine.hash_file(f)
        assert len(h) == 64  # sha256 hex length

        jf = tmp_path / "sample.json"
        jf.write_text('{"name": "polyphony", "version": "0.2.0"}', encoding="utf-8")
        parsed = engine.parse_json(jf)
        assert parsed["name"] == "polyphony"
        assert parsed["version"] == "0.2.0"

        # Direct string parsing
        parsed2 = engine.parse_json('{"count": 42}')
        assert parsed2["count"] == 42


def test_rule_evaluation_pytest_done():
    """Section 18 explicit requirement:
    pytest -> 19/19 passed -> deterministic rule -> DONE (No LLM confirmation required).
    """
    engine = DeterministicEngine()
    res = {"passed": 19, "failed": 0, "errors": 0, "skipped": 0, "total": 19}
    decision = engine.evaluate_rule("pytest", res)
    assert decision.action == "DONE"
    assert not decision.requires_llm
    assert "19/19 passed" in decision.reason
    assert decision.tokens_saved_estimate > 0

    # Failing tests require LLM
    fail_res = {"passed": 18, "failed": 1, "errors": 0, "skipped": 0, "total": 19}
    fail_dec = engine.evaluate_rule("pytest", fail_res)
    assert fail_dec.action == "FAIL"
    assert fail_dec.requires_llm

    # Static analysis ruff & mypy
    ruff_clean = engine.evaluate_rule("ruff", {"clean": True})
    assert ruff_clean.action == "PASS"
    assert not ruff_clean.requires_llm

    mypy_clean = engine.evaluate_rule("mypy", {"clean": True, "error_count": 0})
    assert mypy_clean.action == "PASS"
    assert not mypy_clean.requires_llm


def test_repo_structure_and_dependencies():
    engine = DeterministicEngine(cwd=Path("."))
    deps = engine.inspect_dependencies()
    assert "pyproject" in deps["sources"]

    struct = engine.get_repo_structure(max_depth=2)
    assert struct["directories"] > 0
    assert struct["files"] > 0
    assert struct["total_entries"] > 0


def test_process_status():
    engine = DeterministicEngine()
    current_pid = os.getpid()
    status = engine.get_process_status(current_pid)
    assert status["alive"] is True
    assert status["status"] == "RUNNING"

    # Dead pid
    dead_status = engine.get_process_status(99999999)
    assert dead_status["alive"] is False
    assert dead_status["status"] == "STOPPED"


def test_can_resolve_and_execute_deterministic():
    engine = DeterministicEngine(cwd=Path("."))
    assert engine.can_resolve_deterministically("git status") is True
    assert engine.can_resolve_deterministically("count tests") is True
    assert engine.can_resolve_deterministically("Refactor whole system with LLM") is False

    res = engine.execute_deterministic("count tests")
    assert res is not None
    assert res.tool == "count_tests"
    assert res.success is True
    assert res.output["test_count"] > 0
