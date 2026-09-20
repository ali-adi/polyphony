"""Tests for Formal Event Model and replay functionality (Section 10)."""

from pathlib import Path
from click.testing import CliRunner
import pytest

from orchestrator.cli import cli
from orchestrator.events import Event, EventStream, EventType, TaskReplayer


def test_event_serialization():
    evt = Event(
        event_id="evt-12345",
        task_id="task-test",
        timestamp="2026-09-20T01:00:00Z",
        event_type=EventType.TASK_STARTED,
        payload={"goal": "Fix bug", "iteration": 1},
    )
    d = evt.to_dict()
    assert d["event_id"] == "evt-12345"
    assert d["event_type"] == "TASK_STARTED"
    assert d["payload"]["goal"] == "Fix bug"

    deserialized = Event.from_dict(d)
    assert deserialized.event_id == evt.event_id
    assert deserialized.event_type == EventType.TASK_STARTED


def test_event_stream_emit_and_read(tmp_path):
    stream = EventStream(tmp_path)
    evt1 = stream.emit(EventType.TASK_CREATED, {"goal": "Implement feature"}, task_id="task-abc")
    evt2 = stream.emit(EventType.LEAD_DECISION, {"action": "DELEGATE", "executor": "cursor"}, task_id="task-abc")
    evt3 = stream.emit(EventType.TASK_COMPLETED, {"summary": "Completed successfully"}, task_id="task-abc")

    events = stream.read_events()
    assert len(events) == 3
    assert events[0].event_type == EventType.TASK_CREATED
    assert events[1].event_type == EventType.LEAD_DECISION
    assert events[2].event_type == EventType.TASK_COMPLETED


def test_task_replayer(tmp_path):
    task_dir = tmp_path / "tasks" / "proj_x" / "task-001"
    task_dir.mkdir(parents=True)
    stream = EventStream(task_dir)

    stream.emit(EventType.TASK_CREATED, {"goal": "Reproduce crash"}, task_id="task-001")
    stream.emit(EventType.ITERATION_STARTED, {"iteration": 1, "max_iterations": 3}, task_id="task-001")
    stream.emit(EventType.TASK_COMPLETED, {"summary": "Done"}, task_id="task-001")

    replayer = TaskReplayer(root_dir=tmp_path)
    lines = replayer.replay_task("task-001")
    assert any("Polyphony Replay: Task task-001" in l for l in lines)
    assert any("TASK_CREATED" in l for l in lines)
    assert any("TASK_COMPLETED" in l for l in lines)


def test_cli_replay_command(tmp_path):
    task_dir = tmp_path / "tasks" / "my_project" / "task-cli-test"
    task_dir.mkdir(parents=True)
    stream = EventStream(task_dir)
    stream.emit(EventType.TASK_CREATED, {"goal": "CLI Replay Test"}, task_id="task-cli-test")

    runner = CliRunner()
    res = runner.invoke(cli, ["replay", "task-cli-test", "--root", str(tmp_path)])
    assert res.exit_code == 0
    assert "Polyphony Replay: Task task-cli-test" in res.output
    assert "TASK_CREATED" in res.output
