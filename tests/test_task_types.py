"""Tests for Explicit Task Types and default workflows (Section 9)."""

import pytest

from orchestrator.state import StateManager, TaskStatus
from orchestrator.task_types import (
    DEFAULT_WORKFLOWS,
    TaskType,
    classify_task_type,
    get_workflow_definition,
)


def test_task_types_enumeration():
    expected_types = [
        "FEATURE", "BUGFIX", "REFACTOR", "RESEARCH",
        "EXPERIMENT", "AUDIT", "VERIFICATION", "MAINTENANCE"
    ]
    for name in expected_types:
        t = TaskType.from_str(name)
        assert t.value == name
        assert t in DEFAULT_WORKFLOWS


def test_classify_task_type():
    assert classify_task_type("Fix critical ZeroDivisionError crash in worker") == TaskType.BUGFIX
    assert classify_task_type("Refactor database query helper to remove duplicates") == TaskType.REFACTOR
    assert classify_task_type("Research state-of-the-art token pruning papers") == TaskType.RESEARCH
    assert classify_task_type("Audit repository for security vulnerabilities") == TaskType.AUDIT
    assert classify_task_type("Run benchmark experiments across models") == TaskType.EXPERIMENT
    assert classify_task_type("Verify all test suites pass") == TaskType.VERIFICATION
    assert classify_task_type("Update dependency locks and housekeeping chores") == TaskType.MAINTENANCE
    assert classify_task_type("Add new user profile settings page") == TaskType.FEATURE


def test_workflow_stages_and_properties():
    # BUGFIX workflow
    wf_bug = get_workflow_definition(TaskType.BUGFIX)
    assert wf_bug.stages == ["reproduce", "implement", "test", "verify"]
    assert wf_bug.read_only_default is False

    # RESEARCH workflow
    wf_res = get_workflow_definition(TaskType.RESEARCH)
    assert "gather_evidence" in wf_res.stages
    assert wf_res.read_only_default is True

    # AUDIT workflow
    wf_audit = get_workflow_definition(TaskType.AUDIT)
    assert wf_audit.stages == ["inspect", "collect_evidence", "report"]
    assert wf_audit.read_only_default is True


def test_state_manager_task_type_integration(tmp_path):
    sm = StateManager(tmp_path)

    # 1. Inferred task type from goal
    st1 = sm.create_task("proj_test", str(tmp_path), "Fix payment webhook crash")
    assert st1.task_type == TaskType.BUGFIX
    assert st1.workflow_stages == ["reproduce", "implement", "test", "verify"]
    assert st1.read_only is False

    # 2. Explicit task type with read-only default
    st2 = sm.create_task("proj_test", str(tmp_path), "Inspect secrets", task_type="AUDIT")
    assert st2.task_type == TaskType.AUDIT
    assert st2.workflow_stages == ["inspect", "collect_evidence", "report"]
    assert st2.read_only is True
