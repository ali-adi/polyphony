"""Antigravity CLI (agy) executor adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from executors.base import BaseExecutor, ExecutorResult
from executors.python_executor import _get_changed_files_via_git


class AgyExecutor(BaseExecutor):
    """Executes reasoning or coding actions via Antigravity CLI (`agy -p`)."""

    def __init__(self, binary_path: Optional[str] = None):
        self.binary_path = binary_path or shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")

    @property
    def name(self) -> str:
        return "agy"

    def is_available(self) -> bool:
        if not self.binary_path or not Path(self.binary_path).exists():
            return False
        return True

    def execute(
        self,
        instruction: str,
        cwd: str,
        read_only: bool = False,
        timeout_seconds: int = 300,
        output_format: str = "text",
        mode: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        thinking_level: Optional[Any] = None,
        subagents: Optional[Any] = None,
        **kwargs,
    ) -> ExecutorResult:
        if not self.is_available():
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error="Antigravity CLI (agy) binary not found.",
                exit_code=127,
            )

        start_time = time.time()
        initial_files = set(_get_changed_files_via_git(cwd))

        cmd = [
            self.binary_path,
            "--input-format",
            "text",
            "--dangerously-skip-permissions",
            "--add-dir",
            cwd,
        ]

        # Session continuation
        session_id = kwargs.get("session_id") or kwargs.get("conversation_id")
        continue_session = kwargs.get("continue_session", False)
        if session_id:
            cmd.extend(["--conversation", str(session_id)])
        elif continue_session:
            cmd.append("--continue")

        if output_format in ("text", "json", "stream-json"):
            cmd.extend(["--output-format", output_format])

        if mode:
            cmd.extend(["--mode", mode])
        elif read_only:
            cmd.extend(["--mode", "plan"])

        if model:
            cmd.extend(["--model", str(model)])

        resolved_effort = effort
        if not resolved_effort and thinking_level is not None:
            from orchestrator.models_config import map_thinking_to_effort
            resolved_effort = map_thinking_to_effort(thinking_level)

        if resolved_effort:
            cmd.extend(["--effort", str(resolved_effort)])

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
            full_out = (output + " " + (error or "")).lower()

            metadata = {"cmd": " ".join(cmd)}
            if session_id:
                metadata["session_id"] = session_id
            if "quota" in full_out or "rate limit" in full_out or "resource exhausted" in full_out:
                metadata["quota_exceeded"] = True

            return ExecutorResult(
                success=(res.returncode == 0),
                executor_name=self.name,
                output=output,
                error=error,
                exit_code=res.returncode,
                duration_seconds=duration,
                files_changed=newly_changed,
                metadata=metadata,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error=f"AGY execution timed out after {timeout_seconds} seconds.",
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
