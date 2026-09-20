"""State and persistence management for orchestrated tasks."""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml

from executors.base import ExecutorResult

logger = logging.getLogger("polyphony.state")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STALE = "stale"
    RECOVERING = "recovering"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    CANCELLED = "cancelled"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"


class IterationRecord(BaseModel):
    iteration_id: str = Field(default_factory=lambda: f"iter-{uuid.uuid4().hex[:8]}")
    iteration_number: int
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    reasoner_used: str = "claude"
    lead_decision: Dict[str, Any] = Field(default_factory=dict)
    executor_used: str = ""
    instruction: str = ""
    execution_result: Optional[ExecutorResult] = None
    tests_passed: Optional[bool] = None
    test_output: Optional[str] = None
    safety_passed: bool = True
    safety_message: Optional[str] = None
    files_changed: List[str] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


from orchestrator.task_types import TaskType, classify_task_type, get_workflow_definition


class TaskState(BaseModel):
    task_id: str
    execution_id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:8]}")
    project_name: str
    project_path: str
    goal: str
    task_type: TaskType = TaskType.FEATURE
    workflow_stages: List[str] = Field(default_factory=list)
    read_only: bool = False
    status: TaskStatus = TaskStatus.PENDING
    start_time: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    end_time: Optional[str] = None
    last_heartbeat: Optional[str] = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    pid: Optional[int] = Field(default_factory=os.getpid)
    current_iteration: int = 0
    max_iterations: int = 10
    iterations: List[IterationRecord] = Field(default_factory=list)
    all_files_changed: List[str] = Field(default_factory=list)
    final_summary: Optional[str] = None
    error: Optional[str] = None
    lead_session_id: Optional[str] = None
    executor_sessions: Dict[str, str] = Field(default_factory=dict)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    detailed_usage: Dict[str, Any] = Field(default_factory=dict)
    idempotency_keys: List[str] = Field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    approval_history: List[Dict[str, Any]] = Field(default_factory=list)


