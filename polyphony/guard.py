"""The only sanctioned way to spawn git.

`push` is the one git operation with irreversible, outward-facing
consequence, so it is refused structurally — before a process exists —
rather than by inspecting an agent's instruction text, which is defeatable.
"""

from __future__ import annotations

import subprocess
from typing import List

# git flags that consume the following token as their value, so the
# subcommand cannot be the token immediately after them.
_FLAGS_WITH_VALUES = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix",
}

_FORBIDDEN_SUBCOMMANDS = {"push"}


class ForbiddenGitCommand(Exception):
    """Raised when a git invocation is refused by policy."""


def _subcommand(args: List[str]) -> str | None:
    """Find the git subcommand, skipping global flags and their values."""
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in _FLAGS_WITH_VALUES:
            i += 2
        elif tok.startswith("-"):
            i += 1
        else:
            return tok
    return None


def run_git(
    args: List[str], cwd: str, timeout: int = 30, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run a git command, refusing forbidden subcommands before spawning.

    `env`, if given, replaces the environment, as in subprocess.run.
    """
    sub = _subcommand(args)
    if sub in _FORBIDDEN_SUBCOMMANDS:
        raise ForbiddenGitCommand(
            f"Refused: 'git {sub}' is blocked by Polyphony. Publishing work is "
            f"the operator's decision, not Polyphony's."
        )
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
