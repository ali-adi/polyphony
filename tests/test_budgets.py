"""Tests for Token Budgets and Adaptive Token Allocation (Sections 21 & 22)."""

import pytest
from click.testing import CliRunner
from orchestrator.budgets import (
    AdaptiveBudgetAllocator,
    BudgetHealth,
    TokenBudget,
)
from orchestrator.cli import cli
from orchestrator.task_types import TaskType


def test_token_budget_spending_and_remaining():
    """Verify Section 21:
    budget:
      total_tokens: 50000
      lead: 15000
      execution: 25000
      verification: 5000
      reserve: 5000
    """
    budget = TokenBudget(
        total_tokens=50000,
        lead=15000,
        execution=25000,
        verification=5000,
        reserve=5000,
    )
    assert budget.remaining == 50000

    # Record spends: Planning 8k, Implementation 14k, Verification 3k -> Remaining 25k
    budget.record_spend("lead", 8000)
    budget.record_spend("execution", 14000)
    budget.record_spend("verification", 3000)

    assert budget.remaining == 25000
    breakdown = budget.remaining_breakdown()
    assert breakdown["lead"] == 7000
    assert breakdown["execution"] == 11000
    assert breakdown["verification"] == 2000
    assert breakdown["reserve"] == 5000
    assert breakdown["total_remaining"] == 25000

    status = budget.evaluate_status()
    assert status.health == BudgetHealth.HEALTHY


def test_tight_budget_actions():
    """Verify Section 21:
    When remaining is low (e.g. 6k), Polyphony may:
    - compact context
    - switch executor
    - perform deterministic verification
    - request human input
    - stop
    - use a lower-cost strategy
    """
    budget = TokenBudget(
        total_tokens=50000,
        lead=15000,
        execution=25000,
        verification=5000,
        reserve=5000,
    )
    # Planning 18k, Implementation 21k, Verification 5k -> Remaining 6k
    budget.record_spend("lead", 18000)
    budget.record_spend("execution", 21000)
    budget.record_spend("verification", 5000)

    assert budget.remaining == 6000
    status = budget.evaluate_status()
    assert status.health == BudgetHealth.CRITICAL
    rec = status.recommendations
    assert "compact_context" in rec
    assert "switch_executor" in rec
    assert "perform_deterministic_verification" in rec
    assert "use_lower_cost_strategy" in rec

    # Exhausted budget
    budget.record_spend("execution", 6000)
    assert budget.remaining == 0
    exhausted_status = budget.evaluate_status()
    assert exhausted_status.health == BudgetHealth.EXHAUSTED
    assert "stop" in exhausted_status.recommendations
    assert "request_human_input" in exhausted_status.recommendations


def test_adaptive_allocation_by_complexity_and_type():
    """Verify Section 22:
    Simple bugfix:
    -> small lead budget
    -> larger implementation budget
    -> deterministic verification

    Architecture redesign:
    -> larger lead budget
    -> implementation
    -> independent review
    -> verification

    Reserve some budget for unexpected failures.
    Never spend the entire budget before verification.
    """
    # 1. Simple bugfix
    bugfix_budget = AdaptiveBudgetAllocator.allocate_by_task(
        task_type=TaskType.BUGFIX,
        total_tokens=50000,
    )
    assert bugfix_budget.lead < bugfix_budget.execution
    assert bugfix_budget.reserve > 0
    assert bugfix_budget.verification >= 5000

    # 2. Architecture redesign / Refactor
    refactor_budget = AdaptiveBudgetAllocator.allocate_by_task(
        task_type=TaskType.REFACTOR,
        total_tokens=50000,
    )
    assert refactor_budget.lead > bugfix_budget.lead
    assert refactor_budget.reserve > 0
    assert refactor_budget.verification >= 5000

    # 3. Reallocation preserves verification and reserve
    refactor_budget.record_spend("lead", 5000)
    reallocated = AdaptiveBudgetAllocator.reallocate_remaining(refactor_budget)
    assert reallocated.remaining > 0
    assert reallocated.verification >= 5000


def test_cli_token_budget_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["start", "--help"])
    assert result.exit_code == 0
    assert "--token-budget" in result.output
