"""State and persistence management for orchestrated tasks."""

from __future__ import annotations

import datetime
import json
import logging
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
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    NEEDS_HUMAN = "needs_human"


class IterationRecord(BaseModel):
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


class TaskState(BaseModel):
    task_id: str
    project_name: str
    project_path: str
    goal: str
    read_only: bool = False
    status: TaskStatus = TaskStatus.PENDING
    start_time: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    end_time: Optional[str] = None
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


class StateManager:
    """Manages persistent disk state for tasks under tasks/<project>/<task_id>/."""

    def __init__(self, root_dir: str | Path = "."):
        self.root_dir = Path(root_dir).resolve()
        self.tasks_base = self.root_dir / "tasks"

    def _get_task_dir(self, project_name: str, task_id: str) -> Path:
        return self.tasks_base / project_name / task_id

    def create_task(
        self,
        project_name: str,
        project_path: str,
        goal: str,
        read_only: bool = False,
        max_iterations: int = 10,
    ) -> TaskState:
        now_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"task-{now_str}-{uuid.uuid4().hex[:6]}"

        state = TaskState(
            task_id=task_id,
            project_name=project_name,
            project_path=project_path,
            goal=goal,
            read_only=read_only,
            max_iterations=max_iterations,
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
                    "project_name": state.project_name,
                    "project_path": state.project_path,
                    "goal": state.goal,
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
        try:
            task_dir = self._get_task_dir(state.project_name, state.task_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            state_file = task_dir / "state.json"
            # Exclude iterations list to avoid O(N^2) I/O explosion; individual iterations are saved under iterations/
            state_data = state.model_dump(exclude={"iterations"})
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state for task {state.task_id}: {e}")

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

            self.save_state(state)
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
        except Exception as e:
            logger.warning(f"Failed to complete task {state.task_id}: {e}")

    def load_state(self, project_name: str, task_id: str) -> Optional[TaskState]:
        try:
            task_dir = self._get_task_dir(project_name, task_id)
            state_file = task_dir / "state.json"
            if not state_file.exists():
                return None
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

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

            return TaskState.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to load state for task {task_id}: {e}")
            return None

    def list_tasks(self, project_name: str) -> List[TaskState]:
        proj_dir = self.tasks_base / project_name
        if not proj_dir.exists():
            return []
        tasks = []
        for task_dir in proj_dir.iterdir():
            if task_dir.is_dir() and (task_dir / "state.json").exists():
                st = self.load_state(project_name, task_dir.name)
                if st:
                    tasks.append(st)
        return sorted(tasks, key=lambda t: t.start_time, reverse=True)
