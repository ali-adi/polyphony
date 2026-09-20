"""One task's isolated workspace: a provisioned git worktree outside the repo.

Worktrees deliberately live outside the target repository. Placing them
inside leaves untracked directories in the working tree, where an agent
running `git add -A` could commit a second copy of the repo into itself.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from orchestrator.guard import run_git

DEFAULT_ROOT = Path.home() / ".polyphony"


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
