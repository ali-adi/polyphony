"""Tests for router fallback behavior across executor adapters."""

import pytest
from executors.base import BaseExecutor, ExecutorResult
from executors.router import ExecutorRouter


class FailingExecutor(BaseExecutor):
    def __init__(self, name: str, fail_on_execute: bool = True):
        self._name = name
        self.fail_on_execute = fail_on_execute

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def execute(self, instruction: str, cwd: str, **kwargs) -> ExecutorResult:
        if self.fail_on_execute:
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error=f"{self.name} failed execution",
                exit_code=1,
            )
        return ExecutorResult(
            success=True,
            executor_name=self.name,
            output=f"Success from {self.name}",
            exit_code=0,
        )


class UnavailableExecutor(BaseExecutor):
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return False

    def execute(self, instruction: str, cwd: str, **kwargs) -> ExecutorResult:
        return ExecutorResult(
            success=False,
            executor_name=self.name,
            output="",
            error="Not available",
            exit_code=127,
        )


def test_fallback_when_primary_fails(tmp_path):
    router = ExecutorRouter()
    # Replace agy with failing executor and cursor with working mock executor
    router.executors["agy"] = FailingExecutor("agy", fail_on_execute=True)
    router.executors["cursor"] = FailingExecutor("cursor", fail_on_execute=False)

    # Request agy as primary, fallback chain should invoke cursor and succeed
    result, used = router.execute(
        target_executor="agy",
        instruction="Perform edit",
        cwd=str(tmp_path),
        custom_fallback_chain=["agy", "cursor"],
    )

    assert result.success is True
    assert used == "cursor"
    assert "Success from cursor" in result.output


def test_fallback_when_primary_unavailable(tmp_path):
    router = ExecutorRouter()
    router.executors["agy"] = UnavailableExecutor("agy")
    router.executors["cursor"] = FailingExecutor("cursor", fail_on_execute=False)

    result, used = router.execute(
        target_executor="agy",
        instruction="Perform edit",
        cwd=str(tmp_path),
        custom_fallback_chain=["agy", "cursor"],
    )

    assert result.success is True
    assert used == "cursor"
    assert "Success from cursor" in result.output


class TaskErrorExecutor(BaseExecutor):
    @property
    def name(self) -> str:
        return "claude"

    def is_available(self) -> bool:
        return True

    def execute(self, instruction: str, cwd: str, **kwargs) -> ExecutorResult:
        return ExecutorResult(
            success=False,
            executor_name=self.name,
            output="SyntaxError: invalid syntax in test.py",
            error="AssertionError: 1 != 2",
            exit_code=1,
        )


def test_no_fallback_on_task_error(tmp_path):
    router = ExecutorRouter()
    router.executors["claude"] = TaskErrorExecutor()
    router.executors["agy"] = FailingExecutor("agy", fail_on_execute=False)

    result, used = router.execute(
        target_executor="claude",
        instruction="Run tests",
        cwd=str(tmp_path),
        custom_fallback_chain=["claude", "agy"],
    )

    # Should return task error directly to orchestrator without falling back to agy
    assert result.success is False
    assert used == "claude"
    assert "AssertionError" in result.error

