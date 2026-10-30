from __future__ import annotations

import subprocess
from typing import List

# git global flags that take the next token as their value
_FLAGS_WITH_VALUES = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix",
}

_FORBIDDEN_SUBCOMMANDS = {"push"}


class ForbiddenGitCommand(Exception):
    pass


def _subcommand(args: List[str]) -> str | None:
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
