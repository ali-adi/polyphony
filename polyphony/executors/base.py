"""The executor contract: one CLI invocation, in one directory, in one mode."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
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
    # A CLI with no safe edit mode drops CODE rather than bypassing permissions.
    modes: tuple[Mode, ...] = (Mode.REVIEW, Mode.CODE)

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
        output_path: Path | None = None,
        on_start: Callable[[int], None] | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutorResult:
        """Run the CLI once.

        stdout goes straight to output_path as the CLI writes it, so a job's
        progress is readable while it runs. stderr goes to a separate file:
        it is what explains a non-zero exit, and keeping it out of the output
        keeps a review's product clean. Both are files, not pipes, so a chatty
        CLI can never block on a full pipe buffer.

        The CLI leads its own process group, so a timeout kills everything it
        started, not just the CLI. on_start receives that group's id, which
        cancel needs because the group is no longer the worker's.

        `env` replaces the inherited environment when given; the worker
        passes one with the project's env_scrub variables removed.
        """
        if not self.is_available():
            return ExecutorResult(
                self.name,
                False,
                error=f"{self.name} CLI is not installed or not available.",
                exit_code=127,
            )

        argv = self.build_argv(instruction, mode, cwd, model)
        with (
            open(output_path, "w+b") if output_path else tempfile.TemporaryFile() as out,
            tempfile.TemporaryFile() as err,
        ):
            try:
                with subprocess.Popen(
                    argv,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=out,
                    stderr=err,
                    text=True,
                    start_new_session=True,
                ) as proc:
                    timed_out = False
                    try:
                        if on_start:
                            on_start(proc.pid)
                        proc.communicate(self.stdin(instruction), timeout=timeout_seconds)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        _kill_group(proc.pid)
                    except BaseException:
                        # Leaving here would otherwise wait on the CLI forever.
                        _kill_group(proc.pid)
                        raise
            except (OSError, subprocess.SubprocessError) as e:
                # Environment failures are executor failures. Anything else is a
                # Polyphony bug and must propagate rather than look like one.
                return ExecutorResult(
                    self.name,
                    False,
                    error=str(e),
                    exit_code=1,
                )
            output, stderr = _read(out), _read(err)

        if timed_out:
            error = f"{self.name} timed out after {timeout_seconds}s."
            return ExecutorResult(self.name, False, output, error, 124)
        if proc.returncode != 0:
            error = stderr or output or f"{self.name} exited {proc.returncode}."
            return ExecutorResult(self.name, False, output, error, proc.returncode)

        soft = self.detect_failure(output + "\n" + stderr)
        return ExecutorResult(self.name, soft is None, output, soft, 0)


def _read(f) -> str:
    f.seek(0)
    return f.read().decode(errors="replace").strip()


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass  # already gone, or (macOS) still being reaped
