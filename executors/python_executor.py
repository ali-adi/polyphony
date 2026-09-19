"""Deterministic Python and shell executor."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional
from executors.base import BaseExecutor, ExecutorResult


def _get_changed_files_via_git(cwd: str) -> List[str]:
    """Inspect git status to see modified or untracked files."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            files = []
            for line in lines:
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1])
            return files
    except Exception:
        pass
    return []


class PythonExecutor(BaseExecutor):
    """Executes deterministic Python / shell commands."""

    def __init__(self, default_interpreter: str = "python3"):
        self.default_interpreter = default_interpreter

    @property
    def name(self) -> str:
        return "python"

    def is_available(self) -> bool:
        return True

    def execute(
        self,
        instruction: str,
        cwd: str,
        read_only: bool = False,
        timeout_seconds: int = 300,
        **kwargs,
    ) -> ExecutorResult:
        start_time = time.time()
        initial_files = set(_get_changed_files_via_git(cwd))

        # Determine command: if instruction is a full command (e.g. "env/bin/python -m ...")
        # run as shell/bash command
        try:
            res = subprocess.run(
                instruction,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = time.time() - start_time
            current_files = set(_get_changed_files_via_git(cwd))
            newly_changed = sorted(list(current_files - initial_files))

            success = (res.returncode == 0)
            return ExecutorResult(
                success=success,
                executor_name=self.name,
                output=res.stdout,
                error=res.stderr if not success else None,
                exit_code=res.returncode,
                duration_seconds=duration,
                files_changed=newly_changed,
                metadata={"command": instruction},
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error=f"Execution timed out after {timeout_seconds} seconds.",
                exit_code=124,
                duration_seconds=duration,
                metadata={"command": instruction, "timeout": True},
            )
        except Exception as e:
            duration = time.time() - start_time
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error=str(e),
                exit_code=1,
                duration_seconds=duration,
                metadata={"command": instruction},
            )
