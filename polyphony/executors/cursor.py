"""Cursor CLI executor adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from polyphony.executors.base import BaseExecutor, Mode


class CursorExecutor(BaseExecutor):
    """Executes coding actions via Cursor Agent CLI."""

    name = "cursor"

    _class_is_agent_ready: bool | None = None
    _class_last_checked: float = 0.0
    _CACHE_TTL_SECONDS: float = 300.0

    def find_binary(self) -> str | None:
        candidate_paths = [
            shutil.which("cursor-agent"),
            os.path.expanduser("~/.local/bin/cursor-agent"),
            shutil.which("cursor"),
            "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
            os.path.expanduser("~/.local/bin/cursor"),
        ]
        return next((p for p in candidate_paths if p and Path(p).exists()), None)

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
        except (OSError, subprocess.SubprocessError):
            CursorExecutor._class_is_agent_ready = False

        return CursorExecutor._class_is_agent_ready

    def _uses_agent_subcommand(self) -> bool:
        """The legacy `cursor` binary needs an `agent` subcommand; `cursor-agent` does not."""
        return Path(self.binary_path).name != "cursor-agent"

    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """Construct the full cursor-agent argv for one invocation.

        The prompt is positional and must be appended last: cursor parses
        `agent [options] [prompt...]`, so an instruction placed earlier would
        be consumed as a flag's value.
        """
        cmd = [self.binary_path]
        if self._uses_agent_subcommand():
            cmd.append("agent")
        cmd.append("-p")

        if mode is Mode.REVIEW:
            cmd.extend(["--mode", "plan", "--trust"])
        else:
            cmd.extend(["-f", "--sandbox", "enabled"])

        if model:
            cmd.extend(["--model", model])

        cmd.append(instruction)
        return cmd

    # cursor-agent exits 0 even when it refuses to do the work, reporting the
    # reason on stdout. These are the markers observed in real runs; add to
    # this list only from evidence, never from guesswork
    # (docs/evidence/smoke-results.md).
    #
    # Each marker counts only at the start of a line, as the CLI prints it
    # (after an icon such as the trust prompt's "⚠"): the output also holds
    # the agent's own summary, and a job that added handling for an "out of
    # usage" API response must not be failed for saying so.
    _SOFT_FAILURE_MARKERS = (
        "ActionRequiredError",
        "You're out of usage",
        "Workspace Trust Required",
    )

    def detect_failure(self, output: str) -> str | None:
        if not output:
            return None
        for line in output.splitlines():
            text = line.lstrip(" \t⚠️")
            for marker in self._SOFT_FAILURE_MARKERS:
                if text.startswith(marker):
                    return f"cursor-agent reported a failure in its output: {marker}"
        return None
