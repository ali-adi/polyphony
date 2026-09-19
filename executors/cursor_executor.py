"""Cursor CLI executor adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from executors.base import BaseExecutor, ExecutorResult
from executors.python_executor import _get_changed_files_via_git


class CursorExecutor(BaseExecutor):
    """Executes coding actions via Cursor Agent CLI."""

    _class_is_agent_ready: Optional[bool] = None

    def __init__(self, binary_path: Optional[str] = None):
        candidate_paths = [
            binary_path,
            shutil.which("cursor"),
            "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
            os.path.expanduser("~/.local/bin/cursor"),
        ]
        self.binary_path = next((p for p in candidate_paths if p and Path(p).exists()), None)

    @property
    def _is_agent_ready(self) -> Optional[bool]:
        return CursorExecutor._class_is_agent_ready

    @_is_agent_ready.setter
    def _is_agent_ready(self, val: Optional[bool]):
        CursorExecutor._class_is_agent_ready = val

    @property
    def name(self) -> str:
        return "cursor"

    def is_available(self) -> bool:
        if not self.binary_path or not Path(self.binary_path).exists():
            return False
        if CursorExecutor._class_is_agent_ready is not None:
            return CursorExecutor._class_is_agent_ready

        # Test if cursor agent subcommand is installed and available
        try:
            res = subprocess.run(
                [self.binary_path, "agent", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # If it prompts to install from web, agent binary is not locally ready
            if "cursor-agent not found" in res.stdout or "cursor-agent not found" in res.stderr:
                CursorExecutor._class_is_agent_ready = False
            else:
                CursorExecutor._class_is_agent_ready = (res.returncode == 0)
        except Exception:
            CursorExecutor._class_is_agent_ready = False

        return CursorExecutor._class_is_agent_ready

    def execute(
        self,
        instruction: str,
        cwd: str,
        read_only: bool = False,
        timeout_seconds: int = 300,
        model: Optional[str] = None,
        thinking_level: Optional[Any] = None,
        subagents: Optional[Any] = None,
        **kwargs,
    ) -> ExecutorResult:
        if not self.is_available():
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error="Cursor agent CLI is not installed or available.",
                exit_code=127,
                metadata={"available": False},
            )

        start_time = time.time()
        initial_files = set(_get_changed_files_via_git(cwd))

        cmd = [self.binary_path, "agent", "-p"]
        if model:
            cmd.extend(["--model", str(model)])

        try:
            res = subprocess.run(
                cmd,
                input=instruction,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = time.time() - start_time
            current_files = set(_get_changed_files_via_git(cwd))
            newly_changed = sorted(list(current_files - initial_files))

            output = res.stdout.strip()
            error = res.stderr.strip() if res.returncode != 0 else None

            return ExecutorResult(
                success=(res.returncode == 0),
                executor_name=self.name,
                output=output,
                error=error,
                exit_code=res.returncode,
                duration_seconds=duration,
                files_changed=newly_changed,
                metadata={"cmd": " ".join(cmd)},
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error=f"Cursor agent timed out after {timeout_seconds} seconds.",
                exit_code=124,
                duration_seconds=duration,
                metadata={"timeout": True},
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
            )
