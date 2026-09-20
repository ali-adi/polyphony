"""One task's isolated workspace: a provisioned git worktree outside the repo.

Worktrees deliberately live outside the target repository. Placing them
inside leaves untracked directories in the working tree, where an agent
running `git add -A` could commit a second copy of the repo into itself.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrator.guard import run_git

DEFAULT_ROOT = Path.home() / ".polyphony"


class ProvisionError(Exception):
    """Raised when a workspace cannot be fully provisioned.

    Always fatal. A partially provisioned workspace produces test failures
    unrelated to the agent's work, which the orchestrator would then treat
    as real regressions.
    """


@dataclass
class Workspace:
    task_id: str
    project: str
    repo: Path
    path: Path
    branch: str

    @classmethod
    def create(
        cls,
        project: str,
        task_id: str,
        repo: str | Path,
        root: Path | None = None,
    ) -> "Workspace":
        repo_path = Path(repo).resolve()
        base = Path(root) if root is not None else DEFAULT_ROOT
        wt_path = base / "worktrees" / project / task_id
        branch = f"polyphony/{task_id}"

        wt_path.parent.mkdir(parents=True, exist_ok=True)

        res = run_git(["worktree", "add", "-b", branch, str(wt_path)], cwd=str(repo_path))
        if res.returncode != 0:
            raise RuntimeError(
                f"Could not create worktree for {task_id} at {wt_path}: {res.stderr.strip()}"
            )

        return cls(
            task_id=task_id,
            project=project,
            repo=repo_path,
            path=wt_path,
            branch=branch,
        )

    def remove(self, delete_branch: bool = True) -> None:
        """Remove the worktree and, by default, its branch — leaving no trace."""
        run_git(["worktree", "remove", "--force", str(self.path)], cwd=str(self.repo))
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        if delete_branch:
            run_git(["branch", "-D", self.branch], cwd=str(self.repo))

    def provision(self, entries: list[dict]) -> list[str]:
        """Materialize gitignored paths the project declares it needs.

        `clone` uses APFS copy-on-write: near-instant, no disk cost until
        written, and genuinely isolated. `link` symlinks instead — it is a
        hole in the isolation boundary, since writes reach the real path,
        and exists only for paths too large to clone.
        """
        provisioned: list[str] = []
        for entry in entries:
            rel = str(entry.get("path", "")).strip()
            mode = str(entry.get("mode", "clone")).strip()

            if not rel:
                raise ProvisionError("Provision entry is missing a 'path'.")
            if rel.startswith("/") or ".." in Path(rel).parts:
                raise ProvisionError(
                    f"Refusing to provision {rel!r}: paths must be relative to the repo root."
                )

            src = (self.repo / rel).resolve()
            dst = (self.path / rel).resolve()

            if not src.exists():
                raise ProvisionError(
                    f"Cannot provision {rel!r}: {src} does not exist in {self.repo}."
                )

            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                raise ProvisionError(f"Cannot provision {rel!r}: {dst} already exists.")

            if mode == "link":
                dst.symlink_to(src)
            elif mode == "clone":
                res = subprocess.run(
                    ["cp", "-Rc", str(src), str(dst)],
                    capture_output=True, text=True,
                )
                if res.returncode != 0:
                    # -c (clonefile) needs APFS; fall back to a plain recursive copy.
                    res = subprocess.run(
                        ["cp", "-R", str(src), str(dst)],
                        capture_output=True, text=True,
                    )
                    if res.returncode != 0:
                        raise ProvisionError(
                            f"Cannot provision {rel!r}: {res.stderr.strip()}"
                        )
            else:
                raise ProvisionError(
                    f"Unknown provision mode {mode!r} for {rel!r}; expected 'clone' or 'link'."
                )

            provisioned.append(rel)
        return provisioned
