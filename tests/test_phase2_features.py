"""Tests for Phase 2 architectural features:
- Underspecified delegation guardrail
- Failure and traceback extraction
- Durable project memory loading and auto-append
- Centralized dirty file snapshotting
- Consecutive error loop circuit breaker
- AgyExecutor command line flags
- Core optimization, benchmarking, and research skills
"""

import json
import os
import time
from pathlib import Path
import pytest
import yaml

from orchestrator.context import (
    compress_execution_output,
    load_project_knowledge,
)
from orchestrator.main import (
    _is_underspecified_delegation,
    Orchestrator,
)
from orchestrator.state import TaskState, IterationRecord, TaskStatus
from executors.base import (
    BaseExecutor,
    ExecutorResult,
    _snapshot_file_states,
    detect_changed_files,
)
from executors.agy_executor import AgyExecutor


def test_is_underspecified_delegation():
    # Vague short instruction delegated to coding agent
    bad_dec = {"action": "DELEGATE", "instruction": "fix bug"}
    is_bad, reason = _is_underspecified_delegation(bad_dec, instruction="fix bug", target_executor="agy")
    assert is_bad is True
    assert "underspecified" in reason.lower()

    # Vague phrase without target_files delegated to cursor
    bad_dec2 = {
        "action": "DELEGATE",
        "instruction": "Please refactor the auth layer to make it cleaner",
    }
    is_bad2, reason2 = _is_underspecified_delegation(
        bad_dec2,
        instruction=bad_dec2["instruction"],
        target_executor="cursor",
    )
    assert is_bad2 is True
    assert "target_files" in reason2.lower()

    # Well-specified delegation with target_files
    good_dec = {
        "action": "DELEGATE",
        "instruction": "Update auth/jwt.py lines 45-80 to use RS256; run pytest tests/test_auth.py",
        "target_files": ["auth/jwt.py"],
    }
    is_bad3, reason3 = _is_underspecified_delegation(
        good_dec,
        instruction=good_dec["instruction"],
        target_executor="agy",
    )
    assert is_bad3 is False
    assert reason3 == ""

    # Non-coding agent (e.g. python executor for tests) is permitted without file scoping
    test_dec = {"action": "DELEGATE", "instruction": "pytest -q"}
    is_bad4, _ = _is_underspecified_delegation(test_dec, instruction="pytest -q", target_executor="python")
    assert is_bad4 is False


def test_compress_execution_output_preserves_tracebacks():
    lines = [f"Normal informational logging line {i}" for i in range(150)]
    lines.append("FAILED tests/test_payment.py::test_stripe_charge - AssertionError: Expected 200 got 500")
    lines.append("Traceback (most recent call last):")
    lines.append('  File "app/payment.py", line 42, in charge')
    lines.append("    raise StripeError('Connection timed out')")
    lines.extend([f"Trailing cleanup log {i}" for i in range(50)])
    raw_output = "\n".join(lines)

    compressed = compress_execution_output(raw_output, max_chars=800)
    assert "FAILED tests/test_payment.py" in compressed
    assert "AssertionError" in compressed
    assert "StripeError" in compressed


def test_durable_project_memory_loading(tmp_path):
    proj_dir = tmp_path / "projects" / "mem_proj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text("name: mem_proj\npath: /tmp/mem\n", encoding="utf-8")
    (proj_dir / "architecture.md").write_text("# Architecture\nLayered microservices.\n", encoding="utf-8")
    (proj_dir / "decisions.md").write_text("# Decisions\nAdopted RS256 for tokens.\n", encoding="utf-8")
    (proj_dir / "known_issues.md").write_text("# Known Issues\nSQLite lock under high concurrency.\n", encoding="utf-8")

    knowledge = load_project_knowledge("mem_proj", tmp_path)
    assert "Layered microservices" in knowledge.get("architecture", "")
    assert "Adopted RS256" in knowledge.get("decisions", "")
    assert "SQLite lock" in knowledge.get("known_issues", "")


