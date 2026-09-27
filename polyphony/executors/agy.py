"""Antigravity CLI (agy) executor adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from polyphony.executors.base import BaseExecutor, Mode


class AgyExecutor(BaseExecutor):
    """Executes reasoning or coding actions via Antigravity CLI (`agy -p`)."""

    name = "agy"

    def find_binary(self) -> str | None:
        return shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")

    _MODE_FLAGS = {
        Mode.REVIEW: "plan",
        Mode.CODE: "accept-edits",
    }

    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """Construct the full agy argv for one invocation.

        --sandbox enables terminal restrictions; agy enforces the edit
        policy itself via --mode, so no permission bypass is needed.
        """
        cmd = [
            self.binary_path,
            f"-p={instruction}",
            "--mode", self._MODE_FLAGS[mode],
            "--sandbox",
            "--add-dir", cwd,
        ]
        if model:
            cmd.extend(["--model", model])
        return cmd
