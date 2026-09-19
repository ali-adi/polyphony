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


def test_task_logger_structured_json(tmp_path):
    from orchestrator.logging import TaskLogger

    log_file = tmp_path / "custom_logs" / "test.log"
    logger = TaskLogger(
        "task-json-test",
        log_file=log_file,
        logging_config={"structured_json": True, "level": "DEBUG"},
    )
    logger._write_log("INFO", "Test structured JSON message")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8").strip()
    data = json.loads(content)
    assert data["level"] == "INFO"
    assert data["message"] == "Test structured JSON message"
    assert "timestamp" in data


def test_state_manager_iterations_persistence(tmp_path):
    mgr = StateManager(root_dir=tmp_path)
    state = mgr.create_task(
        project_name="demo",
        project_path=str(tmp_path / "demo"),
        goal="Test iteration persistence",
    )

    rec = IterationRecord(
        iteration_number=1,
        instruction="echo 'hello'",
    )
    mgr.record_iteration(state, rec)

    # Verify state.json does NOT contain full iterations list
    state_file = tmp_path / "tasks" / "demo" / state.task_id / "state.json"
    with open(state_file) as f:
        state_data = json.load(f)
    assert "iterations" not in state_data or state_data["iterations"] == []

    # Verify loading reconstructs iterations from iterations/iteration_01.json
    loaded = mgr.load_state("demo", state.task_id)
    assert len(loaded.iterations) == 1
    assert loaded.iterations[0].instruction == "echo 'hello'"


def test_git_branch_isolation(tmp_path, monkeypatch):
    import subprocess
    target_code = tmp_path / "gitproj"
    target_code.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(target_code), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Polyphony Tester"], cwd=str(target_code), check=True)
    subprocess.run(["git", "config", "user.email", "tester@polyphony.ai"], cwd=str(target_code), check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init commit"], cwd=str(target_code), check=True)

    proj_dir = tmp_path / "projects" / "gitproj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        f"name: gitproj\npath: {target_code}\ngit:\n  isolate_branch: true\nexecutors:\n  lead: python\n",
        encoding="utf-8",
    )

    from orchestrator.main import Orchestrator
    orch = Orchestrator(
        project_name="gitproj",
        root_dir=tmp_path,
        read_only=False,
        max_iterations=1,
    )

    # Lead returns complete immediately
    mock_py = orch.router.get_executor("python")
    monkeypatch.setattr(mock_py, "execute", lambda *args, **kwargs: ExecutorResult(
        executor_name="python",
        success=True,
        output='{"analysis": "All done", "action": "COMPLETE"}',
        exit_code=0,
    ))

    task = orch.run_task(goal="Test branch isolation")
    assert task.status == TaskStatus.COMPLETED

    # Verify branch was created
    res = subprocess.run(["git", "branch", "--show-current"], cwd=str(target_code), capture_output=True, text=True)
    assert res.stdout.strip() == f"polyphony/{task.task_id}"