def test_durable_memory_auto_append_on_complete(tmp_path):
    proj_dir = tmp_path / "projects" / "append_proj"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(f"name: append_proj\npath: {target_repo}\n", encoding="utf-8")
    decisions_file = proj_dir / "decisions.md"
    decisions_file.write_text("# Decisions\nInitial decision.\n", encoding="utf-8")

    orch = Orchestrator(
        project_name="append_proj",
        root_dir=tmp_path,
        read_only=False,
    )

    class MockLeadExecutor(BaseExecutor):
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
                    "action": "COMPLETE",
                    "analysis": "Task done.",
                    "summary": "Optimized cache lookup.",
                    "learnings": "LRU cache size 1024 provides 4x speedup over 256.",
                }),
                exit_code=0,
            )

    orch.router.executors["claude"] = MockLeadExecutor()
    state = orch.run_task("Benchmark cache size")

    assert state.status == TaskStatus.COMPLETED
    updated_decisions = decisions_file.read_text(encoding="utf-8")
    assert "LRU cache size 1024 provides 4x speedup" in updated_decisions


def test_detect_changed_files_mtime_and_size(tmp_path):
    target_file = tmp_path / "dirty.py"
    target_file.write_text("initial content\n", encoding="utf-8")

    # Snapshot before modification
    snapshot = _snapshot_file_states(str(tmp_path))
    assert "dirty.py" in snapshot

    # Modify file
    time.sleep(0.05)
    target_file.write_text("modified content with extra lines\nand new logic\n", encoding="utf-8")

    # detect_changed_files should find target_file even if git status was already dirty
    changed = detect_changed_files(initial_snapshot=snapshot, cwd=str(tmp_path))
    assert "dirty.py" in changed


def test_consecutive_error_loop_circuit_breaker(tmp_path):
    proj_dir = tmp_path / "projects" / "loop_proj"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(
        f"name: loop_proj\npath: {target_repo}\nexecutors:\n  primary: python\n",
        encoding="utf-8",
    )

    orch = Orchestrator(
        project_name="loop_proj",
        root_dir=tmp_path,
        max_iterations=10,
    )

    class MockFailingLead(BaseExecutor):
        def __init__(self):
            self.invocations = 0

        @property
        def name(self) -> str:
            return "claude"

        def is_available(self) -> bool:
            return True

        def check_quota_status(self) -> tuple[bool, str]:
            return True, "Available"

        def execute(self, *args, **kwargs) -> ExecutorResult:
            self.invocations += 1
            return ExecutorResult(
                executor_name="claude",
                success=True,
                output=json.dumps({
                    "action": "DELEGATE",
                    "executor": "python",
                    "instruction": "pytest -q",
                    "target_files": ["tests/test_x.py"],
                }),
                exit_code=0,
            )

    class MockFailingPython(BaseExecutor):
        @property
        def name(self) -> str:
            return "python"

        def is_available(self) -> bool:
            return True

        def execute(self, *args, **kwargs) -> ExecutorResult:
            return ExecutorResult(
                executor_name="python",
                success=False,
                output="Error: test failed syntax error",
                exit_code=1,
                error="SyntaxError: invalid syntax",
            )

    orch.router.executors["claude"] = MockFailingLead()
    orch.router.executors["python"] = MockFailingPython()

    # Orchestrator should abort after 3 consecutive failures rather than wasting all 10 iterations
    state = orch.run_task("Fix syntax error")
    assert state.status == TaskStatus.FAILED
    assert len(state.iterations) == 3
    assert "3-iteration error loop" in state.error


def test_agy_executor_includes_print_flag(tmp_path, monkeypatch):
    import subprocess

    captured_cmds = []
    class DummyProc:
        returncode = 0
        stdout = '{"response": "done", "session_id": "conv-123"}'
        stderr = ""

    def mock_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return DummyProc()

    monkeypatch.setattr(subprocess, "run", mock_run)

    executor = AgyExecutor()
    res = executor.execute("Implement feature", cwd=str(tmp_path))
    assert res.success is True

    agy_cmds = [c for c in captured_cmds if any("agy" in str(arg) for arg in c)]
    assert len(agy_cmds) >= 1
    agy_cmd = agy_cmds[0]
    # Check that non-interactive -p / --print flag is present
    assert "-p" in agy_cmd or "--print" in agy_cmd
    # Check session extraction
    assert res.metadata.get("session_id") == "conv-123"


def test_core_skills_validity():
    skills_root = Path("skills")
    required_skills = ["optimization", "benchmarking", "research"]

    for sk in required_skills:
        skill_file = skills_root / sk / "SKILL.md"
        assert skill_file.exists(), f"Skill {sk}/SKILL.md missing!"
        content = skill_file.read_text(encoding="utf-8")
        assert content.startswith("---")
        parts = content.split("---", 2)
        assert len(parts) >= 3
        fm = yaml.safe_load(parts[1])
        assert fm.get("name") == sk
        assert "description" in fm


