"""Tests for Token Usage Tracking (Section 20: Token Usage Tracking)."""

import pytest
from orchestrator.tokens import TokenUsageTracker, TokenUsageRecord


def test_token_usage_record_fields():
    """Verify Section 20 required fields:
    task, iteration, agent, executor, model, decision, prompt, result.
    """
    rec = TokenUsageRecord(
        task_id="task-101",
        iteration=1,
        agent="lead",
        executor="claude",
        model="claude-3-7-sonnet",
        decision="plan",
        prompt_tokens=18200,
        completion_tokens=3100,
        prompt_snippet="Analyze code and create plan",
        result_snippet="Plan: 1. Refactor, 2. Test",
        is_reasoning_call=True,
    )
    d = rec.to_dict()
    assert d["task_id"] == "task-101"
    assert d["iteration"] == 1
    assert d["agent"] == "lead"
    assert d["executor"] == "claude"
    assert d["model"] == "claude-3-7-sonnet"
    assert d["decision"] == "plan"
    assert d["prompt_tokens"] == 18200
    assert d["completion_tokens"] == 3100
    assert d["total_tokens"] == 21300


def test_token_usage_tracker_summary():
    """Verify exact Section 20 YAML structure:
    usage:
      lead:
        input_tokens: 18200
        output_tokens: 3100
      executors:
        cursor:
          input_tokens: 12000
          output_tokens: 2100
      total:
        input: 30200
        output: 5200
    """
    tracker = TokenUsageTracker()

    # 1. Lead record
    tracker.record(
        task_id="task-001",
        iteration=1,
        agent="lead",
        executor="claude",
        model="claude-3-7-sonnet",
        decision="plan",
        prompt_tokens=18200,
        completion_tokens=3100,
        is_reasoning_call=True,
        context_size=18200,
        cache_hit=False,
    )

    # 2. Executor record (cursor)
    tracker.record(
        task_id="task-001",
        iteration=1,
        agent="implementer",
        executor="cursor",
        model="claude-3-5-sonnet",
        decision="code",
        prompt_tokens=12000,
        completion_tokens=2100,
        is_executor_call=True,
        context_size=12000,
        cache_hit=True,
    )

    tracker.mark_task_success("task-001")

    summary = tracker.get_summary()
    usage = summary["usage"]
    metrics = summary["metrics"]

    # Check usage numbers matching Section 20 spec
    assert usage["lead"]["input_tokens"] == 18200
    assert usage["lead"]["output_tokens"] == 3100
    assert usage["executors"]["cursor"]["input_tokens"] == 12000
    assert usage["executors"]["cursor"]["output_tokens"] == 2100
    assert usage["total"]["input"] == 30200
    assert usage["total"]["output"] == 5200
    assert usage["total"]["tokens"] == 35400

    # Check metrics
    assert metrics["llm_calls"] == 2
    assert metrics["executor_calls"] == 1
    assert metrics["reasoning_calls"] == 1
    assert metrics["tokens_per_iteration"][1] == 35400
    assert metrics["tokens_per_successful_task"] == 35400.0
    assert metrics["average_context_size"] == 15100.0
    assert metrics["cache_hit_rate"] == 0.5
    assert metrics["context_reuse"] == 1


def test_token_usage_breakdowns():
    tracker = TokenUsageTracker()
    tracker.record(
        task_id="task-a",
        iteration=1,
        agent="researcher",
        executor="claude",
        model="claude-3-5-sonnet",
        decision="search",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    tracker.record(
        task_id="task-b",
        iteration=1,
        agent="verifier",
        executor="python",
        model="deterministic",
        decision="verify",
        prompt_tokens=200,
        completion_tokens=50,
    )

    by_task = tracker.usage_by_task("task-a")
    assert by_task["input_tokens"] == 1000
    assert by_task["total"] == 1500

    by_agent = tracker.usage_by_agent("verifier")
    assert by_agent["total"] == 250

    by_model = tracker.usage_by_model("claude-3-5-sonnet")
    assert by_model["total"] == 1500

    by_decision = tracker.usage_by_decision("search")
    assert by_decision["total"] == 1500
