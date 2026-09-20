"""Tests for Long-Term Intelligence and Learned Routing (Sections 46 & 47)."""

import pytest
from pathlib import Path

from orchestrator.intelligence import (
    BudgetAllocator,
    ComplexityEstimator,
    ComplexityLevel,
    FailurePredictor,
    HistoricalExperienceStore,
    HistoricalRunRecord,
    LearnedRouter,
    LearnedWorkflowType,
    TaskCharacteristics,
    WorkflowSelector,
)


def test_task_characteristics_extraction():
    # Simple bugfix
    c_simple = TaskCharacteristics.from_task(
        goal="Fix off-by-one error in pagination calculation",
        target_files=["utils/pagination.py"],
        task_type="BUGFIX",
    )
    assert c_simple.file_count == 1
    assert not c_simple.is_ambiguous
    assert not c_simple.touches_critical_paths
    assert not c_simple.is_research_needed

    # Ambiguous research with critical auth paths
    c_complex = TaskCharacteristics.from_task(
        goal="Investigate why maybe auth token validation is failing intermittently",
        target_files=["auth/token_service.py", "auth/keys.py", "db/models.py", "api/routes.py", "middleware/auth.py"],
        task_type="RESEARCH",
    )
    assert c_complex.file_count == 5
    assert c_complex.is_ambiguous
    assert c_complex.touches_critical_paths
    assert c_complex.is_research_needed


def test_complexity_estimator():
    c_simple = TaskCharacteristics(goal="Update readme", file_count=1, task_type="MAINTENANCE")
    assert ComplexityEstimator.estimate(c_simple) == ComplexityLevel.SIMPLE

    c_medium = TaskCharacteristics(goal="Add new filter", file_count=3, task_type="FEATURE")
    assert ComplexityEstimator.estimate(c_medium) == ComplexityLevel.MEDIUM

    c_complex = TaskCharacteristics(goal="Refactor auth", file_count=6, touches_critical_paths=True)
    assert ComplexityEstimator.estimate(c_complex) == ComplexityLevel.COMPLEX


def test_failure_predictor():
    c_safe = TaskCharacteristics(goal="Clean test fixtures", file_count=1, has_clear_criteria=True)
    risk_safe, factors_safe = FailurePredictor.predict_risk(c_safe)
    assert risk_safe < 0.20
    assert len(factors_safe) == 0

    c_risky = TaskCharacteristics(
        goal="Rewrite database engine maybe",
        file_count=8,
        touches_critical_paths=True,
        is_ambiguous=True,
        has_clear_criteria=False,
    )
    risk_high, factors_risky = FailurePredictor.predict_risk(c_risky)
    assert risk_high > 0.70
    assert len(factors_risky) >= 3


def test_budget_allocator():
    simple_direct = BudgetAllocator.predict_budget(ComplexityLevel.SIMPLE, LearnedWorkflowType.DIRECT_EXECUTION)
    complex_multi = BudgetAllocator.predict_budget(ComplexityLevel.COMPLEX, LearnedWorkflowType.MULTI_AGENT)

    assert simple_direct < 15000
    assert complex_multi > 60000
    assert complex_multi > simple_direct * 4


def test_historical_experience_store(tmp_path: Path):
    store_file = tmp_path / "experience.json"
    store = HistoricalExperienceStore(persistence_path=store_file)

    # Verify seeded priors from Section 47
    metrics = store.get_metrics(LearnedWorkflowType.DIRECT_EXECUTION, ComplexityLevel.SIMPLE)
    assert metrics is not None
    assert metrics.sample_count >= 30
    assert metrics.success_rate > 0.90
    assert metrics.median_tokens == 9000

    # Add custom run and verify update
    store.record_run(
        HistoricalRunRecord(
            task_id="test_run_1",
            workflow=LearnedWorkflowType.DAG,
            complexity=ComplexityLevel.COMPLEX,
            success=True,
            safety_violations=0,
            tokens_used=55000,
            latency_seconds=120.0,
            iterations=3,
        )
    )

    dag_metrics = store.get_metrics(LearnedWorkflowType.DAG, ComplexityLevel.COMPLEX)
    assert dag_metrics is not None
    assert dag_metrics.sample_count == 1
    assert dag_metrics.success_rate == 1.0


def test_workflow_selector_and_learned_router():
    router = LearnedRouter()

    # 1. Simple refactor task -> should prefer DIRECT_EXECUTION (high success, low tokens)
    simple_task = TaskCharacteristics.from_task(
        goal="Fix syntax error in helper function",
        target_files=["utils/helpers.py"],
        task_type="BUGFIX",
    )
    decision = router.route(simple_task)
    assert decision.complexity == ComplexityLevel.SIMPLE
    assert decision.selected_workflow in (LearnedWorkflowType.DIRECT_EXECUTION, LearnedWorkflowType.REASON_EXECUTE)
    assert decision.allocated_token_budget <= 20000
    assert "direct_execution" in decision.candidate_scores
    assert len(decision.explanation) > 0

    # 2. Critical security task -> candidate list includes HUMAN_APPROVAL
    critical_task = TaskCharacteristics.from_task(
        goal="Update secret encryption key format in auth system",
        target_files=["auth/crypto.py", "auth/session.py"],
        task_type="FEATURE",
        touches_critical_paths=True,
    )
    decision_crit = router.route(critical_task)
    assert decision_crit.complexity == ComplexityLevel.COMPLEX
    assert "human_approval" in decision_crit.candidate_scores
    assert decision_crit.predicted_failure_risk > 0.2
