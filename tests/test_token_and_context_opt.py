"""Tests for Token Optimization and Context Optimization (Sections 13 & 14)."""

import pytest

from orchestrator.tokens import (
    ContextBudgetConfig,
    ContextBudgetManager,
    ContextDeduplicator,
    DiffFirstContextBuilder,
    RelevanceFilter,
    calculate_reasoning_efficiency,
)


def test_calculate_reasoning_efficiency():
    # 1.0 success with 5000 tokens
    eff1 = calculate_reasoning_efficiency(1.0, 5000)
    assert eff1 == 2.0

    # 1.0 success with 20000 tokens (less efficient)
    eff2 = calculate_reasoning_efficiency(1.0, 20000)
    assert eff2 == 0.5
    assert eff1 > eff2

    # Zero tokens spent
    assert calculate_reasoning_efficiency(1.0, 0) == float("inf")


def test_context_budget_manager():
    cfg = ContextBudgetConfig(lead=30000, implementation=20000, research=16000, verification=8000)
    mgr = ContextBudgetManager(cfg)

    assert mgr.get_budget_for_role("lead") == 30000
    assert mgr.get_budget_for_role("implementation") == 20000
    assert mgr.get_budget_for_role("verification") == 8000

    mgr.record_usage("lead", 15000)
    assert mgr.is_within_budget("lead") is True

    mgr.record_usage("lead", 20000)
    assert mgr.is_within_budget("lead") is False


def test_relevance_filter():
    rf = RelevanceFilter()

    # Filter rules
    all_rules = [
        "python_style_pep8",
        "react_components_rule",
        "database_indexing_rule",
        "always_write_tests",
    ]
    matched_rules = rf.filter_rules(all_rules, goal="Fix database query index latency")
    assert "database_indexing_rule" in matched_rules
    assert "always_write_tests" in matched_rules

    # Filter memories
    memories = [
        {"content": "Redis caching was disabled due to memory leak"},
        {"content": "CSS flexbox bug on mobile browsers"},
        {"content": "Database timeout setting must be 30s"},
    ]
    matched_mem = rf.filter_memories(memories, goal="Optimize database query timeout")
    assert len(matched_mem) >= 1
    assert "Database timeout" in matched_mem[0]["content"]


def test_context_deduplicator():
    dedup = ContextDeduplicator()
    blocks = [
        "Rule 1: Always format code.",
        "Rule 2: Run pytest before stopping.",
        "Rule 1: Always format code.",
        "Rule 3: Check git status.",
    ]
    unique = dedup.deduplicate_blocks(blocks)
    assert len(unique) == 3
    assert unique[0] == "Rule 1: Always format code."
    assert unique[1] == "Rule 2: Run pytest before stopping."
    assert unique[2] == "Rule 3: Check git status."


def test_diff_first_context_builder():
    diff = "--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n-old\n+new"
    failure = "AssertionError: token expired"
    remaining = ["Implement refresh token", "Verify with test_auth.py"]

    ctx = DiffFirstContextBuilder.build_iteration_diff_context(
        iteration=2,
        latest_diff=diff,
        last_failure=failure,
        remaining_criteria=remaining,
        budget_limit=5000,
    )

    assert "=== ITERATION 2 DIFF-FIRST CONTEXT ===" in ctx
    assert "## 1. What Changed (Latest Diff):" in ctx
    assert "+new" in ctx
    assert "## 2. What Failed / Current Diagnostics:" in ctx
    assert "AssertionError: token expired" in ctx
    assert "## 3. What Remains to Complete Goal:" in ctx
    assert "- [ ] Implement refresh token" in ctx
