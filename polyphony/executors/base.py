"""The executor contract: one CLI invocation, in one directory, in one mode."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Mode(str, Enum):
    """How much authority an executor gets for one invocation.

    REVIEW maps onto each CLI's native read-only/plan mode, CODE onto its
    accept-edits mode. The CLI enforces the permission; nothing bypasses it.
    """

    REVIEW = "review"
    CODE = "code"


@dataclass
class ExecutorResult:
    executor: str
    success: bool
    output: str = ""
    error: str | None = None
    exit_code: int = 0


class BaseExecutor(ABC):
    name: str = ""

    def __init__(self, binary_path: str | None = None):
        self.binary_path = binary_path or self.find_binary()

    @abstractmethod
    def find_binary(self) -> str | None:
        """Locate the CLI when no explicit path was given."""

    def is_available(self) -> bool:
        return bool(self.binary_path) and Path(self.binary_path).exists()

    @abstractmethod
    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """The full argv for one invocation."""

    def stdin(self, instruction: str) -> str:
        """What to send on stdin. Empty by default: an inherited stdin can
        hang a non-interactive CLI waiting for input that never comes."""
        return ""

    def detect_failure(self, output: str) -> str | None:
        """A failure the CLI reported in its output despite exiting 0."""
        return None

    def execute(
        self,
        instruction: str,
        cwd: str,
        mode: Mode,
        model: str | None = None,
        timeout_seconds: int = 1800,
    ) -> ExecutorResult:
        if not self.is_available():
            return ExecutorResult(
                self.name,
                False,
                error=f"{self.name} CLI is not installed or not available.",
                exit_code=127,
            )

        argv = self.build_argv(instruction, mode, cwd, model)
        try:
            res = subprocess.run(
                argv,
                input=self.stdin(instruction),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ExecutorResult(
                self.name,
                False,
                error=f"{self.name} timed out after {timeout_seconds}s.",
                exit_code=124,
            )
        except (OSError, subprocess.SubprocessError) as e:
            # Environment failures are executor failures. Anything else is a
            # Polyphony bug and must propagate rather than look like one.
            return ExecutorResult(
                self.name,
                False,
                error=str(e),
                exit_code=1,
            )

        output = res.stdout.strip()
        if res.returncode != 0:
            error = res.stderr.strip() or output or f"{self.name} exited {res.returncode}."
            return ExecutorResult(self.name, False, output, error, res.returncode)

        soft = self.detect_failure(output + "\n" + res.stderr)
        return ExecutorResult(self.name, soft is None, output, soft, 0)
