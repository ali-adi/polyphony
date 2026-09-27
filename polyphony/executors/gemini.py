"""Google Gemini CLI (gemini) executor adapter.

Opt-in and unverified against a real binary: the flags come from the
gemini-cli docs (docs/evidence/new-adapters-unverified.md).
"""

from __future__ import annotations

import shutil

from polyphony.executors.base import BaseExecutor, Mode


class GeminiExecutor(BaseExecutor):
    """Executes reasoning or coding actions via Gemini CLI (`gemini --prompt`)."""

    name = "gemini"

    def find_binary(self) -> str | None:
        return shutil.which("gemini")

    # plan is Gemini's read-only mode. auto_edit approves edits only; any
    # other tool call would need approval, which headless runs treat as a
    # denial, so nothing hangs and nothing is bypassed.
    _MODE_FLAGS = {
        Mode.REVIEW: "plan",
        Mode.CODE: "auto_edit",
    }

    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """Construct the full gemini argv for one invocation.

        The prompt is attached with `=` so an instruction starting with a
        dash stays the flag's value.
        """
        cmd = [self.binary_path, "--approval-mode", self._MODE_FLAGS[mode]]
        if model:
            cmd.extend(["--model", model])
        cmd.append(f"--prompt={instruction}")
        return cmd
