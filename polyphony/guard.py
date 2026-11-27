from __future__ import annotations

import functools
import os
import shutil
import subprocess
from typing import List

# git global flags that take the next token as their value
_FLAGS_WITH_VALUES = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix",
}

_FORBIDDEN_SUBCOMMANDS = {"push"}


@functools.cache
def git_binary() -> str:
    found = shutil.which("git") or "git"
    # /usr/bin/git is Apple's xcrun shim, which adds a lookup to every spawn
    if os.path.realpath(found) == "/usr/bin/git":
        try:
            res = subprocess.run(["xcrun", "--find", "git"], capture_output=True, text=True)
        except OSError:
            return found
        real = res.stdout.strip()
        if res.returncode == 0 and os.access(real, os.X_OK):
            return real
    return found


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
        [git_binary(), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
