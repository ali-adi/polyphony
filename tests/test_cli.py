"""Tests for CLI commands using click.testing.CliRunner."""

from click.testing import CliRunner
from orchestrator.cli import cli
from orchestrator.state import StateManager, TaskStatus


def test_cli_version_and_help():
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Polyphony: Local-first, multi-agent engineering orchestrator." in result.output

    result_v = runner.invoke(cli, ["--version"])
    assert result_v.exit_code == 0
    assert "0.1.0" in result_v.output


def test_project_list_empty(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list", "--orch-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No projects directory found" in result.output or "No registered projects found" in result.output


def test_project_list_with_project(tmp_path):
    projects_dir = tmp_path / "projects" / "myproject"
    projects_dir.mkdir(parents=True)
    (projects_dir / "project.yaml").write_text(
        "name: myproject\ndescription: Test project\npath: /tmp/myproject\nexecutors:\n  lead: claude\n  primary: agy\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list", "--orch-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "myproject" in result.output
    assert "Test project" in result.output


def test_task_list_and_status(tmp_path):
    mgr = StateManager(root_dir=tmp_path)
    state = mgr.create_task(
        project_name="demo",
        project_path=str(tmp_path / "demo"),
        goal="CLI status test",
        read_only=True,
    )
    mgr.complete_task(state, TaskStatus.COMPLETED, summary="Task finished successfully.")

    runner = CliRunner()
    # List tasks
    list_res = runner.invoke(cli, ["task", "list", "demo", "--orch-root", str(tmp_path)])
    assert list_res.exit_code == 0
    assert state.task_id in list_res.output
    assert "CLI status test" in list_res.output

    # Task status
    status_res = runner.invoke(cli, ["task", "status", "demo", state.task_id, "--orch-root", str(tmp_path)])
    assert status_res.exit_code == 0
    assert state.task_id in status_res.output
    assert "COMPLETED" in status_res.output
    assert "Task finished successfully." in status_res.output


def test_migrate_and_start_help():
    runner = CliRunner()
    res_migrate = runner.invoke(cli, ["migrate", "--help"])
    assert res_migrate.exit_code == 0
    assert "Scan existing repo AI config" in res_migrate.output

    res_start = runner.invoke(cli, ["start", "--help"])
    assert res_start.exit_code == 0
    assert "--max-iterations" in res_start.output
    assert "--lead-model" in res_start.output
    assert "--dry-run" in res_start.output
    assert "--history-window" in res_start.output

    res_resume = runner.invoke(cli, ["resume", "--help"])
    assert res_resume.exit_code == 0
    assert "Resume an existing, paused, or failed task." in res_resume.output


def test_task_status_shows_token_estimates(tmp_path):
    from orchestrator.state import IterationRecord
    from executors.base import ExecutorResult

    mgr = StateManager(root_dir=tmp_path)
    state = mgr.create_task(
        project_name="demo",
        project_path=str(tmp_path / "demo"),
        goal="Token estimate test",
        read_only=True,
    )
    rec = IterationRecord(
        iteration_number=1,
        reasoner_used="claude",
        lead_decision={"action": "VERIFY", "analysis": "Detailed analysis text with 100 characters to test the token counter function!"},
        executor_used="python",
        instruction="pytest -q",
        execution_result=ExecutorResult(executor_name="python", success=True, output="1 passed in 0.01s", exit_code=0),
        safety_passed=True,
    )
    mgr.record_iteration(state, rec)
    mgr.complete_task(state, TaskStatus.COMPLETED, summary="Completed token test")

    runner = CliRunner()
    status_res = runner.invoke(cli, ["task", "status", "demo", state.task_id, "--orch-root", str(tmp_path)])
    assert status_res.exit_code == 0
    assert "Est. Tokens:" in status_res.output
    assert "Tokens:" in status_res.output


def test_config_show_command(tmp_path):
    project_dir = tmp_path / "projects" / "testproj"
    project_dir.mkdir(parents=True)
    (project_dir / "project.yaml").write_text(
        "name: testproj\npath: " + str(tmp_path / "testproj") + "\nexecutors:\n  lead: claude\n  primary: agy\nmodels:\n  lead:\n    claude:\n      model: claude-3-5-sonnet\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    res = runner.invoke(cli, ["config", "show", "testproj", "--orch-root", str(tmp_path)])
    assert res.exit_code == 0
    assert "Resolved Configuration for 'testproj'" in res.output
    assert "Models Hierarchy:" in res.output
    assert "Safety Policies:" in res.output
    assert "claude-3-5-sonnet" in res.output


def test_resume_command_invocation(tmp_path, monkeypatch):
    mgr = StateManager(root_dir=tmp_path)
    proj_dir = tmp_path / "projects" / "demoproj"
    proj_dir.mkdir(parents=True)
    target_code = tmp_path / "demoproj"
    target_code.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        f"name: demoproj\npath: {target_code}\n",
        encoding="utf-8",
    )

    state = mgr.create_task(
        project_name="demoproj",
        project_path=str(target_code),
        goal="Resume test",
        read_only=True,
    )

    resume_called = []
    from orchestrator.main import Orchestrator
    def mock_resume(self, task_id):
        resume_called.append(task_id)
        return state

    monkeypatch.setattr(Orchestrator, "resume_task", mock_resume)

    runner = CliRunner()
    res = runner.invoke(cli, ["resume", "demoproj", state.task_id, "--orch-root", str(tmp_path)])
    assert res.exit_code == 0
    assert resume_called == [state.task_id]


def test_start_command_dry_run(tmp_path, monkeypatch):
    proj_dir = tmp_path / "projects" / "dryproj"
    proj_dir.mkdir(parents=True)
    target_code = tmp_path / "dryproj"
    target_code.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        f"name: dryproj\npath: {target_code}\n",
        encoding="utf-8",
    )

    init_args = {}
    from orchestrator.main import Orchestrator
    original_init = Orchestrator.__init__

    def mock_init(self, *args, **kwargs):
        init_args.update(kwargs)
        original_init(self, *args, **kwargs)

    def mock_run_task(self, goal):
        return None

    monkeypatch.setattr(Orchestrator, "__init__", mock_init)
    monkeypatch.setattr(Orchestrator, "run_task", mock_run_task)

    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["start", "dryproj", "-g", "Check dry run", "--dry-run", "--history-window", "5", "--orch-root", str(tmp_path)],
    )
    assert res.exit_code == 0
    assert init_args.get("dry_run") is True
    assert init_args.get("history_window") == 5

