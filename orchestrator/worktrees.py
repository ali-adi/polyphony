"""Git worktree isolation for parallel task implementation and investigation (Section 33).

Section 33: Worktree-Based Parallelism
Example:
main working tree
      │
      ├── worktree A → implementation
      ├── worktree B → alternative implementation
      └── worktree C → investigation
                         ↓
                     reviewer
                         ↓
                    merge decision

Polyphony remains strictly careful about the user's existing working tree.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("polyphony.worktrees")


@dataclass
class WorktreeInfo:
    id: str
    branch: str
    path: Path
    purpose: str
    created_at: float
    is_merged: bool = False


class WorktreeManager:
    """Manages isolated git worktrees for parallel agents without dirtying the user's working tree."""

    def __init__(self, repo_dir: Union[str, Path]):
        self.repo_dir = Path(repo_dir).resolve()
        self._worktrees: Dict[str, WorktreeInfo] = {}

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        target_cwd = cwd or self.repo_dir
        return subprocess.run(
            ["git"] + args,
            cwd=target_cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    def create_worktree(
        self,
        purpose: str,
        base_ref: str = "HEAD",
        custom_branch: Optional[str] = None,
        custom_dir: Optional[Path] = None,
    ) -> WorktreeInfo:
        """Creates an isolated git worktree for safe parallel implementation."""
        wt_id = f"wt-{uuid.uuid4().hex[:8]}"
        branch_name = custom_branch or f"polyphony/{wt_id}-{purpose}"

        if custom_dir:
            wt_path = Path(custom_dir).resolve()
        else:
            wt_path = self.repo_dir / ".polyphony" / "worktrees" / wt_id

        wt_path.parent.mkdir(parents=True, exist_ok=True)

        res = self._run_git(["worktree", "add", "-b", branch_name, str(wt_path), base_ref])
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create git worktree at {wt_path}: {res.stderr.strip()}")

        info = WorktreeInfo(
            id=wt_id,
            branch=branch_name,
            path=wt_path,
            purpose=purpose,
            created_at=os.path.getmtime(wt_path),
        )
        self._worktrees[wt_id] = info
        logger.info(f"Created worktree '{wt_id}' ({purpose}) on branch '{branch_name}' at {wt_path}")
        return info

    def list_worktrees(self) -> List[WorktreeInfo]:
        return list(self._worktrees.values())

    def get_worktree(self, wt_id: str) -> Optional[WorktreeInfo]:
        return self._worktrees.get(wt_id)

    def remove_worktree(self, wt_id: str, delete_branch: bool = True) -> bool:
        """Safely removes a worktree and optionally deletes its temporary branch."""
        info = self._worktrees.get(wt_id)
        if not info:
            return False

        res = self._run_git(["worktree", "remove", "--force", str(info.path)])
        if res.returncode != 0 and info.path.exists():
            shutil.rmtree(info.path, ignore_errors=True)
            self._run_git(["worktree", "prune"])

        if delete_branch:
            self._run_git(["branch", "-D", info.branch])

        del self._worktrees[wt_id]
        logger.info(f"Cleaned up worktree '{wt_id}'")
        return True

    def merge_decision(
        self,
        chosen_wt_id: str,
        target_branch: Optional[str] = None,
        commit_msg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Merges reviewer-selected worktree into target branch and cleans up other candidate worktrees.

        Section 33:
        worktree A -> implementation
        worktree B -> alternative
        reviewer -> merge decision
        """
        chosen = self._worktrees.get(chosen_wt_id)
        if not chosen:
            raise ValueError(f"Selected worktree '{chosen_wt_id}' does not exist")

        # 1. Determine target branch
        if not target_branch:
            branch_res = self._run_git(["branch", "--show-current"])
            target_branch = branch_res.stdout.strip() or "main"

        # 2. Merge chosen branch
        msg = commit_msg or f"Merge approved worktree {chosen.purpose} ({chosen.id})"
        res = self._run_git(["merge", chosen.branch, "-m", msg])
        merge_success = res.returncode == 0
        merge_output = res.stdout if merge_success else res.stderr

        chosen.is_merged = merge_success

        # 3. Clean up non-chosen candidate worktrees
        other_ids = [wid for wid in list(self._worktrees.keys()) if wid != chosen_wt_id]
        for wid in other_ids:
            self.remove_worktree(wid, delete_branch=True)

        return {
            "success": merge_success,
            "chosen_worktree": chosen.id,
            "branch": chosen.branch,
            "target_branch": target_branch,
            "message": merge_output.strip(),
            "cleaned_up_candidates": other_ids,
        }

    def cleanup_all(self) -> None:
        """Clean up all active worktrees and prune."""
        for wid in list(self._worktrees.keys()):
            self.remove_worktree(wid, delete_branch=True)
        self._run_git(["worktree", "prune"])