class StateManager:
    """Manages persistent disk state for tasks under tasks/<project>/<task_id>/."""

    def __init__(self, root_dir: str | Path = "."):
        self.root_dir = Path(root_dir).resolve()
        self.tasks_base = self.root_dir / "tasks"

    def _get_task_dir(self, project_name: str, task_id: str) -> Path:
        return self.tasks_base / project_name / task_id

    def acquire_task_lock(self, project_name: str, task_id: str) -> Path:
        """Acquires process concurrency lock for a task. Raises RuntimeError if already held."""
        task_dir = self._get_task_dir(project_name, task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        lock_file = task_dir / "task.lock"

        if lock_file.exists():
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    lock_info = json.load(f)
                locked_pid = lock_info.get("pid")
                # Check if locked_pid is currently alive
                if locked_pid and locked_pid != os.getpid():
                    try:
                        os.kill(locked_pid, 0)
                        # Process is alive!
                        raise RuntimeError(f"Task '{task_id}' is locked by active process PID {locked_pid}")
                    except (ProcessLookupError, PermissionError):
                        # Dead process or no permissions, lock is stale and can be reclaimed
                        pass
            except json.JSONDecodeError:
                pass

        lock_data = {
            "pid": os.getpid(),
            "acquired_at": datetime.datetime.now().isoformat(),
            "task_id": task_id,
        }
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, indent=2)
        return lock_file

    def release_task_lock(self, project_name: str, task_id: str) -> None:
        """Releases the concurrency lock for a task."""
        task_dir = self._get_task_dir(project_name, task_id)
        lock_file = task_dir / "task.lock"
        if lock_file.exists():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to remove lockfile {lock_file}: {e}")

    def create_task(
        self,
        project_name: str,
        project_path: str,
        goal: str,
        read_only: bool = False,
        max_iterations: int = 10,
        task_type: Optional[Union[TaskType, str]] = None,
    ) -> TaskState:
        now_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"task-{now_str}-{uuid.uuid4().hex[:6]}"

        resolved_type = (
            TaskType.from_str(task_type)
            if task_type
            else classify_task_type(goal)
        )
        workflow_def = get_workflow_definition(resolved_type)
        effective_read_only = read_only or workflow_def.read_only_default

        state = TaskState(
            task_id=task_id,
            project_name=project_name,
            project_path=project_path,
            goal=goal,
            task_type=resolved_type,
            workflow_stages=workflow_def.stages,
            read_only=effective_read_only,
            max_iterations=max_iterations,
            pid=os.getpid(),
            last_heartbeat=datetime.datetime.now().isoformat(),
        )

        task_dir = self._get_task_dir(project_name, task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "iterations").mkdir(exist_ok=True)
        (task_dir / "logs").mkdir(exist_ok=True)

        # Write initial task.yaml
        with open(task_dir / "task.yaml", "w", encoding="utf-8") as f:
            yaml.dump(
                {
                    "task_id": state.task_id,
                    "execution_id": state.execution_id,
                    "project_name": state.project_name,
                    "project_path": state.project_path,
                    "goal": state.goal,
                    "task_type": state.task_type.value,
                    "workflow_stages": state.workflow_stages,
                    "read_only": state.read_only,
                    "max_iterations": state.max_iterations,
                    "start_time": state.start_time,
                },
                f,
                sort_keys=False,
            )

        self.save_state(state)
        return state

    def save_state(self, state: TaskState) -> None:
        """Atomically saves task state with automatic backup to prevent corruption."""
        try:
            task_dir = self._get_task_dir(state.project_name, state.task_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            state_file = task_dir / "state.json"
            tmp_file = task_dir / "state.json.tmp"
            bak_file = task_dir / "state.json.bak"

            # Exclude iterations list to avoid O(N^2) I/O explosion; individual iterations are saved under iterations/
            state_data = state.model_dump(exclude={"iterations"})

            # Write to temp file first
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Rotate existing to backup
            if state_file.exists():
                shutil.copy2(state_file, bak_file)

            # Atomic rename
            tmp_file.replace(state_file)
        except Exception as e:
            logger.warning(f"Failed to save state for task {state.task_id}: {e}")

    def update_heartbeat(self, state: TaskState) -> None:
        """Updates task heartbeat timestamp and process PID."""
        state.last_heartbeat = datetime.datetime.now().isoformat()
        state.pid = os.getpid()
        self.save_state(state)

    def check_and_record_idempotency_key(self, state: TaskState, key: str) -> bool:
        """Checks if idempotency key has already been executed. Returns False if already seen, True if new."""
        if key in state.idempotency_keys:
            logger.warning(f"Duplicate command blocked by idempotency key: {key}")
            return False
        state.idempotency_keys.append(key)
        self.save_state(state)
        return True

    def check_stale_tasks(
        self,
        project_name: str,
        heartbeat_timeout_seconds: int = 60,
    ) -> List[TaskState]:
        """Detects tasks marked RUNNING that have no active process or whose heartbeat expired."""
        tasks = self.list_tasks(project_name)
        stale_tasks = []
        now = datetime.datetime.now()

        for st in tasks:
            if st.status == TaskStatus.RUNNING:
                is_stale = False

                # 1. Check process PID
                if st.pid:
                    try:
                        os.kill(st.pid, 0)
                    except (ProcessLookupError, PermissionError):
                        # Process died
                        is_stale = True

                # 2. Check heartbeat age
                if st.last_heartbeat:
                    try:
                        hb_dt = datetime.datetime.fromisoformat(st.last_heartbeat)
                        if (now - hb_dt).total_seconds() > heartbeat_timeout_seconds:
                            is_stale = True
                    except Exception:
                        pass
                else:
                    is_stale = True

                if is_stale:
                    st.status = TaskStatus.STALE
                    self.save_state(st)
                    stale_tasks.append(st)

        return stale_tasks

    def record_iteration(self, state: TaskState, record: IterationRecord) -> None:
        try:
            state.iterations.append(record)
            state.current_iteration = len(state.iterations)
            for f in record.files_changed:
                if f not in state.all_files_changed:
                    state.all_files_changed.append(f)

            task_dir = self._get_task_dir(state.project_name, state.task_id)
            iter_dir = task_dir / "iterations"
            iter_dir.mkdir(parents=True, exist_ok=True)
            iter_file = iter_dir / f"iteration_{record.iteration_number:02d}.json"
            with open(iter_file, "w", encoding="utf-8") as f:
                f.write(record.model_dump_json(indent=2))

            self.update_heartbeat(state)
        except Exception as e:
            logger.warning(f"Failed to record iteration {record.iteration_number} for task {state.task_id}: {e}")

    def complete_task(
        self,
        state: TaskState,
        status: TaskStatus,
        summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            state.status = status
            state.end_time = datetime.datetime.now().isoformat()
            if summary:
                state.final_summary = summary
            if error:
                state.error = error
            self.save_state(state)
            self.release_task_lock(state.project_name, state.task_id)
        except Exception as e:
            logger.warning(f"Failed to complete task {state.task_id}: {e}")

    def load_state(self, project_name: str, task_id: str) -> Optional[TaskState]:
        """Loads state, recovering from state.json.bak or iterations/ if state is corrupted."""
        task_dir = self._get_task_dir(project_name, task_id)
        state_file = task_dir / "state.json"
        bak_file = task_dir / "state.json.bak"

        data = None
        # Attempt primary state file
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Primary state file corrupted for {task_id}: {e}. Trying backup...")

        # Attempt backup file if primary failed
        if data is None and bak_file.exists():
            try:
                with open(bak_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"Successfully recovered {task_id} state from backup file.")
            except Exception as e:
                logger.warning(f"Backup state file also corrupted for {task_id}: {e}")

        # Attempt reconstruction from task.yaml and iterations/ if both JSON files failed
        if data is None:
            task_yaml_file = task_dir / "task.yaml"
            if task_yaml_file.exists():
                try:
                    with open(task_yaml_file, "r", encoding="utf-8") as f:
                        yaml_meta = yaml.safe_load(f) or {}
                    data = {
                        "task_id": yaml_meta.get("task_id", task_id),
                        "project_name": yaml_meta.get("project_name", project_name),
                        "project_path": yaml_meta.get("project_path", str(self.root_dir / project_name)),
                        "goal": yaml_meta.get("goal", ""),
                        "read_only": yaml_meta.get("read_only", False),
                        "max_iterations": yaml_meta.get("max_iterations", 10),
                        "status": TaskStatus.RECOVERING.value,
                        "start_time": yaml_meta.get("start_time", datetime.datetime.now().isoformat()),
                    }
                    logger.info(f"Reconstructed basic state from task.yaml for {task_id}")
                except Exception as e:
                    logger.error(f"Cannot reconstruct state for {task_id}: {e}")
                    return None
            else:
                return None

        # Reconstruct iterations from iterations/ directory if omitted from state.json
        if "iterations" not in data or not data["iterations"]:
            data["iterations"] = []
            iter_dir = task_dir / "iterations"
            if iter_dir.exists():
                for iter_file in sorted(iter_dir.glob("iteration_*.json")):
                    try:
                        with open(iter_file, "r", encoding="utf-8") as f_iter:
                            it_data = json.load(f_iter)
                            data["iterations"].append(it_data)
                    except Exception:
                        pass

        try:
            return TaskState.model_validate(data)
        except Exception as e:
            logger.error(f"Pydantic validation failed for task state {task_id}: {e}")
            return None

    def list_tasks(self, project_name: str) -> List[TaskState]:
        proj_dir = self.tasks_base / project_name
        if not proj_dir.exists():
            return []
        tasks = []
        for task_dir in proj_dir.iterdir():
            if task_dir.is_dir() and ((task_dir / "state.json").exists() or (task_dir / "task.yaml").exists()):
                st = self.load_state(project_name, task_dir.name)
                if st:
                    tasks.append(st)
        return sorted(tasks, key=lambda t: t.start_time, reverse=True)

    def list_all_tasks(self) -> List[TaskState]:
        """Lists all tasks across all projects."""
        if not self.tasks_base.exists():
            return []
        all_tasks = []
        for proj_dir in self.tasks_base.iterdir():
            if proj_dir.is_dir():
                all_tasks.extend(self.list_tasks(proj_dir.name))
        return sorted(all_tasks, key=lambda t: t.start_time, reverse=True)

    def find_task(self, task_id: str, project_name: Optional[str] = None) -> Optional[TaskState]:
        """Find a task by task_id across all projects if project_name not specified."""
        if project_name:
            return self.load_state(project_name, task_id)
        if not self.tasks_base.exists():
            return None
        for proj_dir in self.tasks_base.iterdir():
            if proj_dir.is_dir():
                st = self.load_state(proj_dir.name, task_id)
                if st:
                    return st
        return None
