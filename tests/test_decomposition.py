"""Tests for Dynamic Task Decomposition (Section 36: Dynamic Task Decomposition)."""

import pytest
from orchestrator.decomposition import TaskDecomposer, ChildTaskSpec, DecompositionPlan


def test_section_36_decomposition_structure():
    """Verify Section 36 structure:
    TASK
    ├── investigate
    ├── implement
    ├── test
    ├── benchmark
    └── review

    Each child gets:
    - objective
    - constraints
    - inputs
    - expected output
    - dependency information
    - budget
    - deadline
    - capabilities
    """
    plan = TaskDecomposer.decompose(
        task_id="task-orch-99",
        goal="Implement Redis distributed lock",
        total_budget=50000,
        deadline_seconds=300.0,
    )

    child_names = [c.name for c in plan.children]
    assert child_names == ["investigate", "implement", "test", "benchmark", "review"]

    for child in plan.children:
        assert child.objective, f"Missing objective for {child.name}"
        assert len(child.constraints) > 0, f"Missing constraints for {child.name}"
        assert isinstance(child.inputs, dict), f"Missing inputs dict for {child.name}"
        assert child.expected_output, f"Missing expected_output for {child.name}"
        assert isinstance(child.dependency_information, list), f"Missing dependency info for {child.name}"
        assert child.budget > 0, f"Missing budget for {child.name}"
        assert child.deadline > 0, f"Missing deadline for {child.name}"
        assert len(child.capabilities) > 0, f"Missing capabilities for {child.name}"

    # Verify dependencies
    implement_child = plan.get_child("implement")
    assert f"{plan.task_id}-investigate" in implement_child.dependency_information

    test_child = plan.get_child("test")
    assert f"{plan.task_id}-implement" in test_child.dependency_information

    review_child = plan.get_child("review")
    assert f"{plan.task_id}-benchmark" in review_child.dependency_information


def test_parent_aggregates_evidence_without_transcripts():
    """Verify Section 36:
    The parent aggregates evidence rather than blindly concatenating transcripts.
    """
    plan = TaskDecomposer.decompose(
        task_id="task-orch-99",
        goal="Implement Redis lock",
    )

    # Simulate verbose executor outputs with raw noisy logs
    raw_investigate = {
        "target_files": ["src/lock.py"],
        "summary": "Lock design ready",
        "verbose_narration": "I am thinking about calling this and that... (1000 lines)",
    }
    raw_implement = {
        "files_changed": ["src/lock.py"],
        "summary": "Added DistributedLock class",
        "diff": "+++ b/src/lock.py\n+class DistributedLock: pass",
        "chat_transcript": "User: hello, Assistant: sure thing...",
    }
    raw_test = {
        "passed": 8,
        "failed": 0,
        "output": "8 passed in 0.2s\nMore raw text...",
    }

    # Aggregate evidence
    TaskDecomposer.aggregate_child_evidence(plan, "investigate", raw_investigate)
    TaskDecomposer.aggregate_child_evidence(plan, "implement", raw_implement)
    TaskDecomposer.aggregate_child_evidence(plan, "test", raw_test)

    evidence = plan.aggregated_evidence

    # Verify evidence contains only compact structured results, NOT raw transcripts
    assert "verbose_narration" not in evidence["investigate"]
    assert evidence["investigate"]["target_files"] == ["src/lock.py"]

    assert "chat_transcript" not in evidence["implement"]
    assert evidence["implement"]["files_changed"] == ["src/lock.py"]

    assert evidence["test"]["passed"] == 8
    assert evidence["test"]["status"] == "PASS"
