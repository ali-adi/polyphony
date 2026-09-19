"""Router and fallback orchestrator across executor adapters."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from executors.base import BaseExecutor, ExecutorResult
from executors.claude_executor import ClaudeExecutor
from executors.agy_executor import AgyExecutor
from executors.cursor_executor import CursorExecutor
from executors.python_executor import PythonExecutor

logger = logging.getLogger("polyphony.router")


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
                if hasattr(models_config, "subagents") and "subagents" not in candidate_kwargs:
                    candidate_kwargs["subagents"] = models_config.subagents

            result = candidate.execute(
                instruction=instruction,
                cwd=cwd,
                read_only=read_only,
                timeout_seconds=timeout_seconds,
                **candidate_kwargs,
            )

            # Check if this execution succeeded
            if result.success:
                return result, candidate_name

            last_result = result
            # If failed due to quota limit or binary error, try next in fallback chain
            logger.warning(
                f"Executor '{candidate_name}' failed with error: {result.error}. "
                f"Checking fallback..."
            )

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
