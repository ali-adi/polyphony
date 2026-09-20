"""Formal Event Model and durable JSONL event streaming for Polyphony (Section 10)."""

from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class EventType(str, Enum):
    """Standardized event types in the Polyphony lifecycle."""
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PAUSED = "TASK_PAUSED"
    TASK_RESUMED = "TASK_RESUMED"

    LEAD_STARTED = "LEAD_STARTED"
    LEAD_DECISION = "LEAD_DECISION"

    EXECUTOR_SELECTED = "EXECUTOR_SELECTED"
    EXECUTOR_STARTED = "EXECUTOR_STARTED"
    EXECUTOR_OUTPUT = "EXECUTOR_OUTPUT"
    EXECUTOR_FINISHED = "EXECUTOR_FINISHED"

    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_FINISHED = "VERIFICATION_FINISHED"

    REVIEW_STARTED = "REVIEW_STARTED"
    REVIEW_FINISHED = "REVIEW_FINISHED"

    ITERATION_STARTED = "ITERATION_STARTED"
    ITERATION_FINISHED = "ITERATION_FINISHED"

    HUMAN_REQUESTED = "HUMAN_REQUESTED"
    HUMAN_RESPONDED = "HUMAN_RESPONDED"

    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_FINISHED = "ROLLBACK_FINISHED"

    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_ABORTED = "TASK_ABORTED"

    @classmethod
    def from_str(cls, val: str) -> EventType:
        norm = val.strip().upper()
        for member in cls:
            if member.value == norm or member.name == norm:
                return member
        return cls(norm)


@dataclass
class Event:
    """Individual durable event in the event stream."""
    event_id: str
    task_id: str
    timestamp: str
    event_type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    execution_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        return cls(
            event_id=data.get("event_id", f"evt-{uuid.uuid4().hex[:8]}"),
            task_id=data.get("task_id", ""),
            execution_id=data.get("execution_id"),
            timestamp=data.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
            event_type=EventType.from_str(data.get("event_type", "TASK_CREATED")),
            payload=data.get("payload", {}),
        )


class EventStream:
    """Durable JSONL event stream writer and reader."""

    def __init__(self, task_dir: Union[str, Path]):
        self.task_dir = Path(task_dir)
        self.events_file = self.task_dir / "events.jsonl"

    def emit(
        self,
        event_type: Union[EventType, str],
        payload: Optional[Dict[str, Any]] = None,
        task_id: str = "",
        execution_id: Optional[str] = None,
    ) -> Event:
        """Appends an event to events.jsonl atomically."""
        self.task_dir.mkdir(parents=True, exist_ok=True)
        evt_type = EventType.from_str(event_type) if isinstance(event_type, str) else event_type
        evt = Event(
            event_id=f"evt-{uuid.uuid4().hex[:10]}",
            task_id=task_id,
            execution_id=execution_id,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            event_type=evt_type,
            payload=payload or {},
        )

        line = json.dumps(evt.to_dict()) + "\n"
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
        return evt

    def read_events(self) -> List[Event]:
        """Reads all events chronologically from events.jsonl."""
        if not self.events_file.exists():
            return []
        events = []
        with open(self.events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    events.append(Event.from_dict(data))
                except Exception:
                    pass
        return events


class TaskReplayer:
    """Reconstructs what happened in a task execution from the event stream."""

    def __init__(self, root_dir: Union[str, Path] = "."):
        self.root_dir = Path(root_dir).resolve()
        self.tasks_base = self.root_dir / "tasks"

    def find_task_events_file(self, task_id: str, project_name: Optional[str] = None) -> Optional[Path]:
        if project_name:
            p = self.tasks_base / project_name / task_id / "events.jsonl"
            if p.exists():
                return p

        # Search across all project folders
        for match in self.tasks_base.glob(f"*/{task_id}/events.jsonl"):
            return match
        return None

    def replay_task(self, task_id: str, project_name: Optional[str] = None) -> List[str]:
        """Produces chronological human-readable replay log for a task."""
        events_file = self.find_task_events_file(task_id, project_name)
        if not events_file:
            return [f"No event stream found for task '{task_id}'."]

        stream = EventStream(events_file.parent)
        events = stream.read_events()
        if not events:
            return [f"Event stream for task '{task_id}' is empty."]

        lines = [
            f"=== Polyphony Replay: Task {task_id} ===",
            f"Found {len(events)} events recorded in {events_file}",
            "-" * 60,
        ]

        for idx, evt in enumerate(events, 1):
            ts = evt.timestamp[:19].replace("T", " ")
            type_str = evt.event_type.value
            p = evt.payload

            detail = ""
            if evt.event_type == EventType.TASK_CREATED:
                detail = f"Goal: {p.get('goal', '')} [Type: {p.get('task_type', 'FEATURE')}]"
            elif evt.event_type == EventType.ITERATION_STARTED:
                detail = f"Iteration {p.get('iteration')}/{p.get('max_iterations')}"
            elif evt.event_type == EventType.LEAD_DECISION:
                detail = f"Action: {p.get('action')} -> Executor: {p.get('executor', 'none')} | Analysis: {p.get('analysis', '')[:100]}"
            elif evt.event_type == EventType.EXECUTOR_OUTPUT:
                detail = f"Result: {p.get('status')} | Files: {p.get('files_changed', [])}"
            elif evt.event_type == EventType.VERIFICATION_FINISHED:
                detail = f"Passed: {p.get('passed')}"
            elif evt.event_type == EventType.HUMAN_REQUESTED:
                detail = f"Question: {p.get('question')}"
            elif evt.event_type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED, EventType.TASK_ABORTED):
                detail = f"Summary: {p.get('summary', p.get('error', ''))}"
            else:
                detail = str(p) if p else ""

            lines.append(f"[{idx:03d}] {ts} | {type_str:<22} | {detail}")

        lines.append("-" * 60)
        lines.append("=== Replay Complete ===")
        return lines
