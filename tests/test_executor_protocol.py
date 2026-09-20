"""Tests for formalized Executor Protocol conforming to Section 6."""

from pathlib import Path
import pytest

from executors.base import BaseExecutor, ExecutorResult, ExecutorStatus
from executors.claude_executor import ClaudeExecutor
from executors.agy_executor import AgyExecutor
from executors.cursor_executor import CursorExecutor
from executors.python_executor import PythonExecutor


def test_executor_protocol_capabilities():
    claude = ClaudeExecutor()
    assert "high_reasoning" in claude.capabilities()
    assert "code_editing" in claude.capabilities()

    agy = AgyExecutor()
    assert "fast_reasoning" in agy.capabilities()
    assert "web_research" in agy.capabilities()

    cursor = CursorExecutor()
    assert "code_editing" in cursor.capabilities()

    python_ex = PythonExecutor()
    assert "deterministic_computation" in python_ex.capabilities()
    assert "test_execution" in python_ex.capabilities()


def test_executor_protocol_health():
    claude = ClaudeExecutor()
    h = claude.health()
    assert "status" in h
    assert "available" in h

    python_ex = PythonExecutor()
    py_h = python_ex.health()
    assert py_h["status"] == "OK"
    assert py_h["available"] is True


def test_executor_protocol_lifecycle(tmp_path):
    python_ex = PythonExecutor()

    # 1. start
    handle = python_ex.start("echo 'protocol test'", cwd=str(tmp_path))
    assert handle.startswith("python-")

    # 2. poll
    poll_info = python_ex.poll(handle)
    assert poll_info["completed"] is True
    assert poll_info["status"] == "COMPLETED"

    # 3. send (noop on finished handle, but accepted)
    python_ex.send(handle, "additional input")

    # 4. collect
    res = python_ex.collect(handle)
    assert isinstance(res, ExecutorResult)
    assert res.success is True
    assert res.status == ExecutorStatus.SUCCESS
    assert "protocol test" in res.output
    assert res.summary != ""
    assert res.confidence == 1.0


def test_executor_result_normalized_schema():
    # Schema test
    res = ExecutorResult(
        executor_name="test_engine",
        status=ExecutorStatus.SUCCESS,
        summary="Fixed normalization bugs",
        files_changed=["a.py", "b.py"],
        tests={"passed": 12, "failed": 0},
        metrics={"tokens": 150.0},
        errors=[],
        warnings=["deprecation in lib"],
        artifacts=["report.txt"],
        next_action="VERIFY",
        confidence=0.98,
    )
    assert res.success is True
    assert res.status == ExecutorStatus.SUCCESS
    assert res.summary == "Fixed normalization bugs"
    assert res.files_changed == ["a.py", "b.py"]
    assert res.tests["passed"] == 12
    assert res.next_action == "VERIFY"
    assert res.confidence == 0.98


def test_executor_result_backward_compatibility():
    res = ExecutorResult(
        executor_name="test_engine",
        success=False,
        output="Command failed with exit code 1",
        error="Crash occurred",
        exit_code=1,
    )
    assert res.status == ExecutorStatus.FAILED
    assert "Crash occurred" in res.errors
    assert res.summary == "Command failed with exit code 1"
