"""Tests for Phase 3 architectural improvements:
- Lazy agent zero-change completion guardrail
- One-time delegation context header per session
- Failure classification engine
- Passing test output normalization
- ASK_HUMAN action & NEEDS_HUMAN status
- Task retry with human feedback CLI
"""

import json
from pathlib import Path
from click.testing import CliRunner
import pytest

from orchestrator.cli import cli
from orchestrator.context import classify_failure, compress_execution_output
from orchestrator.main import Orchestrator
from orchestrator.state import StateManager, TaskState, TaskStatus, IterationRecord
from executors.base import BaseExecutor, ExecutorResult


def test_classify_failure():
    assert classify_failure("SyntaxError: unexpected EOF while parsing") == "SYNTAX_ERROR"
    assert classify_failure("AssertionError: Expected 200 got 500") == "TEST_BUG"
    assert classify_failure("FAILED tests/test_api.py::test_login") == "TEST_BUG"
    assert classify_failure("ModuleNotFoundError: No module named 'jwt'") == "ENVIRONMENT"
    assert classify_failure("zsh: command not found: pytest") == "ENVIRONMENT"
    assert classify_failure("Command timed out after 300s", exit_code=124) == "TIMEOUT"
    assert classify_failure("Permission denied: /var/log/sys.log", exit_code=126) == "PERMISSION"
    assert classify_failure("Anthropic API rate limit exceeded") == "INFRASTRUCTURE"
    assert classify_failure("KeyError: 'user_id'") == "CODE_BUG"


def test_compress_execution_output_normalizes_passed_tests():
    # Long passing pytest output with 200 dots
    raw_passed = (
        "tests/test_one.py " + "." * 100 + "\n"
        "tests/test_two.py " + "." * 100 + "\n"
        "============================== 200 passed in 1.45s =============================="
    )
    res = compress_execution_output(raw_passed)
    assert "[Test Suite Passed:" in res
    assert "200 passed in 1.45s" in res


def test_lazy_agent_zero_change_interception(tmp_path):
    proj_dir = tmp_path / "projects" / "lazy_proj"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(f"name: lazy_proj\npath: {target_repo}\n", encoding="utf-8")

    orch = Orchestrator(
        project_name="lazy_proj",
        root_dir=tmp_path,
        max_iterations=3,
    )

    turn = 0
    class MockLazyLead(BaseExecutor):
        @property
        def name(self) -> str:
            return "claude"

        def is_available(self) -> bool:
            return True

        def check_quota_status(self) -> tuple[bool, str]:
            return True, "Available"

        def execute(self, *args, **kwargs) -> ExecutorResult:
            nonlocal turn
            turn += 1
            if turn == 1:
                # Premature complete with 0 files modified on a "fix" goal
                return ExecutorResult(
                    executor_name="claude",
                    success=True,
                    output=json.dumps({"action": "COMPLETE", "analysis": "I am done without editing files"}),
                    exit_code=0,
                )
            else:
                # Responding to interception with allow_zero_changes
                return ExecutorResult(
                    executor_name="claude",
                    success=True,
                    output=json.dumps({
                        "action": "COMPLETE",
                        "analysis": "Verified bug was already resolved in upstream.",
                        "allow_zero_changes": True,
                    }),
                    exit_code=0,
                )

    orch.router.executors["claude"] = MockLazyLead()
    state = orch.run_task("Fix the critical auth deadlock")

    # Turn 1 should be intercepted as safety violation
    assert len(state.iterations) >= 2
    assert state.iterations[0].safety_passed is False
    assert "Completion rejected: The goal indicates code modifications" in state.iterations[0].safety_message
    # Turn 2 should succeed with allow_zero_changes
    assert state.status == TaskStatus.COMPLETED


