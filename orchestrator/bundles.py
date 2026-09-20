"""Exportable Run Bundles generator and validator (Section 43).

Section 43: Exportable Run Bundles
Supports exporting a task to:
task-bundle/
├── metadata.yaml
├── state.json
├── events.jsonl
├── report.md
├── decisions.md
├── evidence/
├── diffs/
└── metrics.json

Useful for:
- debugging
- benchmarks
- sharing
- regression tests
- reproducibility
- incident analysis
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml

logger = logging.getLogger("polyphony.bundles")


class RunBundleExporter:
    """Packages complete task execution states into portable run bundles."""

    BUNDLE_FILES = [
        "metadata.yaml",
        "state.json",
        "events.jsonl",
        "report.md",
        "decisions.md",
        "metrics.json",
    ]
    BUNDLE_DIRS = ["evidence", "diffs"]

    @classmethod
    def export(
        cls,
        task_id: str,
        project_name: str,
        output_dir: Union[str, Path],
        orch_root: Union[str, Path] = ".",
    ) -> Path:
        """Exports a self-contained task bundle satisfying Section 43."""
        root = Path(orch_root).resolve()
        task_dir = root / "tasks" / project_name / task_id

        dest_dir = Path(output_dir).resolve() / f"{task_id}-bundle"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "evidence").mkdir(exist_ok=True)
        (dest_dir / "diffs").mkdir(exist_ok=True)

        # 1. state.json
        state_file = task_dir / "state.json"
        state_data = {}
        if state_file.exists():
            state_data = json.loads(state_file.read_text(encoding="utf-8"))
            shutil.copy2(state_file, dest_dir / "state.json")
        else:
            (dest_dir / "state.json").write_text(json.dumps({"task_id": task_id, "project": project_name}, indent=2))

        # 2. metadata.yaml
        meta = {
            "bundle_version": "1.0",
            "task_id": task_id,
            "project_name": project_name,
            "goal": state_data.get("goal", ""),
            "status": state_data.get("status", "unknown"),
            "created_at": state_data.get("start_time", ""),
            "iterations_count": len(state_data.get("iterations", [])),
        }
        (dest_dir / "metadata.yaml").write_text(yaml.dump(meta, sort_keys=False), encoding="utf-8")

        # 3. events.jsonl
        events_file = task_dir / "events.jsonl"
        if events_file.exists():
            shutil.copy2(events_file, dest_dir / "events.jsonl")
        else:
            (dest_dir / "events.jsonl").write_text("", encoding="utf-8")

        # 4. report.md
        report_file = task_dir / "report.md"
        if report_file.exists():
            shutil.copy2(report_file, dest_dir / "report.md")
        else:
            (dest_dir / "report.md").write_text(f"# Task Report: {task_id}\n\nStatus: {meta['status']}\n", encoding="utf-8")

        # 5. decisions.md
        decisions_content = [f"# Decisions History: {task_id}", ""]
        for it in state_data.get("iterations", []):
            ld = it.get("lead_decision") or {}
            decisions_content.append(f"- **Iteration {it.get('iteration_number')}**: {ld.get('action')} — {ld.get('rationale')}")
        (dest_dir / "decisions.md").write_text("\n".join(decisions_content), encoding="utf-8")

        # 6. metrics.json
        metrics_data = {
            "total_tokens": state_data.get("total_tokens", 0),
            "total_cost_usd": state_data.get("total_cost_usd", 0.0),
            "iterations": len(state_data.get("iterations", [])),
        }
        (dest_dir / "metrics.json").write_text(json.dumps(metrics_data, indent=2), encoding="utf-8")

        # 7. evidence and diffs
        if (task_dir / "evidence").exists():
            shutil.copytree(task_dir / "evidence", dest_dir / "evidence", dirs_exist_ok=True)
        if (task_dir / "diffs").exists():
            shutil.copytree(task_dir / "diffs", dest_dir / "diffs", dirs_exist_ok=True)

        logger.info(f"Exported complete run bundle to {dest_dir}")
        return dest_dir

    @classmethod
    def validate_bundle(cls, bundle_path: Union[str, Path]) -> bool:
        """Validates that a directory is a compliant Section 43 task-bundle."""
        bp = Path(bundle_path).resolve()
        if not bp.is_dir():
            return False

        for f in cls.BUNDLE_FILES:
            if not (bp / f).is_file():
                logger.warning(f"Run bundle missing file: {f}")
                return False

        for d in cls.BUNDLE_DIRS:
            if not (bp / d).is_dir():
                logger.warning(f"Run bundle missing directory: {d}")
                return False

        return True
