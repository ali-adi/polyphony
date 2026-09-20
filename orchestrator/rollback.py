"""Safe rollback engine that distinguishes pre-existing user work from Polyphony changes."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml


def _compute_file_hash(file_path: Path) -> Optional[str]:
    """Compute SHA-256 hash of a file if it exists and is readable."""
    if not file_path.is_file():
        return None
    try:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


@dataclass
class WorkspaceBaseline:
    """Pre-execution baseline recording exact state of the repository."""
    cwd: str
    git_root: Optional[str]
    head_commit: Optional[str]
    branch_or_worktree: Optional[str]
    tracked_diff: str
    untracked_files: List[str]
    untracked_hashes: Dict[str, str]
    tracked_modified_files: List[str]
    file_snapshots: Dict[str, str]  # rel_path -> backup file path
    snapshot_dir: Optional[str] = None


@dataclass
class RollbackReport:
    """Detailed report of what changes were safely reverted vs preserved."""
    reverted_files: List[str]
    deleted_untracked_files: List[str]
    preserved_user_files: List[str]
    success: bool
    error: Optional[str] = None


class SafeRollbackManager:
    """Guarantees rollback removes ONLY Polyphony changes while strictly preserving user work."""

    def __init__(self, storage_root: Optional[Path] = None):
        self.storage_root = Path(storage_root) if storage_root else Path(".polyphony_checkpoints")

    def _get_git_info(self, cwd: Path) -> Dict[str, Any]:
        git_root = None
        head_commit = None
        branch = None
        tracked_diff = ""
        untracked: List[str] = []
        modified: List[str] = []

        try:
            res_root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
            if res_root.returncode == 0:
                git_root = res_root.stdout.strip()

            if git_root:
                # HEAD commit
                res_head = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=git_root,
                    capture_output=True,
                    text=True,
                )
                head_commit = res_head.stdout.strip() if res_head.returncode == 0 else None

                # Branch / worktree
                res_branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=git_root,
                    capture_output=True,
                    text=True,
                )
                branch = res_branch.stdout.strip() if res_branch.returncode == 0 else None

                # Tracked diff against HEAD
                res_diff = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=git_root,
                    capture_output=True,
                    text=True,
                )
                tracked_diff = res_diff.stdout if res_diff.returncode == 0 else ""

                # Status porcelain
                res_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=git_root,
                    capture_output=True,
                    text=True,
                )
                if res_status.returncode == 0:
                    for line in res_status.stdout.splitlines():
                        if not line:
                            continue
                        code = line[:2]
                        path = line[3:].strip()
                        if "??" in code:
                            untracked.append(path)
                        else:
                            modified.append(path)
        except Exception:
            pass

        return {
            "git_root": git_root,
            "head_commit": head_commit,
            "branch": branch,
            "tracked_diff": tracked_diff,
            "untracked_files": untracked,
            "modified_files": modified,
        }

    def record_baseline(
        self,
        cwd: str | Path,
        relevant_files: Optional[List[str]] = None,
    ) -> WorkspaceBaseline:
        """Captures full repository baseline and snapshots relevant files before execution."""
        cwd_path = Path(cwd).resolve()
        git_info = self._get_git_info(cwd_path)
        git_root = Path(git_info["git_root"]) if git_info["git_root"] else cwd_path

        # Create temporary snapshot directory in temp dir to isolate from workspace
        import tempfile
        snapshot_dir = Path(tempfile.mkdtemp(prefix="polyphony_snap_"))

        untracked_hashes: Dict[str, str] = {}
        for u_file in git_info["untracked_files"]:
            if u_file.startswith(".polyphony"):
                continue
            abs_p = git_root / u_file
            h = _compute_file_hash(abs_p)
            if h:
                untracked_hashes[u_file] = h

        # Determine which files to snapshot (relevant files + modified + untracked)
        to_snapshot = set(relevant_files or [])
        to_snapshot.update(git_info["modified_files"])

        file_snapshots: Dict[str, str] = {}
        for rel_file in to_snapshot:
            src = git_root / rel_file
            if src.is_file():
                dest = snapshot_dir / rel_file
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                file_snapshots[rel_file] = str(dest)

        return WorkspaceBaseline(
            cwd=str(cwd_path),
            git_root=str(git_root) if git_info["git_root"] else None,
            head_commit=git_info["head_commit"],
            branch_or_worktree=git_info["branch"],
            tracked_diff=git_info["tracked_diff"],
            untracked_files=git_info["untracked_files"],
            untracked_hashes=untracked_hashes,
            tracked_modified_files=git_info["modified_files"],
            file_snapshots=file_snapshots,
            snapshot_dir=str(snapshot_dir),
        )

    def calculate_delta(self, baseline: WorkspaceBaseline) -> Dict[str, Any]:
        """Calculates exact delta between baseline and current workspace state."""
        cwd_path = Path(baseline.cwd)
        git_root = Path(baseline.git_root) if baseline.git_root else cwd_path
        current_info = self._get_git_info(cwd_path)

        # 1. Newly created untracked files by Polyphony
        baseline_untracked_set = set(baseline.untracked_files)
        current_untracked_set = set(current_info["untracked_files"])
        new_untracked = sorted(list(current_untracked_set - baseline_untracked_set))

        # 2. Tracked files modified since baseline
        modified_by_polyphony = []
        for mod_file in current_info["modified_files"]:
            snap_path = baseline.file_snapshots.get(mod_file)
            current_abs = git_root / mod_file
            current_hash = _compute_file_hash(current_abs)
            if snap_path:
                snap_hash = _compute_file_hash(Path(snap_path))
                if current_hash != snap_hash:
                    modified_by_polyphony.append(mod_file)
            else:
                # File wasn't modified in baseline -> Polyphony modified it
                modified_by_polyphony.append(mod_file)

        return {
            "new_untracked_files": new_untracked,
            "modified_by_polyphony": modified_by_polyphony,
            "user_preexisting_untracked": list(baseline_untracked_set),
            "user_preexisting_modified": baseline.tracked_modified_files,
        }

    def safe_rollback(self, baseline: WorkspaceBaseline) -> RollbackReport:
        """Reverts ONLY Polyphony changes, preserving all pre-existing user uncommitted changes."""
        cwd_path = Path(baseline.cwd)
        git_root = Path(baseline.git_root) if baseline.git_root else cwd_path
        delta = self.calculate_delta(baseline)

        reverted: List[str] = []
        deleted_untracked: List[str] = []
        preserved: List[str] = []

        try:
            # 1. Delete ONLY newly created untracked files
            for new_untracked in delta["new_untracked_files"]:
                target = git_root / new_untracked
                if target.is_file():
                    target.unlink()
                    deleted_untracked.append(new_untracked)
                elif target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                    deleted_untracked.append(new_untracked)

            # Pre-existing untracked files are preserved
            for user_untracked in delta["user_preexisting_untracked"]:
                preserved.append(user_untracked)

            # 2. Revert tracked files modified by Polyphony
            for mod_file in delta["modified_by_polyphony"]:
                target = git_root / mod_file
                if mod_file in baseline.file_snapshots:
                    # Restore pre-execution snapshot (exact user edits preserved!)
                    snap_src = Path(baseline.file_snapshots[mod_file])
                    if snap_src.is_file():
                        shutil.copy2(snap_src, target)
                        reverted.append(mod_file)
                else:
                    # File was clean in baseline; restore using git checkout
                    res = subprocess.run(
                        ["git", "checkout", "HEAD", "--", mod_file],
                        cwd=str(git_root),
                        capture_output=True,
                        text=True,
                    )
                    if res.returncode == 0:
                        reverted.append(mod_file)

            # Record preserved user modified files that were not touched
            for user_mod in delta["user_preexisting_modified"]:
                if user_mod not in reverted:
                    preserved.append(user_mod)

            return RollbackReport(
                reverted_files=reverted,
                deleted_untracked_files=deleted_untracked,
                preserved_user_files=sorted(list(set(preserved))),
                success=True,
            )
        except Exception as e:
            return RollbackReport(
                reverted_files=reverted,
                deleted_untracked_files=deleted_untracked,
                preserved_user_files=preserved,
                success=False,
                error=str(e),
            )
        finally:
            self.safe_release(baseline)

    def safe_release(self, baseline: WorkspaceBaseline) -> None:
        """Removes the temporary snapshot directory."""
        if baseline.snapshot_dir:
            shutil.rmtree(baseline.snapshot_dir, ignore_errors=True)
