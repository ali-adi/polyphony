"""Tests for Cost-Aware Routing & 'Don't Call an LLM' Decisions (Sections 26 & 27)."""

import pytest
from executors.capabilities import Capability
from executors.cost_aware import (
    CostAwareRouter,
    ExecutorProfile,
    RoutingTarget,
)
from executors.router import ExecutorRouter


def test_effective_cost_factors_failure_rate():
    """Verify Section 26:
    'Do not optimize for cheapness alone.
     A cheap executor that fails three times may cost more than a strong executor succeeding once.'
    """
    # Flaky cheap executor: 3000 tokens, 67% failure rate (takes ~3 attempts to succeed)
    flaky_cheap = ExecutorProfile(
        name="flaky",
        capabilities={Capability.CODE_EDITING.value},
        quality_score=0.70,
        latency_seconds=10.0,
        token_expenditure=3000,
        failure_rate=0.67,
    )

    # Reliable executor: 6000 tokens, 0% failure rate
    reliable = ExecutorProfile(
        name="reliable",
        capabilities={Capability.CODE_EDITING.value},
        quality_score=0.98,
        latency_seconds=10.0,
        token_expenditure=6000,
        failure_rate=0.0,
    )

    # Effective cost for flaky cheap executor is higher due to failure risk:
    # 3000 / (1 - 0.67) = ~9090 > 6000
    assert flaky_cheap.effective_cost("medium") > reliable.effective_cost("medium")


def test_cost_aware_router_high_complexity_prefers_quality():
    """Verify Section 26:
    Under high complexity, router weighs quality heavily to avoid compounding failure loops.
    """
    router = CostAwareRouter()
    decision_high = router.route(
        instruction="Refactor whole authentication module to use asymmetric encryption",
        required_capabilities=[Capability.HIGH_REASONING.value],
        task_complexity="high",
    )
    # High reasoning / complexity should pick Claude (highest quality)
    assert decision_high.target == RoutingTarget.CLAUDE
    assert decision_high.expected_quality >= 0.95


def test_dont_call_an_llm_routing_decision():
    """Verify Section 27:
    The router should be able to return DETERMINISTIC instead of CLAUDE, CURSOR, AGY.
    Examples:
    - 'Are all tests passing?' -> pytest
    - 'What files changed?' -> git diff
    - 'How many benchmark cases passed?' -> Python
    - 'Is this task complete according to a simple rule?' -> policy engine
    """
    router = CostAwareRouter()

    # 1. Tests passing
    d1 = router.route("Are all tests passing?")
    assert d1.target == RoutingTarget.DETERMINISTIC
    assert d1.is_deterministic is True
    assert d1.deterministic_tool == "pytest"
    assert d1.expected_cost == 0.0

    # 2. Files changed
    d2 = router.route("What files changed in the last commit?")
    assert d2.target == RoutingTarget.DETERMINISTIC
    assert d2.deterministic_tool == "git_diff"

    # 3. Benchmark cases
    d3 = router.route("How many benchmark cases passed?")
    assert d3.target == RoutingTarget.DETERMINISTIC
    assert d3.deterministic_tool == "python"

    # 4. Simple rule
    d4 = router.route("Is this task complete according to rule?")
    assert d4.target == RoutingTarget.DETERMINISTIC
    assert d4.deterministic_tool == "policy_engine"


def test_router_execute_smart_uses_deterministic_shortcut():
    """Verify integration in ExecutorRouter."""
    router = ExecutorRouter()
    res, used_name = router.execute_smart(
        instruction="What files changed?",
        cwd=".",
    )
    assert used_name == "python"
    assert res.metadata.get("deterministic_shortcut") == "git_diff"
    assert res.metadata.get("tokens_saved") == 5000
