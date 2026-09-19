"""Tests for executor adapters and routing."""

import os
from pathlib import Path
import pytest

from executors.base import ExecutorResult
from executors.python_executor import PythonExecutor
from executors.router import ExecutorRouter


def test_python_executor_success(tmp_path):
    executor = PythonExecutor()
    res = executor.execute("echo 'hello from python executor'", cwd=str(tmp_path))

    assert res.success is True
    assert res.exit_code == 0
    assert "hello from python executor" in res.output
    assert res.executor_name == "python"


def test_python_executor_failure(tmp_path):
    executor = PythonExecutor()
    res = executor.execute("false", cwd=str(tmp_path))

    assert res.success is False
    assert res.exit_code != 0


def test_router_fallback():
    router = ExecutorRouter()
    # Test that fallback chain contains expected fallbacks
    chain_agy = router.get_default_fallback_chain("agy")
    assert chain_agy == ["agy", "cursor", "claude"]

    chain_cursor = router.get_default_fallback_chain("cursor")
    assert chain_cursor == ["cursor", "agy", "claude"]

    # Test python execution through router
    res, used = router.execute(
        target_executor="python",
        instruction="echo 'routed'",
        cwd=os.getcwd(),
    )
    assert res.success is True
    assert used == "python"
    assert "routed" in res.output


def test_python_executor_safety_blocking(tmp_path):
    executor = PythonExecutor()
    res = executor.execute("git push origin main", cwd=str(tmp_path))

    assert res.success is False
    assert res.metadata.get("safety_blocked") is True
    assert "Blocked by safety policy" in res.error


def test_python_executor_git_rename_parsing(tmp_path, monkeypatch):
    from executors.python_executor import _get_changed_files_via_git
    import subprocess

    class DummyProc:
        returncode = 0
        stdout = "R  old_file.py -> new_file.py\nM  existing.py\n?? untracked.py\n"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyProc())
    changed = _get_changed_files_via_git(str(tmp_path))
    assert changed == ["new_file.py", "existing.py", "untracked.py"]
