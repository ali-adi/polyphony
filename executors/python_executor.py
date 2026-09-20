"""Deterministic Python and shell executor."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from executors.base import (
    BaseExecutor,
    ExecutorResult,
    _get_changed_files_via_git,
    _snapshot_file_states,
    detect_changed_files,
)

logger = logging.getLogger("polyphony.executor.python")





class PythonExecutor(BaseExecutor):
    """Executes deterministic Python / shell commands."""

    def __init__(self, default_interpreter: str = "python3", interactive: bool = False):
        self.default_interpreter = default_interpreter
        self.interactive = interactive

    @property
    def name(self) -> str:
        return "python"

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> List[str]:
        return [
            "deterministic_computation",
            "test_execution",
            "shell_execution",
            "offline_execution",
            "cheap_execution",
        ]

    def health(self) -> Dict[str, Any]:
        return {
            "status": "OK",
            "available": True,
            "default_interpreter": self.default_interpreter,
            "details": "Python & Shell deterministic runtime ready",
        }

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
        start_time = time.time()

        # Defense-in-depth safety validation
        engine = kwargs.get("safety_engine")
        if not engine:
            from orchestrator.safety import SafetyConfig, SafetyEngine
            engine = SafetyEngine(SafetyConfig(read_only=read_only), project_root=cwd)
        safe, reason = engine.validate_command(instruction)
        if not safe:
            err_msg = reason if reason and reason.startswith("Blocked") else f"Blocked by safety policy: {reason}"
            return ExecutorResult(
                success=False,
                executor_name=self.name,
                output="",
                error=err_msg,
                exit_code=1,
                metadata={"command": instruction, "safety_blocked": True},
            )

        is_interactive = kwargs.get("interactive", self.interactive)
        if is_interactive:
            try:
                ans = input(f"\n[SECURITY APPROVAL] Execute command in '{cwd}'?\n  Command: {instruction}\nApprove [y/N]: ").strip().lower()
                if ans not in ("y", "yes"):
                    return ExecutorResult(
                        success=False,
                        executor_name=self.name,
                        output="",
                        error="Command rejected by user in interactive mode.",
                        exit_code=130,
                        duration_seconds=time.time() - start_time,
                        metadata={"command": instruction, "user_aborted": True},
                    )
            except (EOFError, KeyboardInterrupt):
                return ExecutorResult(
                    success=False,
                    executor_name=self.name,
                    output="",
                    error="Command execution aborted by user interrupt.",
                    exit_code=130,
                    duration_seconds=time.time() - start_time,
                    metadata={"command": instruction, "user_aborted": True},
                )
        else:
            logger.warning(f"[SECURITY] Executing command autonomously via shell=True: {instruction[:120]}")

        initial_snapshot = _snapshot_file_states(cwd)

        # Determine command: if instruction is a full command (e.g. "env/bin/python -m ...")
        # run as shell/bash command
        proc = None
        try:
            # Build environment with project virtualenv and interpreter directory in PATH
            env = os.environ.copy()
            extra_paths: List[str] = []
            for venv_name in (".venv", "venv", "env"):
                venv_bin = Path(cwd) / venv_name / "bin"
                if venv_bin.exists() and str(venv_bin) not in extra_paths:
                    extra_paths.append(str(venv_bin))
            if self.default_interpreter:
                interp_path = Path(self.default_interpreter)
                if not interp_path.is_absolute():
                    interp_path = Path(cwd) / interp_path
                if interp_path.exists():
                    interp_dir = str(interp_path.parent)
                    if interp_dir not in extra_paths:
                        extra_paths.append(interp_dir)

            if extra_paths:
                env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + env.get("PATH", "")

            proc = subprocess.Popen(
                instruction,
                cwd=cwd,
                shell=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            duration = time.time() - start_time
            newly_changed = detect_changed_files(initial_snapshot, cwd)

            extracted_metrics = {}
            if stdout:
                try:
                    data = json.loads(stdout.strip())
                    if isinstance(data, dict):
                        m_cand = data.get("metrics") if isinstance(data.get("metrics"), dict) else data
                        for k, v in m_cand.items():
                            if isinstance(v, (int, float)):
                                extracted_metrics[k] = float(v)
                except Exception:
                    pass

            success = (proc.returncode == 0)
            return ExecutorResult(
                success=success,
                executor_name=self.name,
                output=stdout,
                error=stderr if not success else None,
                exit_code=proc.returncode,
                duration_seconds=duration,
                files_changed=newly_changed,
                metrics=extracted_metrics,
                metadata={"command": instruction},
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            if proc:
                try:
                    import signal
                    if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    else:
                        proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=1)
                except Exception:
                    pass
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
