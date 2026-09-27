"""Claude Code CLI executor adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from polyphony.executors.base import BaseExecutor, Mode


class ClaudeExecutor(BaseExecutor):
    """Executes reasoning or coding actions via Claude Code CLI (`claude -p`)."""

    name = "claude"

    def find_binary(self) -> str | None:
        return shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")

    _MODE_FLAGS = {
        Mode.REVIEW: "plan",
        Mode.CODE: "acceptEdits",
    }

    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """Construct the full claude argv for one invocation.

        Permissions are enforced by the CLI itself via --permission-mode.
        --permission-prompts=none makes anything that would prompt fail
        closed instead of hanging a non-interactive run forever.
        """
        cmd = [
            self.binary_path,
            "-p",
            "--permission-mode", self._MODE_FLAGS[mode],
            "--permission-prompts", "none",
        ]
        if model:
            cmd.extend(["--model", model])
        return cmd

    def stdin(self, instruction: str) -> str:
        return instruction
