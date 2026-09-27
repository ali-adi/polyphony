"""opencode executor adapter. Review only.

Opt-in and unverified against a real binary: the flags come from the
opencode docs (docs/evidence/new-adapters-unverified.md).
"""

from __future__ import annotations

import shutil

from polyphony.executors.base import BaseExecutor, Mode


class OpencodeExecutor(BaseExecutor):
    """Executes read-only reviews via `opencode run --agent plan`.

    There is no code mode. opencode's edit-capable build agent starts from
    permissive defaults (every tool, shell included, allowed without asking)
    and has no sandbox, so it would be a permission bypass in all but name.
    """

    name = "opencode"
    modes = (Mode.REVIEW,)

    def find_binary(self) -> str | None:
        return shutil.which("opencode")

    def build_argv(
        self, instruction: str, mode: Mode, cwd: str, model: str | None = None
    ) -> list[str]:
        """Construct the full opencode argv for one invocation.

        The plan agent sets edits and shell commands to ask, and --auto is
        never passed, so nothing approves them. The message is positional
        and goes last.
        """
        if mode not in self.modes:
            raise ValueError("opencode has no code mode; use it for review only.")
        cmd = [self.binary_path, "run", "--agent", "plan", "--dir", cwd]
        if model:
            cmd.extend(["--model", model])
        cmd.append(instruction)
        return cmd