def test_one_time_delegation_context_header(tmp_path):
    proj_dir = tmp_path / "projects" / "header_proj"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(f"name: header_proj\npath: {target_repo}\n", encoding="utf-8")
    (proj_dir / "conventions.md").write_text("Use PEP 8 everywhere.", encoding="utf-8")

    orch = Orchestrator(
        project_name="header_proj",
        root_dir=tmp_path,
        max_iterations=3,
    )

    received_instructions = []
    class MockWorker(BaseExecutor):
        @property
        def name(self) -> str:
            return "cursor"

        def is_available(self) -> bool:
            return True

        def execute(self, instruction, *args, **kwargs) -> ExecutorResult:
            received_instructions.append(instruction)
            return ExecutorResult(
                executor_name="cursor",
                success=True,
                output="applied change",
                files_changed=["app.py"],
                metadata={"session_id": "sess-abc"},
            )

    turn = 0
    class MockLead(BaseExecutor):
        @property
        def name(self) -> str:
            return "claude"

        def is_available(self) -> bool:
            return True

        def check_quota_status(self) -> tuple[bool, str]:
            return True, "Available"

        def execute(self, *args, **kwargs) -> ExecutorResult:
            nonlocal turn
            turn += 1
            if turn <= 2:
                return ExecutorResult(
                    executor_name="claude",
                    success=True,
                    output=json.dumps({
                        "action": "DELEGATE",
                        "executor": "cursor",
                        "target_files": ["app.py"],
                        "instruction": f"Step {turn} in app.py",
                    }),
                    exit_code=0,
                )
            return ExecutorResult(
                executor_name="claude",
                success=True,
                output=json.dumps({"action": "COMPLETE", "analysis": "Done"}),
                exit_code=0,
            )

    orch.router.executors["claude"] = MockLead()
    orch.router.executors["cursor"] = MockWorker()

    state = orch.run_task("Multi-turn delegation")
    assert state.status == TaskStatus.COMPLETED
    assert len(received_instructions) == 2

    # First turn must have context header
    assert "[Project Context: header_proj]" in received_instructions[0]
    # Second turn to existing session must NOT repeat context header
    assert "[Project Context: header_proj]" not in received_instructions[1]
    assert received_instructions[1] == "Step 2 in app.py"


def test_ask_human_action_non_interactive(tmp_path):
    proj_dir = tmp_path / "projects" / "human_proj"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(f"name: human_proj\npath: {target_repo}\n", encoding="utf-8")

    orch = Orchestrator(
        project_name="human_proj",
        root_dir=tmp_path,
        max_iterations=3,
    )

    class MockAskingLead(BaseExecutor):
        @property
        def name(self) -> str:
            return "claude"

        def is_available(self) -> bool:
            return True

        def check_quota_status(self) -> tuple[bool, str]:
            return True, "Available"

        def execute(self, *args, **kwargs) -> ExecutorResult:
            return ExecutorResult(
                executor_name="claude",
                success=True,
                output=json.dumps({
                    "action": "ASK_HUMAN",
                    "question": "Which database dialect should we use?",
                }),
                exit_code=0,
            )

    orch.router.executors["claude"] = MockAskingLead()
    state = orch.run_task("Setup database")

    # In automated non-interactive testing, transitions cleanly to NEEDS_HUMAN
    assert state.status == TaskStatus.NEEDS_HUMAN
    assert "Which database dialect" in state.final_summary


def test_task_retry_cli(tmp_path, monkeypatch):
    repo_dir = tmp_path / "retryproj"
    repo_dir.mkdir()
    proj_dir = tmp_path / "projects" / "retryproj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(f"name: retryproj\npath: {repo_dir}\n", encoding="utf-8")

    mgr = StateManager(root_dir=tmp_path)
    state = mgr.create_task(
        project_name="retryproj",
        project_path=str(repo_dir),
        goal="Retry test",
    )
    mgr.complete_task(state, TaskStatus.FAILED, error="Syntax failure")

    # Mock resume_task
    resumed_args = {}
    from orchestrator.main import Orchestrator
    def mock_resume(self, task_id, extra_iterations=None):
        resumed_args["task_id"] = task_id
        resumed_args["extra_iterations"] = extra_iterations
        return None

    monkeypatch.setattr(Orchestrator, "resume_task", mock_resume)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["task", "retry", "retryproj", state.task_id, "-f", "Use PostgreSQL dialect instead", "--orch-root", str(tmp_path)],
    )
    assert res.exit_code == 0

    reloaded = mgr.load_state("retryproj", state.task_id)
    assert reloaded.status == TaskStatus.RUNNING
    assert len(reloaded.iterations) == 1
    assert "Use PostgreSQL dialect" in reloaded.iterations[0].instruction
    assert resumed_args.get("task_id") == state.task_id