def test_agy_agent_and_json_schema_flags(tmp_path, monkeypatch):
    import subprocess
    captured_cmds = []

    class DummyProc:
        returncode = 0
        stdout = '{"action": "COMPLETE", "analysis": "ok"}'
        stderr = ""

    def mock_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return DummyProc()

    monkeypatch.setattr(subprocess, "run", mock_run)

    executor = AgyExecutor()
    res = executor.execute(
        "Implement feature",
        cwd=str(tmp_path),
        agent="flash-coder",
        json_schema='{"type": "object"}',
    )
    assert res.success is True

    agy_cmds = [c for c in captured_cmds if any("agy" in str(arg) for arg in c)]
    assert len(agy_cmds) >= 1
    agy_cmd = agy_cmds[0]
    assert "--agent" in agy_cmd
    assert agy_cmd[agy_cmd.index("--agent") + 1] == "flash-coder"
    assert "--json-schema" in agy_cmd
    assert agy_cmd[agy_cmd.index("--json-schema") + 1] == '{"type": "object"}'


def test_python_executor_metrics_extraction(tmp_path):
    from executors.python_executor import PythonExecutor

    executor = PythonExecutor()
    # Script outputs JSON with metrics
    script = 'python3 -c "import json; print(json.dumps({\'p50_ms\': 42.5, \'memory_mb\': 12.8}))"'
    res = executor.execute(script, cwd=str(tmp_path))
    assert res.success is True
    assert res.metrics.get("p50_ms") == 42.5
    assert res.metrics.get("memory_mb") == 12.8


def test_orchestrator_metrics_propagation(tmp_path):
    proj_dir = tmp_path / "projects" / "metric_proj"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(
        f"name: metric_proj\npath: {target_repo}\nexecutors:\n  primary: python\n",
        encoding="utf-8",
    )

    orch = Orchestrator(
        project_name="metric_proj",
        root_dir=tmp_path,
        max_iterations=5,
    )

    class MockLead(BaseExecutor):
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
                    "action": "COMPLETE",
                    "analysis": "Benchmark completed successfully.",
                    "metrics": {"candidate_p50_ms": 78.4, "speedup": 1.62},
                }),
                exit_code=0,
            )

    orch.router.executors["claude"] = MockLead()
    state = orch.run_task("Benchmark query throughput")

    assert state.status == TaskStatus.COMPLETED
    assert len(state.iterations) == 1
    assert state.iterations[0].metrics.get("candidate_p50_ms") == 78.4
    assert state.iterations[0].metrics.get("speedup") == 1.62


def test_circuit_breaker_on_repeated_verification_test_failures(tmp_path):
    proj_dir = tmp_path / "projects" / "test_breaker"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(
        f"name: test_breaker\npath: {target_repo}\ntesting:\n  command: pytest\n",
        encoding="utf-8",
    )

    orch = Orchestrator(
        project_name="test_breaker",
        root_dir=tmp_path,
        max_iterations=10,
    )
    orch.safety_config.require_tests_before_stop = True

    class MockPrematureCompleteLead(BaseExecutor):
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
                    "action": "COMPLETE",
                    "analysis": "I think it is all done.",
                }),
                exit_code=0,
            )

    class MockFailingPy(BaseExecutor):
        @property
        def name(self) -> str:
            return "python"

        def is_available(self) -> bool:
            return True

        def execute(self, *args, **kwargs) -> ExecutorResult:
            return ExecutorResult(
                executor_name="python",
                success=False,
                output="",
                error="AssertionError: test failed",
                exit_code=1,
            )

    orch.router.executors["claude"] = MockPrematureCompleteLead()
    orch.router.executors["python"] = MockFailingPy()

    state = orch.run_task("Try completing with broken tests")
    assert state.status == TaskStatus.FAILED
    assert len(state.iterations) == 3
    assert "Verification tests failed 3 consecutive times" in state.error


def test_python_executor_timeout_process_group(tmp_path):
    from executors.python_executor import PythonExecutor

    executor = PythonExecutor()
    start_t = time.time()
    res = executor.execute("python3 -c 'import time; time.sleep(10)'", cwd=str(tmp_path), timeout_seconds=1)
    duration = time.time() - start_t

    assert res.success is False
    assert res.metadata.get("timeout") is True
    assert "timed out" in (res.error or "").lower()
    assert duration < 4.0


