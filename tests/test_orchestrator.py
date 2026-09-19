"""Tests for core orchestrator, state management, and reporting."""

import json
from pathlib import Path
import pytest

from orchestrator.state import StateManager, TaskState, IterationRecord, TaskStatus
from orchestrator.context import build_reasoning_prompt, parse_reasoner_decision, load_project_knowledge
from orchestrator.report import generate_task_report
from executors.base import ExecutorResult


def test_state_manager(tmp_path):
    mgr = StateManager(root_dir=tmp_path)
    state = mgr.create_task(
        project_name="demo",
        project_path=str(tmp_path / "demo"),
        goal="Test goal",
        read_only=True,
        max_iterations=5,
    )

    assert state.task_id.startswith("task-")
    assert state.status == TaskStatus.PENDING

    # Record iteration
    rec = IterationRecord(
        iteration_number=1,
        reasoner_used="claude",
        lead_decision={"action": "DELEGATE", "executor": "agy", "instruction": "Inspect files"},
        executor_used="agy",
        instruction="Inspect files",
        execution_result=ExecutorResult(
            success=True,
            executor_name="agy",
            output="Files inspected",
        ),
        files_changed=["README.md"],
    )
    mgr.record_iteration(state, rec)

    assert state.current_iteration == 1
    assert "README.md" in state.all_files_changed

    # Complete task
    mgr.complete_task(state, TaskStatus.COMPLETED, summary="Goal accomplished.")
    assert state.status == TaskStatus.COMPLETED
    assert state.end_time is not None

    # Load back
    loaded = mgr.load_state("demo", state.task_id)
    assert loaded is not None
    assert loaded.status == TaskStatus.COMPLETED
    assert loaded.final_summary == "Goal accomplished."
    assert len(loaded.iterations) == 1


def test_context_and_decision_parsing():
    valid_json = '{"analysis": "All done", "action": "COMPLETE", "executor": "python", "instruction": "", "success_criteria": [], "verification_needed": false}'
    decision = parse_reasoner_decision(valid_json)
    assert decision["action"] == "COMPLETE"
    assert decision["analysis"] == "All done"

    # Markdown wrapped json
    markdown_json = '```json\n{"analysis": "Delegating", "action": "DELEGATE", "executor": "agy", "instruction": "run check"}\n```'
    decision2 = parse_reasoner_decision(markdown_json)
    assert decision2["action"] == "DELEGATE"
    assert decision2["executor"] == "agy"


def test_report_generation(tmp_path):
    state = TaskState(
        task_id="task-12345",
        project_name="demo",
        project_path="/path/to/demo",
        goal="Test task report generation",
        read_only=True,
        status=TaskStatus.COMPLETED,
        final_summary="All checks passed.",
    )
    rec = IterationRecord(
        iteration_number=1,
        lead_decision={"action": "COMPLETE", "analysis": "Done"},
        reasoner_used="claude",
        instruction="None",
        tests_passed=True,
    )
    state.iterations.append(rec)

    dest = tmp_path / "report.md"
    report_text = generate_task_report(state, dest)

    assert dest.exists()
    assert "# Task Report: Test task report generation" in report_text
    assert "All checks passed." in report_text
    assert "Iteration 1" in report_text
