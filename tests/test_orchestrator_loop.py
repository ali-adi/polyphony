"""End-to-end unit tests for Orchestrator.run_task() ReAct loop."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from executors.base import BaseExecutor, ExecutorResult
from orchestrator.main import Orchestrator
from orchestrator.state import TaskStatus


class MockLeadExecutor(BaseExecutor):
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.invocations = 0

    @property
    def name(self) -> str:
        return "claude"

    def is_available(self) -> bool:
        return True

    def check_quota_status(self) -> tuple[bool, str]:
        return True, "Available"

    def execute(self, instruction: str, cwd: str, **kwargs) -> ExecutorResult:
        self.invocations += 1
        if self._responses:
            resp = self._responses.pop(0)
            return ExecutorResult(
                success=True,
                executor_name=self.name,
                output=resp,
                exit_code=0,
            )
        return ExecutorResult(
            success=True,
            executor_name=self.name,
            output='{"action": "COMPLETE", "analysis": "Done"}',
            exit_code=0,
        )


def _setup_mock_project(tmp_path: Path, name: str = "demo") -> Path:
    proj_dir = tmp_path / "projects" / name
    proj_dir.mkdir(parents=True, exist_ok=True)
    target_dir = tmp_path / name
    target_dir.mkdir(parents=True, exist_ok=True)

    (proj_dir / "project.yaml").write_text(
        f"""name: {name}
path: {target_dir}
description: Mock project for loop tests
executors:
  lead: claude
  primary: agy
safety:
  protected_paths:
    - database/
  blocked_commands:
    - git push
testing:
  command: python -c 'exit(0)'
""",
        encoding="utf-8",
    )
    return target_dir


def test_orchestrator_loop_delegate_and_complete(tmp_path):
    target_dir = _setup_mock_project(tmp_path)

    # 1st response: DELEGATE to python to echo
    # 2nd response: COMPLETE
    responses = [
        json.dumps({
            "action": "DELEGATE",
            "executor": "python",
            "instruction": "echo 'running delegation'",
            "analysis": "Need to run inspection first",
            "verification_needed": False,
        }),
        json.dumps({
            "action": "COMPLETE",
            "analysis": "Task accomplished successfully.",
        }),
    ]
    mock_lead = MockLeadExecutor(responses)

    orch = Orchestrator(project_name="demo", root_dir=str(tmp_path), preferred_lead="claude")
    orch.router.executors["claude"] = mock_lead

    task_state = orch.run_task("Complete delegation test")

    assert task_state.status == TaskStatus.COMPLETED
    assert len(task_state.iterations) == 2
    assert task_state.iterations[0].lead_decision["action"] == "DELEGATE"
    assert task_state.iterations[0].executor_used == "python"
    assert task_state.iterations[1].lead_decision["action"] == "COMPLETE"
    assert task_state.final_summary == "Task accomplished successfully."


def test_orchestrator_loop_abort(tmp_path):
    _setup_mock_project(tmp_path)

    responses = [
        json.dumps({
            "action": "ABORT",
            "analysis": "Requirements are conflicting; aborting.",
        }),
    ]
    mock_lead = MockLeadExecutor(responses)

    orch = Orchestrator(project_name="demo", root_dir=str(tmp_path), preferred_lead="claude")
    orch.router.executors["claude"] = mock_lead

    task_state = orch.run_task("Conflicting requirements")

    assert task_state.status == TaskStatus.ABORTED
    assert len(task_state.iterations) == 1
    assert "conflicting" in task_state.error.lower()


def test_orchestrator_loop_safety_command_blocking(tmp_path):
    _setup_mock_project(tmp_path)

    # 1st response tries dangerous git push -> safety blocks
    # 2nd response pivots to safe complete
    responses = [
        json.dumps({
            "action": "DELEGATE",
            "executor": "python",
            "instruction": "git push origin main",
            "analysis": "Pushing changes",
        }),
        json.dumps({
            "action": "COMPLETE",
            "analysis": "Pivoted and finished without push.",
        }),
    ]
    mock_lead = MockLeadExecutor(responses)

    orch = Orchestrator(project_name="demo", root_dir=str(tmp_path), preferred_lead="claude")
    orch.router.executors["claude"] = mock_lead

    task_state = orch.run_task("Test safety blocking")

    assert len(task_state.iterations) == 2
    assert task_state.iterations[0].safety_passed is False
    assert "Blocked by safety policy" in task_state.iterations[0].safety_message
    assert task_state.status == TaskStatus.COMPLETED


def test_orchestrator_parse_retry(tmp_path):
    _setup_mock_project(tmp_path)

    # 1st response: malformed output
    # 2nd response: valid JSON returned on retry
    responses = [
        "I am not giving you JSON yet, sorry.",
        json.dumps({
            "action": "COMPLETE",
            "analysis": "Fixed format and completed.",
        }),
    ]
    mock_lead = MockLeadExecutor(responses)

    orch = Orchestrator(project_name="demo", root_dir=str(tmp_path), preferred_lead="claude")
    orch.router.executors["claude"] = mock_lead

    task_state = orch.run_task("Test parse retry")

    assert task_state.status == TaskStatus.COMPLETED
    assert task_state.final_summary == "Fixed format and completed."


def test_orchestrator_midtask_lead_failover(tmp_path):
    _setup_mock_project(tmp_path)

    # Claude fails with quota exceeded on execution
    class QuotaFailingLead(BaseExecutor):
        @property
        def name(self) -> str:
            return "claude"

        def is_available(self) -> bool:
            return True

        def execute(self, instruction: str, cwd: str, **kwargs) -> ExecutorResult:
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error="weekly limit exceeded",
                exit_code=1,
                metadata={"quota_exceeded": True},
            )

    # AGY succeeds as fallback
    class WorkingAgyLead(BaseExecutor):
        @property
        def name(self) -> str:
            return "agy"

        def is_available(self) -> bool:
            return True

        def execute(self, instruction: str, cwd: str, **kwargs) -> ExecutorResult:
            return ExecutorResult(
                success=True,
                executor_name=self.name,
                output=json.dumps({"action": "COMPLETE", "analysis": "Completed via AGY failover"}),
                exit_code=0,
            )

    orch = Orchestrator(project_name="demo", root_dir=str(tmp_path), preferred_lead="claude")
    orch.router.executors["claude"] = QuotaFailingLead()
    orch.router.executors["agy"] = WorkingAgyLead()

    task_state = orch.run_task("Test lead failover")

    assert task_state.status == TaskStatus.COMPLETED
    assert "Completed via AGY failover" in task_state.final_summary