def test_resume_task_auto_extends_max_iterations(tmp_path):
    proj_dir = tmp_path / "projects" / "resume_ext"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(
        f"name: resume_ext\npath: {target_repo}\n",
        encoding="utf-8",
    )

    orch = Orchestrator(
        project_name="resume_ext",
        root_dir=tmp_path,
        max_iterations=2,
    )

    class MockLead(BaseExecutor):
        def __init__(self):
            self.count = 0

        @property
        def name(self) -> str:
            return "claude"

        def is_available(self) -> bool:
            return True

        def check_quota_status(self) -> tuple[bool, str]:
            return True, "Available"

        def execute(self, *args, **kwargs) -> ExecutorResult:
            self.count += 1
            if self.count >= 4:
                return ExecutorResult(
                    executor_name="claude",
                    success=True,
                    output=json.dumps({"action": "COMPLETE", "analysis": "Finished on resume"}),
                    exit_code=0,
                )
            return ExecutorResult(
                executor_name="claude",
                success=True,
                output=json.dumps({"action": "VERIFY", "instruction": "python3 -c 'exit(0)'"}),
                exit_code=0,
            )

    lead_mock = MockLead()
    orch.router.executors["claude"] = lead_mock

    # Run initial task which stops at max iterations
    state = orch.run_task("Task to be resumed")
    assert state.status == TaskStatus.FAILED
    assert state.current_iteration >= 2

    # Now resume task with default extension
    orch_resumed = Orchestrator(
        project_name="resume_ext",
        root_dir=tmp_path,
        max_iterations=2,
    )
    orch_resumed.router.executors["claude"] = lead_mock
    resumed_state = orch_resumed.resume_task(state.task_id)

    assert resumed_state.status == TaskStatus.COMPLETED
    assert resumed_state.current_iteration >= 4
    assert resumed_state.max_iterations >= 4


def test_complete_skips_redundant_verification_test(tmp_path):
    proj_dir = tmp_path / "projects" / "redundant_test"
    proj_dir.mkdir(parents=True)
    target_repo = tmp_path / "repo"
    target_repo.mkdir()
    (proj_dir / "project.yaml").write_text(
        f"name: redundant_test\npath: {target_repo}\ntesting:\n  command: pytest -q\n",
        encoding="utf-8",
    )

    orch = Orchestrator(
        project_name="redundant_test",
        root_dir=tmp_path,
        max_iterations=5,
    )
    orch.safety_config.require_tests_before_stop = True

    py_invocations = []
    class MockPy(BaseExecutor):
        @property
        def name(self) -> str:
            return "python"

        def is_available(self) -> bool:
            return True

        def execute(self, instruction, *args, **kwargs) -> ExecutorResult:
            py_invocations.append(instruction)
            return ExecutorResult(
                executor_name="python",
                success=True,
                output="1 passed",
                exit_code=0,
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
            if turn == 1:
                return ExecutorResult(
                    executor_name="claude",
                    success=True,
                    output=json.dumps({"action": "VERIFY", "instruction": "pytest -q"}),
                    exit_code=0,
                )
            else:
                return ExecutorResult(
                    executor_name="claude",
                    success=True,
                    output=json.dumps({"action": "COMPLETE", "analysis": "Done"}),
                    exit_code=0,
                )

    orch.router.executors["claude"] = MockLead()
    orch.router.executors["python"] = MockPy()

    state = orch.run_task("Test redundant verification")
    assert state.status == TaskStatus.COMPLETED
    # Pytest should have been executed exactly once (during iteration 1 VERIFY), NOT twice!
    assert len(py_invocations) == 1


def test_skills_descriptions_loaded_in_system_prompt(tmp_path):
    from orchestrator.context import build_system_prompt

    knowledge = {
        "name": "skills_test",
        "project_skills": ["custom-skill"],
        "global_skills": ["benchmarking"],
        "skill_descriptions": {
            "custom-skill": "Custom domain protocol for parsing",
            "benchmarking": "Run rigorous, variance-controlled benchmarks",
        },
    }

    sys_prompt = build_system_prompt(knowledge, available_executors=["python", "claude"])
    assert "- `custom-skill`: Custom domain protocol for parsing" in sys_prompt
    assert "- `benchmarking`: Run rigorous, variance-controlled benchmarks" in sys_prompt



