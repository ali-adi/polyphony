"""Base abstract class and result models for execution adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutorResult(BaseModel):
    """Normalized result returned by any executor engine."""
    success: bool
    executor_name: str
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    duration_seconds: float = 0.0
    files_changed: List[str] = Field(default_factory=list)
    raw_response: Optional[Any] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseExecutor(ABC):
    """Abstract interface for all agent executors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the executor adapter (e.g. claude, agy, cursor, python)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the underlying CLI binary or runtime is installed and accessible."""
        pass

    @abstractmethod
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
        """Execute a given instruction inside the target repository working directory."""
        pass
