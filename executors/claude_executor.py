"""Claude Code CLI executor adapter."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from executors.base import (
    BaseExecutor,
    ExecutorResult,
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


class ClaudeExecutor(BaseExecutor):
    """Executes reasoning or coding actions via Claude Code CLI (`claude -p`)."""

    def __init__(self, binary_path: Optional[str] = None):
        self.binary_path = binary_path or shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")

    @property
    def name(self) -> str:
        return "claude"

    def is_available(self) -> bool:
        if not self.binary_path or not Path(self.binary_path).exists():
            return False
        return True

    def check_binary_health(self) -> tuple[bool, str]:
        """Check if Claude CLI binary is present and functional."""
        if not self.is_available():
            return False, "Claude CLI binary not found."
        try:
            res = subprocess.run(
                [self.binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (res.stdout + res.stderr).strip()
            if res.returncode == 0:
                return True, "Available"
            if "weekly limit" in output.lower() or "rate limit" in output.lower():
                return False, output
            return False, output or f"Claude CLI returned non-zero exit code {res.returncode}"
        except Exception as e:
            return False, str(e)

    # Backwards compatibility alias
    check_quota_status = check_binary_health

    def execute(
        self,
        instruction: str,
        cwd: str,
        read_only: bool = False,
        timeout_seconds: int = 300,
        output_format: str = "text",
        system_prompt: Optional[str] = None,
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
                error="Claude CLI binary not found.",
                exit_code=127,
            )

        start_time = time.time()
        initial_snapshot = _snapshot_file_states(cwd)

        cmd = [
            self.binary_path,
            "-p",
            "--dangerously-skip-permissions",
        ]

        # Session continuation
        session_id = kwargs.get("session_id")
        continue_session = kwargs.get("continue_session", False)
        if session_id:
            cmd.extend(["--resume", str(session_id)])
        elif continue_session:
            cmd.append("--continue")

        if model:
            cmd.extend(["--model", str(model)])

        # Handle subagents specification (--agents <json>)
        if subagents:
            agents_json = None
            if hasattr(subagents, "to_claude_agents_json"):
                agents_json = subagents.to_claude_agents_json()
            elif isinstance(subagents, dict):
                agents_json = json.dumps(subagents)
            elif isinstance(subagents, str):
                agents_json = subagents
            if agents_json:
                cmd.extend(["--agents", agents_json])

        if output_format in ("json", "stream-json"):
            cmd.extend(["--output-format", output_format])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt, "--system-prompt-snapshot", "on"])

        if read_only:
            cmd.extend(["--tools", "Read,Bash"])

        env = os.environ.copy()
        if thinking_level is not None:
            from orchestrator.models_config import map_thinking_to_tokens
            tokens = map_thinking_to_tokens(thinking_level)
            if tokens:
                env["MAX_THINKING_TOKENS"] = str(tokens)

        try:
            res = subprocess.run(
                cmd,
                input=instruction,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            duration = time.time() - start_time
            newly_changed = detect_changed_files(initial_snapshot, cwd)

            output = res.stdout.strip()
            error = res.stderr.strip() if res.returncode != 0 else None

            # Detect quota / limit exhaustion
            full_out = (output + " " + (error or "")).lower()
            if "weekly limit" in full_out or "rate limit" in full_out:
                return ExecutorResult(
                    success=False,
                    executor_name=self.name,
                    output=output,
                    error=output or error or "Claude subscription quota reached.",
                    exit_code=res.returncode or 1,
                    duration_seconds=duration,
                    metadata={"quota_exceeded": True},
                )

            metadata: Dict[str, Any] = {"cmd": " ".join(cmd)}
            extracted_session = None
            try:
                data = json.loads(output)
                if isinstance(data, dict):
                    if "session_id" in data:
                        extracted_session = str(data["session_id"])
                    elif "conversation_id" in data:
                        extracted_session = str(data["conversation_id"])
            except Exception:
                pass

            if not extracted_session:
                session_match = re.search(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b", output + " " + (error or ""))
                if session_match:
                    extracted_session = session_match.group(1)

            if extracted_session:
                metadata["session_id"] = extracted_session
            elif session_id:
                metadata["session_id"] = session_id

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
                error=f"Claude CLI timed out after {timeout_seconds} seconds.",
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
