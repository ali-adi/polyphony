"""OpenAI Codex CLI (codex) executor adapter.

Opt-in and unverified against a real binary: the flags come from OpenAI's
CLI reference (docs/evidence/new-adapters-unverified.md).
"""

from __future__ import annotations

import shutil

from polyphony.executors.base import BaseExecutor, Mode


class CodexExecutor(BaseExecutor):
    """Executes reasoning or coding actions via `codex exec`."""

    name = "codex"

    def find_binary(self) -> str | None:
        return shutil.which("codex")

    # Codex's own sandbox policy for the commands the model runs. Code mode
    # is workspace-write, never danger-full-access or the bypass flag.
    _SANDBOX = {
        Mode.REVIEW: "read-only",
        Mode.CODE: "workspace-write",
    }

    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """Construct the full codex argv for one invocation.

        The prompt goes on stdin (`-`), so an instruction starting with a
        dash can never be read as a flag.
        """
        cmd = [
            self.binary_path,
            "exec",
            "--sandbox", self._SANDBOX[mode],
            "--cd", cwd,
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.append("-")
        return cmd

    def stdin(self, instruction: str) -> str:
        return instruction
