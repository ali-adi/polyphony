"""Crash recovery and process disappearance inspection engine for Polyphony."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.state import StateManager, TaskState, TaskStatus


@dataclass
class WorkingTreeInspection:
    """Inspection report of repository state after process interruption."""
    modified_files: List[str]
    untracked_files: List[str]
    is_dirty: bool
    git_head: Optional[str] = None


@dataclass
class RecoveryAssessment:
    """Recovery assessment indicating recommended action and current workspace status."""
    task_id: str
    previous_status: TaskStatus
    recommended_action: str  # COMPLETE, RESUME, RECOVER, ASK_HUMAN, ROLLBACK
    reason: str
    working_tree: WorkingTreeInspection
    tests_passing: Optional[bool] = None
    target_files_satisfied: bool = False


class CrashRecoveryEngine:
    """Inspects interrupted or crashed tasks and determines recovery actions."""

    def __init__(self, root_dir: str | Path = "."):
        self.root_dir = Path(root_dir).resolve()
        self.state_manager = StateManager(self.root_dir)

    def inspect_working_tree(self, workspace_path: Path) -> WorkingTreeInspection:
        """Inspects git status of the project directory."""
        if not (workspace_path / ".git").exists():
            return WorkingTreeInspection(
                modified_files=[],
                untracked_files=[],
                is_dirty=False,
                git_head=None,
            )

        try:
            status_out = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()

            modified = []
            untracked = []
            for line in status_out.splitlines():
                if not line:
                    continue
                code = line[:2]
                path = line[3:].strip()
                if "??" in code:
                    untracked.append(path)
                else:
                    modified.append(path)

            head_out = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()

            return WorkingTreeInspection(
                modified_files=modified,
                untracked_files=untracked,
                is_dirty=bool(modified or untracked),
                git_head=head_out or None,
            )
        except Exception:
            return WorkingTreeInspection(
                modified_files=[],
                untracked_files=[],
                is_dirty=False,
                git_head=None,
            )

    def assess_task(self, project_name: str, task_id: str) -> RecoveryAssessment:
        """Determines whether an interrupted task completed, should be resumed, or needs human input."""
        state = self.state_manager.load_state(project_name, task_id)
        if not state:
            raise ValueError(f"Task '{task_id}' not found for project '{project_name}'")

        workspace = Path(state.project_path)
        tree = self.inspect_working_tree(workspace)

        # Check if process is alive
        process_alive = False
        if state.pid and state.status == TaskStatus.RUNNING:
            try:
                os.kill(state.pid, 0)
                process_alive = True
            except (ProcessLookupError, PermissionError):
                process_alive = False

        # If already terminal, return as-is
        if state.status in (TaskStatus.COMPLETED, TaskStatus.ABORTED, TaskStatus.FAILED):
            return RecoveryAssessment(
                task_id=task_id,
                previous_status=state.status,
                recommended_action="NONE",
                reason=f"Task is already in terminal state: {state.status.value}",
                working_tree=tree,
            )

        # Process disappeared or was stale
        last_iteration = state.iterations[-1] if state.iterations else None
        target_files_changed = bool(state.all_files_changed)

        # Check if tests pass deterministically if test files exist
        tests_passing: Optional[bool] = None
        test_files = list(workspace.glob("**/test_*.py"))
        if test_files:
            try:
                test_proc = subprocess.run(
                    ["pytest", "-q"],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                tests_passing = (test_proc.returncode == 0)
            except Exception:
                tests_passing = None

        # Determine recovery action
        if last_iteration and last_iteration.execution_result and last_iteration.execution_result.success:
            if tests_passing is True:
                rec_action = "COMPLETE"
                reason = "Interrupted execution had successful changes and all test assertions pass."
            elif tests_passing is False:
                rec_action = "RESUME"
                reason = "Working tree has modifications, but tests are currently failing; further iteration needed."
            elif target_files_changed:
                rec_action = "COMPLETE"
                reason = "Required target files were modified prior to process termination."
            else:
                rec_action = "RESUME"
                reason = "Task was interrupted mid-step; resume execution from last saved iteration."
        elif not tree.is_dirty and state.current_iteration == 0:
            rec_action = "RESUME"
            reason = "Task was halted before first iteration made any changes."
        elif tree.is_dirty and tests_passing is False:
            rec_action = "ASK_HUMAN"
            reason = "Repository has unverified dirty changes with failing tests after interruption."
        else:
            rec_action = "RESUME"
            reason = "Execution state intact; safe to resume next iteration."

        return RecoveryAssessment(
            task_id=task_id,
            previous_status=state.status,
            recommended_action=rec_action,
            reason=reason,
            working_tree=tree,
            tests_passing=tests_passing,
            target_files_satisfied=target_files_changed,
        )

    def apply_recovery(
        self,
        project_name: str,
        task_id: str,
        assessment: Optional[RecoveryAssessment] = None,
    ) -> TaskState:
        """Applies the recommended recovery action to the persisted task state."""
        if assessment is None:
            assessment = self.assess_task(project_name, task_id)

        state = self.state_manager.load_state(project_name, task_id)
        if not state:
            raise ValueError(f"Task '{task_id}' not found for project '{project_name}'")

        if assessment.recommended_action == "COMPLETE":
            state.status = TaskStatus.COMPLETED
            state.final_summary = f"Recovered after crash: {assessment.reason}"
        elif assessment.recommended_action == "ASK_HUMAN":
            state.status = TaskStatus.NEEDS_HUMAN
        elif assessment.recommended_action == "RESUME":
            state.status = TaskStatus.RECOVERING
        elif assessment.recommended_action == "ROLLBACK":
            state.status = TaskStatus.FAILED
            state.error = f"Recovery failed: {assessment.reason}"

        # Clean up stale locks
        self.state_manager.release_task_lock(project_name, task_id)
        self.state_manager.save_state(state)
        return state
