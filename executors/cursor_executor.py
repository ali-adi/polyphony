"""Cursor CLI executor adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from executors.base import (
    BaseExecutor,
    ExecutorResult,
    Mode,
    resolve_mode,
    _get_changed_files_via_git as _base_get_changed_files_via_git,
    _snapshot_file_states as _base_snapshot_file_states,
    detect_changed_files as _base_detect_changed_files,
)


def _get_changed_files_via_git(cwd: str) -> List[str]:
    return _base_get_changed_files_via_git(cwd)


def _snapshot_file_states(cwd: str) -> Dict[str, Tuple[float, int]]:
    return _base_snapshot_file_states(cwd, get_changed_files_fn=_get_changed_files_via_git)


def detect_changed_files(initial_snapshot: Dict[str, Tuple[float, int]], cwd: str) -> List[str]:
    return _base_detect_changed_files(initial_snapshot, cwd, snapshot_fn=_snapshot_file_states)


class CursorExecutor(BaseExecutor):
    """Executes coding actions via Cursor Agent CLI."""

    _class_is_agent_ready: Optional[bool] = None
    _class_last_checked: float = 0.0
    _CACHE_TTL_SECONDS: float = 300.0

    def __init__(self, binary_path: Optional[str] = None):
        if binary_path:
            self.binary_path = binary_path
            return
        candidate_paths = [
            shutil.which("cursor-agent"),
            os.path.expanduser("~/.local/bin/cursor-agent"),
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
        now = time.time()
        if (
            CursorExecutor._class_is_agent_ready is not None
            and (now - CursorExecutor._class_last_checked) < CursorExecutor._CACHE_TTL_SECONDS
        ):
            return CursorExecutor._class_is_agent_ready

        # Test if cursor agent subcommand is installed and available
        try:
            CursorExecutor._class_last_checked = now
            probe = [self.binary_path]
            if self._uses_agent_subcommand():
                probe.append("agent")
            probe.append("--help")
            res = subprocess.run(probe, capture_output=True, text=True, timeout=10)
            # If it prompts to install from web, agent binary is not locally ready
            if "cursor-agent not found" in res.stdout or "cursor-agent not found" in res.stderr:
                CursorExecutor._class_is_agent_ready = False
            else:
                CursorExecutor._class_is_agent_ready = (res.returncode == 0)
        except Exception:
            CursorExecutor._class_is_agent_ready = False

        return CursorExecutor._class_is_agent_ready

    def capabilities(self) -> List[str]:
        return [
            "code_editing",
            "fast_reasoning",
            "diff_analysis",
        ]

    def health(self) -> Dict[str, Any]:
        avail = self.is_available()
        return {
            "status": "OK" if avail else "UNAVAILABLE",
            "available": avail,
            "binary_path": self.binary_path,
            "details": "Cursor agent ready" if avail else "Cursor CLI or agent subcommand not ready",
        }

    def _uses_agent_subcommand(self) -> bool:
        """The legacy `cursor` binary needs an `agent` subcommand; `cursor-agent` does not."""
        return Path(self.binary_path).name != "cursor-agent"

    def build_argv(
        self,
        instruction: str,
        instruction_mode: Mode,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        output_format: str = "text",
    ) -> List[str]:
        """Construct the full cursor-agent argv for one invocation.

        The prompt is positional and must be appended last: cursor parses
        `agent [options] [prompt...]`, so an instruction placed earlier would
        be consumed as a flag's value.
        """
        cmd = [self.binary_path]
        if self._uses_agent_subcommand():
            cmd.append("agent")
        cmd.append("-p")

        if instruction_mode is Mode.REVIEW:
            cmd.extend(["--mode", "plan", "--trust"])
        else:
            cmd.extend(["-f", "--sandbox", "enabled"])

        if session_id:
            cmd.extend(["--resume", str(session_id)])
        if model:
            cmd.extend(["--model", str(model)])
        if output_format and output_format != "text":
            cmd.extend(["--output-format", output_format])

        cmd.append(instruction)
        return cmd

    # cursor-agent exits 0 even when it refuses to do the work, reporting the
    # reason on stdout. These are the markers observed in real runs; add to
    # this list only from evidence, never from guesswork.
    _SOFT_FAILURE_MARKERS = (
        "ActionRequiredError",
        "out of usage",
        "Workspace Trust Required",
    )

    def _detect_soft_failure(self, output: str) -> Optional[str]:
        """Detect a failure the CLI reported in its output despite exit code 0."""
        if not output:
            return None
        for marker in self._SOFT_FAILURE_MARKERS:
            if marker in output:
                return f"cursor-agent reported a failure in its output: {marker}"
        return None

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
        initial_snapshot = _snapshot_file_states(cwd)

        cmd = self.build_argv(
            instruction,
            instruction_mode=resolve_mode(kwargs.get("mode"), read_only),
            model=model,
            session_id=kwargs.get("session_id"),
            output_format=kwargs.get("output_format", "text"),
        )

        try:
            res = subprocess.run(
                cmd,
                input="",
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = time.time() - start_time
            newly_changed = detect_changed_files(initial_snapshot, cwd)

            output = res.stdout.strip()
            error = res.stderr.strip() if res.returncode != 0 else None

            soft_failure = self._detect_soft_failure(output)
            return ExecutorResult(
                success=(res.returncode == 0 and soft_failure is None),
                executor_name=self.name,
                output=output,
                error=error or soft_failure,
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
