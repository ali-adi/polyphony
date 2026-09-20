"""Tests for Observability and Exportable Run Bundles (Sections 42 & 43)."""

import json
import tempfile
from pathlib import Path
import yaml
import pytest

from orchestrator.bundles import RunBundleExporter
from orchestrator.observability import ObservabilityEngine, TaskObservabilitySnapshot
from orchestrator.state import StateManager, TaskState


def test_section_42_observability_snapshot_and_tui_card():
    """Verify Section 42:
    Expose all 9 observability dimensions and render terminal dashboard card.
    """
    snapshot = TaskObservabilitySnapshot(
        task_id="42",
        lead="claude",
        executor="cursor",
        current_iteration=3,
        max_iterations=8,
        tokens_spent=21400,
        token_budget=50000,
        status="VERIFYING",
        last_decision="Fix API response normalization",
        stages=[
            {"symbol": "✓", "name": "Planning"},
            {"symbol": "✓", "name": "Implementation"},
            {"symbol": "✓", "name": "Tests"},
            {"symbol": "✗", "name": "Integration test"},
            {"symbol": "→", "name": "Debugging"},
        ],
        task_timeline=[{"time": "2026-09-20T01:00:00", "event": "Started"}],
        executor_timeline=[{"executor": "cursor", "action": "code"}],
        token_usage={"total": 21400},
        failure_graph=[{"iteration": 2, "error": "AssertionError"}],
        iteration_history=[{"iteration": 1}, {"iteration": 2}, {"iteration": 3}],
        decision_history=[{"iteration": 3, "action": "debug"}],
        context_size=[12000, 16000, 18000],
        cache_behavior={"hit_rate": 0.75},
        latency={"p95_seconds": 4.2},
    )

    tui = snapshot.render_tui_card()
    assert "Task #42" in tui
    assert "Lead        Claude" in tui
    assert "Executor    Cursor" in tui
    assert "Iteration   3/8" in tui
    assert "Tokens      21.4k / 50k" in tui
    assert "Status      VERIFYING" in tui
    assert "✓ Planning" in tui
    assert "✗ Integration test" in tui
    assert "Fix API response normalization" in tui


def test_section_43_exportable_run_bundle():
    """Verify Section 43:
    task-bundle/
    ├── metadata.yaml
    ├── state.json
    ├── events.jsonl
    ├── report.md
    ├── decisions.md
    ├── evidence/
    ├── diffs/
    └── metrics.json
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        mgr = StateManager(root_dir=tmp_path)
        proj_repo = tmp_path / "my_project"
        proj_repo.mkdir()

        # Create task state
        state = mgr.create_task(
            project_name="proj",
            project_path=str(proj_repo),
            goal="Add fast serializer",
        )
        task_dir = tmp_path / "tasks" / "proj" / state.task_id
        (task_dir / "report.md").write_text("# Report\nDone.", encoding="utf-8")
        (task_dir / "events.jsonl").write_text('{"event": "start"}\n', encoding="utf-8")

        output_dir = tmp_path / "exported"
        bundle_path = RunBundleExporter.export(
            task_id=state.task_id,
            project_name="proj",
            output_dir=output_dir,
            orch_root=tmp_path,
        )

        assert bundle_path.exists()
        assert (bundle_path / "metadata.yaml").exists()
        assert (bundle_path / "state.json").exists()
        assert (bundle_path / "events.jsonl").exists()
        assert (bundle_path / "report.md").exists()
        assert (bundle_path / "decisions.md").exists()
        assert (bundle_path / "metrics.json").exists()
        assert (bundle_path / "evidence").is_dir()
        assert (bundle_path / "diffs").is_dir()

        # Check metadata content
        meta = yaml.safe_load((bundle_path / "metadata.yaml").read_text(encoding="utf-8"))
        assert meta["task_id"] == state.task_id
        assert meta["project_name"] == "proj"

        # Check validation
        assert RunBundleExporter.validate_bundle(bundle_path) is True
