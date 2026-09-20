"""Tests for Token Efficiency Benchmarking (Section 28: Token Efficiency Benchmarking)."""

import yaml
import pytest
from benchmarks.runners.benchmark_runner import BenchmarkTaskResult


def test_token_efficiency_metrics_schema():
    """Verify Section 28 specification schema:
    correct:
    safe:
    complete:
    tokens:
      input:
      output:
      total:
    calls:
      llm:
      deterministic:
      executor:
    latency:
    iterations:
    human_interventions:
    cache:
      hit_rate:
      reuse:
      redundant_context_ratio:
    """
    res = BenchmarkTaskResult(
        task_id="task_token_01",
        title="ICD-10 Normalization",
        category="token_optimization",
        status="COMPLETED",
        correctness=True,
        completion_rate=1.0,
        iterations=1,
        llm_calls=0,
        deterministic_calls=2,
        executor_calls=1,
        total_tokens=0,
        input_tokens=0,
        output_tokens=0,
        wall_clock_time=0.45,
        human_interventions=0,
        failed_attempts=0,
        recovery_success=False,
        safety_violations=0,
        rollback_correctness=True,
        diagnosis_quality=1.0,
        report_accuracy=1.0,
        context_size=0,
        cache_hit_rate=0.85,
        cache_reuse=3,
        redundant_context_ratio=0.0,
        tokens_per_successful_task=0.0,
    )

    metrics = res.to_token_efficiency_metrics()

    assert metrics["correct"] is True
    assert metrics["safe"] is True
    assert metrics["complete"] is True
    assert metrics["tokens"]["input"] == 0
    assert metrics["tokens"]["output"] == 0
    assert metrics["tokens"]["total"] == 0
    assert metrics["calls"]["llm"] == 0
    assert metrics["calls"]["deterministic"] == 2
    assert metrics["calls"]["executor"] == 1
    assert metrics["latency"] == 0.45
    assert metrics["iterations"] == 1
    assert metrics["human_interventions"] == 0
    assert metrics["cache"]["hit_rate"] == 0.85
    assert metrics["cache"]["reuse"] == 3
    assert metrics["cache"]["redundant_context_ratio"] == 0.0

    # Ensure valid YAML conversion
    yaml_str = yaml.dump(metrics, sort_keys=False)
    parsed = yaml.safe_load(yaml_str)
    assert parsed["calls"]["deterministic"] == 2


def test_strategy_comparison_not_raw_token_alone():
    """Verify Section 28:
    Compare orchestration strategies based on:
    correctness + safety + completeness + latency + reasoning expenditure
    not raw token count alone.
    """
    # Strategy A: 0 tokens, but failed correctness and had safety violation
    broken_cheap = BenchmarkTaskResult(
        task_id="task_strat_a",
        title="Cheap but Broken",
        category="evaluation",
        status="FAILED",
        correctness=False,
        completion_rate=0.2,
        iterations=1,
        llm_calls=0,
        deterministic_calls=0,
        executor_calls=1,
        total_tokens=0,
        input_tokens=0,
        output_tokens=0,
        wall_clock_time=1.0,
        human_interventions=0,
        failed_attempts=1,
        recovery_success=False,
        safety_violations=1,
        rollback_correctness=True,
        diagnosis_quality=0.0,
        report_accuracy=0.0,
        context_size=0,
        cache_hit_rate=0.0,
    )

    # Strategy B: spent 4000 tokens, but 100% correct, safe, complete, fast, with high reasoning expenditure efficiency
    robust_reasoned = BenchmarkTaskResult(
        task_id="task_strat_b",
        title="Robust Strategy",
        category="evaluation",
        status="COMPLETED",
        correctness=True,
        completion_rate=1.0,
        iterations=1,
        llm_calls=1,
        deterministic_calls=3,
        executor_calls=1,
        total_tokens=4000,
        input_tokens=3000,
        output_tokens=1000,
        wall_clock_time=1.2,
        human_interventions=0,
        failed_attempts=0,
        recovery_success=False,
        safety_violations=0,
        rollback_correctness=True,
        diagnosis_quality=1.0,
        report_accuracy=1.0,
        context_size=3000,
        cache_hit_rate=0.9,
    )

    score_a = broken_cheap.calculate_strategy_score()
    score_b = robust_reasoned.calculate_strategy_score()

    # Strategy B must score significantly higher despite spending more tokens
    assert score_b > score_a
    assert score_b >= 90.0
