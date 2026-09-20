"""Tests for polyphony task explain subsystem (Section 12)."""

from click.testing import CliRunner
import pytest

from executors.base import ExecutorResult
from orchestrator.cli import cli
from orchestrator.explain import TaskExplainer, TaskExplanation
from orchestrator.state import IterationRecord, StateManager, TaskStatus


def test_task_explain_comprehensive(tmp_path):
    sm = StateManager(tmp_path)
    state = sm.create_task("proj_test", str(tmp_path), "Fix authentication timeout")

    # Iteration 1: Delegate to cursor, test failure
    rec1 = IterationRecord(
        iteration_number=1,
        reasoner_used="claude",
        lead_decision={"action": "DELEGATE", "executor": "cursor", "analysis": "Delegate auth timeout fix to cursor."},
        executor_used="cursor",
        instruction="Fix timeout in auth.py",
        execution_result=ExecutorResult(executor_name="cursor", success=True, output="Edited auth.py", files_changed=["auth.py"]),
        tests_passed=False,
        test_output="AssertionError: timeout still occurs",
        files_changed=["auth.py"],
    )
    sm.record_iteration(state, rec1)

    # Iteration 2: Complete
    rec2 = IterationRecord(
        iteration_number=2,
        reasoner_used="claude",
        lead_decision={"action": "COMPLETE", "analysis": "All tests pass after config bump."},
        executor_used="claude",
        tests_passed=True,
        files_changed=["auth.py", "config.py"],
    )
    sm.record_iteration(state, rec2)
    state.total_tokens = 8400
    state.total_cost_usd = 0.042
    sm.complete_task(state, status=TaskStatus.COMPLETED, summary="Auth timeout fixed and tests passing.")

    # Run explain
    explainer = TaskExplainer(root_dir=tmp_path)
    exp = explainer.explain(state.task_id)

    assert isinstance(exp, TaskExplanation)
    assert exp.task_id == state.task_id
    assert exp.status == "completed"

    # Verify answers to the 9 questions
    # 1. Executor selection
    assert any("cursor" in r for r in exp.executor_selection_reasons)
    # 2. Lead actions
    assert any("DELEGATE" in r for r in exp.lead_action_reasons)
    # 3. Iteration rationale
    assert len(exp.iteration_reasons) >= 1
    # 4. Stopping rationale
    assert "Auth timeout fixed" in exp.stopping_rationale
    # 5. Blocked
    assert exp.blocked_rationale is None
    # 6. Human
    assert exp.human_escalation_rationale is None
    # 7. Evidence
    assert "auth.py" in exp.completion_evidence["files_changed"]
    assert exp.completion_evidence["tests_passed"] is True
    # 8. Tokens & cost
    assert exp.tokens_and_cost["total_tokens"] == 8400
    assert exp.tokens_and_cost["total_cost_usd"] == 0.042
    # 9. Failures
    assert len(exp.failures_encountered) == 1
    assert exp.failures_encountered[0]["type"] == "TEST_FAILURE"

    # CLI format
    cli_out = exp.format_cli()
    assert "1. Why was each executor selected?" in cli_out
    assert "9. Where did failures occur?" in cli_out


def test_task_explain_cli(tmp_path):
    sm = StateManager(tmp_path)
    state = sm.create_task("proj_test", str(tmp_path), "Explainable Task")
    sm.complete_task(state, status=TaskStatus.COMPLETED, summary="Done")

    runner = CliRunner()
    # Test task explain subcommand
    res1 = runner.invoke(cli, ["task", "explain", state.task_id, "--orch-root", str(tmp_path)])
    assert res1.exit_code == 0
    assert f"=== Explanation for Task: {state.task_id} ===" in res1.output

    # Test top-level explain alias
    res2 = runner.invoke(cli, ["explain", state.task_id, "--root", str(tmp_path)])
    assert res2.exit_code == 0
    assert f"=== Explanation for Task: {state.task_id} ===" in res2.output
