"""Router and fallback orchestrator across executor adapters."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from executors.base import BaseExecutor, ExecutorResult
from executors.claude_executor import ClaudeExecutor
from executors.agy_executor import AgyExecutor
from executors.cursor_executor import CursorExecutor
from executors.python_executor import PythonExecutor

logger = logging.getLogger("polyphony.router")


def is_infrastructure_error(result: ExecutorResult) -> bool:
    """Determine if a failure is an infrastructure issue (deserving fallback) vs task-level issue."""
    if result.metadata.get("quota_exceeded") or result.metadata.get("timeout"):
        return True
    if result.exit_code in (124, 127):  # timeout or binary not found
        return True
    err_str = ((result.error or "") + " " + (result.output or "")).lower()
    infra_signals = [
        "quota",
        "rate limit",
        "weekly limit",
        "binary not found",
        "not available",
        "resource exhausted",
        "timed out",
        "timeout",
        "failed execution",
        "command failed to start",
    ]
    return any(signal in err_str for signal in infra_signals)


def _get_git_root(cwd: str) -> Optional[Path]:
    """Find top-level Git working tree, handling monorepo subdirectories and worktrees."""
    try:
        import subprocess
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            p = Path(res.stdout.strip())
            if p.exists():
                return p
    except Exception:
        pass
    git_dir = Path(cwd) / ".git"
    if git_dir.exists():
        return Path(cwd)
    return None


def _is_temp_checkpoint(cwd: str) -> bool:
    """Verify if the latest commit is a Polyphony temporary checkpoint commit."""
    try:
        import subprocess
        git_root = _get_git_root(cwd) or Path(cwd)
        res = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            cwd=str(git_root),
            capture_output=True,
            text=True,
        )
        return res.stdout.strip() == "polyphony-temp-checkpoint"
    except Exception:
        return False


def create_workspace_checkpoint(cwd: str) -> bool:
    """Create a temporary git commit to guarantee rollback safety without data loss."""
    try:
        git_root = _get_git_root(cwd)
        if git_root:
            import subprocess
            subprocess.run(["git", "add", "-A"], cwd=str(git_root), capture_output=True)
            res = subprocess.run(
                [
                    "git",
                    "-c", "user.name=Polyphony",
                    "-c", "user.email=polyphony@local",
                    "commit",
                    "--allow-empty",
                    "-m", "polyphony-temp-checkpoint",
                ],
                cwd=str(git_root),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0
    except Exception as e:
        logger.warning(f"Failed to create workspace checkpoint in {cwd}: {e}")
    return False


def rollback_workspace(cwd: str):
    """Roll back uncommitted workspace changes after a failed execution in a git repository."""
    try:
        git_root = _get_git_root(cwd)
        if git_root:
            import subprocess
            if _is_temp_checkpoint(str(git_root)):
                # Revert any changes made since checkpoint
                subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=str(git_root), capture_output=True)
                # Remove untracked files created by the failed executor
                subprocess.run(["git", "clean", "-fd"], cwd=str(git_root), capture_output=True)
                # Soft reset to restore previous uncommitted changes cleanly
                subprocess.run(["git", "reset", "--soft", "HEAD~1"], cwd=str(git_root), capture_output=True)
            else:
                logger.warning("No temporary checkpoint commit found at HEAD. Skipping soft reset.")
    except Exception as e:
        logger.warning(f"Failed to rollback workspace in {cwd}: {e}")


def release_workspace_checkpoint(cwd: str):
    """Clean up temporary checkpoint commit while keeping all modifications."""
    try:
        git_root = _get_git_root(cwd)
        if git_root:
            import subprocess
            if _is_temp_checkpoint(str(git_root)):
                subprocess.run(["git", "reset", "--soft", "HEAD~1"], cwd=str(git_root), capture_output=True)
            else:
                logger.warning("No temporary checkpoint commit found at HEAD. Skipping soft reset.")
    except Exception as e:
        logger.warning(f"Failed to release workspace checkpoint in {cwd}: {e}")



class ExecutorRouter:
    """Manages routing of implementation requests and coordinates bidirectional fallbacks."""

    def __init__(
        self,
        claude_path: Optional[str] = None,
        agy_path: Optional[str] = None,
        cursor_path: Optional[str] = None,
        python_bin: str = "python3",
    ):
        self.executors: Dict[str, BaseExecutor] = {
            "claude": ClaudeExecutor(binary_path=claude_path),
            "agy": AgyExecutor(binary_path=agy_path),
            "cursor": CursorExecutor(binary_path=cursor_path),
            "python": PythonExecutor(default_interpreter=python_bin),
        }

    def get_executor(self, name: str) -> Optional[BaseExecutor]:
        return self.executors.get(name.lower())

    def get_available_executors(self) -> Dict[str, bool]:
        """Return dict of executor name to availability boolean."""
        return {name: ex.is_available() for name, ex in self.executors.items()}

    def get_default_fallback_chain(self, primary: str) -> List[str]:
        """Define resilient fallback order depending on the requested primary engine."""
        primary = primary.lower()
        if primary == "claude":
            return ["claude", "agy", "cursor"]
        elif primary == "agy":
            return ["agy", "cursor", "claude"]
        elif primary == "cursor":
            return ["cursor", "agy", "claude"]
        elif primary == "python":
            return ["python"]
        return [primary, "agy", "cursor", "claude"]

    def execute(
        self,
        target_executor: str,
        instruction: str,
        cwd: str,
        read_only: bool = False,
        timeout_seconds: int = 300,
        enable_fallback: bool = True,
        custom_fallback_chain: Optional[List[str]] = None,
        models_config: Optional[Any] = None,
        **kwargs,
    ) -> Tuple[ExecutorResult, str]:
        """
        Execute instruction with automatic fallback handling.
        Returns: (ExecutorResult, used_executor_name)
        """
        chain = custom_fallback_chain or self.get_default_fallback_chain(target_executor)
        if not enable_fallback:
            chain = [target_executor]

        last_result: Optional[ExecutorResult] = None
        attempted: List[str] = []

        for candidate_name in chain:
            candidate = self.get_executor(candidate_name)
            if not candidate:
                continue

            if not candidate.is_available():
                logger.info(f"Executor '{candidate_name}' is not available, skipping.")
                continue

            logger.info(f"Attempting execution using executor: {candidate_name}")
            attempted.append(candidate_name)

            candidate_kwargs = kwargs.copy()
            if models_config and hasattr(models_config, "executors"):
                exec_profile = models_config.executors.get(candidate_name)
                if exec_profile:
                    # Use candidate-specific model if fallback or if none explicitly supplied
                    if candidate_name != target_executor or not candidate_kwargs.get("model"):
                        if exec_profile.model:
                            candidate_kwargs["model"] = exec_profile.model
                    if candidate_name != target_executor or not candidate_kwargs.get("thinking_level"):
                        if exec_profile.thinking_level:
                            candidate_kwargs["thinking_level"] = exec_profile.thinking_level

            has_checkpoint = False
            if not read_only:
                has_checkpoint = create_workspace_checkpoint(cwd)

            try:
                result = candidate.execute(
                    instruction=instruction,
                    cwd=cwd,
                    read_only=read_only,
                    timeout_seconds=timeout_seconds,
                    **candidate_kwargs,
                )
            except Exception as e:
                if has_checkpoint:
                    rollback_workspace(cwd)
                raise

            # Check if this execution succeeded
            if result.success:
                if has_checkpoint:
                    release_workspace_checkpoint(cwd)
                return result, candidate_name

            last_result = result
            # Distinguish infrastructure errors vs task errors
            if is_infrastructure_error(result):
                logger.warning(
                    f"Executor '{candidate_name}' failed with infrastructure error: {result.error}. "
                    f"Rolling back changes and attempting fallback..."
                )
                if not read_only and has_checkpoint:
                    rollback_workspace(cwd)
                continue
            else:
                # Task error (bad code, assertion failure, etc.) -> return to orchestrator for re-planning
                logger.info(
                    f"Executor '{candidate_name}' failed with task-level error: {result.error}. "
                    f"Returning to orchestrator without fallback."
                )
                if has_checkpoint:
                    release_workspace_checkpoint(cwd)
                return result, candidate_name

        # If all candidates exhausted, return last result or failure record
        if last_result:
            return last_result, (attempted[-1] if attempted else target_executor)

        return (
            ExecutorResult(
                success=False,
                executor_name=target_executor,
                output="",
                error=f"No available executors found in fallback chain: {chain}",
                exit_code=127,
            ),
            target_executor,
        )
