"""Tests for Developer UX CLI commands and JSON output ergonomics (Section 48)."""

import json
from pathlib import Path
from click.testing import CliRunner

from orchestrator.cli import cli
from orchestrator.state import StateManager, TaskStatus


def setup_test_project_and_task(tmp_path: Path):
    state_mgr = StateManager(tmp_path)
    task = state_mgr.create_task(
        project_name="demo_proj",
        project_path=str(tmp_path / "demo_proj"),
        goal="Improve authentication token caching",
    )
    task.total_tokens = 12500
    task.total_cost_usd = 0.0375
    task.detailed_usage = {"input_tokens": 10000, "output_tokens": 2500}
    task.all_files_changed = ["auth/token.py"]
    state_mgr.save_state(task)
    return task


def test_cli_status_and_json(tmp_path: Path):
    task = setup_test_project_and_task(tmp_path)
    runner = CliRunner()

    # 1. Global status listing --json
    result = runner.invoke(cli, ["status", "--root", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["task_id"] == task.task_id

    # 2. Specific task status --json
    result_task = runner.invoke(cli, ["status", task.task_id, "--root", str(tmp_path), "--json"])
    assert result_task.exit_code == 0
    task_data = json.loads(result_task.output)
    assert task_data["task_id"] == task.task_id
    assert task_data["status"] == "pending"


def test_cli_inspect_command(tmp_path: Path):
    task = setup_test_project_and_task(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["inspect", task.task_id, "--root", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["task_id"] == task.task_id
    assert data["total_tokens"] == 12500
    assert "auth/token.py" in data["all_files_changed"]


def test_cli_pause_and_cancel(tmp_path: Path):
    task = setup_test_project_and_task(tmp_path)
    runner = CliRunner()

    # Pause
    res_pause = runner.invoke(cli, ["pause", task.task_id, "--root", str(tmp_path), "--json"])
    assert res_pause.exit_code == 0
    pause_data = json.loads(res_pause.output)
    assert pause_data["status"] == "paused"

    # Cancel
    res_cancel = runner.invoke(cli, ["cancel", task.task_id, "--reason", "Not needed anymore", "--root", str(tmp_path), "--json"])
    assert res_cancel.exit_code == 0
    cancel_data = json.loads(res_cancel.output)
    assert cancel_data["status"] == "cancelled"


def test_cli_approve_and_reject(tmp_path: Path):
    task = setup_test_project_and_task(tmp_path)
    state_mgr = StateManager(tmp_path)
    task.pending_approval = {"action": "alter infrastructure", "risk": "HIGH"}
    task.status = TaskStatus.NEEDS_HUMAN
    state_mgr.save_state(task)

    runner = CliRunner()

    # Approve
    res_approve = runner.invoke(cli, ["approve", task.task_id, "--notes", "Verified safe", "--root", str(tmp_path), "--json"])
    assert res_approve.exit_code == 0
    app_data = json.loads(res_approve.output)
    assert app_data["approved"] is True

    # Check updated state
    reloaded = state_mgr.load_state("demo_proj", task.task_id)
    assert reloaded.status == TaskStatus.RUNNING
    assert len(reloaded.approval_history) == 1
    assert reloaded.approval_history[0]["decision"] == "APPROVED"

    # Reject another request
    reloaded.pending_approval = {"action": "drop database", "risk": "CRITICAL"}
    state_mgr.save_state(reloaded)

    res_reject = runner.invoke(cli, ["reject", task.task_id, "--reason", "Unsafe drop", "--root", str(tmp_path), "--json"])
    assert res_reject.exit_code == 0
    rej_data = json.loads(res_reject.output)
    assert rej_data["approved"] is False

    reloaded_after_rej = state_mgr.load_state("demo_proj", task.task_id)
    assert reloaded_after_rej.status == TaskStatus.BLOCKED


def test_cli_metrics_and_export(tmp_path: Path):
    task = setup_test_project_and_task(tmp_path)
    runner = CliRunner()

    # Metrics
    res_metrics = runner.invoke(cli, ["metrics", task.task_id, "--root", str(tmp_path), "--json"])
    assert res_metrics.exit_code == 0
    m_data = json.loads(res_metrics.output)
    assert m_data["total_tokens"] == 12500
    assert m_data["total_cost_usd"] == 0.0375

    # Export
    out_dir = tmp_path / "exports"
    res_export = runner.invoke(cli, ["export", task.task_id, "--output", str(out_dir), "--root", str(tmp_path), "--json"])
    assert res_export.exit_code == 0
    exp_data = json.loads(res_export.output)
    assert "bundle_path" in exp_data
    assert Path(exp_data["bundle_path"]).exists()
