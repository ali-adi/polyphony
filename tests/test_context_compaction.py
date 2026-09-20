"""Tests for Context Compaction (Section 24: Context Compaction)."""

import tempfile
from pathlib import Path
import yaml
import pytest

from orchestrator.context_compaction import ContextCompactor, CompactedContextSchema


def test_compacted_context_schema_yaml():
    """Verify Section 24 YAML format:
    task_summary:
    current_state:
    successful_changes:
    failed_attempts:
    remaining_problem:
    important_decisions:
    known_risks:
    verification_status:
    """
    compacted = CompactedContextSchema(
        task_id="task-comp-01",
        version=1,
        task_summary="Implement user session cache",
        current_state="Iteration 4 complete, cache module created",
        successful_changes=["Modified/created `auth/cache.py`"],
        failed_attempts=["Iter 2 test failure: KeyError 'user_id'"],
        remaining_problem="Handle missing user_id gracefully",
        important_decisions=["Iter 1: delegate to cursor"],
        known_risks=["Cache evictions not benchmarked under load"],
        verification_status="PASSED (all automated tests passed)",
    )

    yaml_str = compacted.to_compact_yaml()
    data = yaml.safe_load(yaml_str)

    expected_keys = [
        "task_summary",
        "current_state",
        "successful_changes",
        "failed_attempts",
        "remaining_problem",
        "important_decisions",
        "known_risks",
        "verification_status",
    ]
    for key in expected_keys:
        assert key in data, f"Key {key} missing from compacted YAML"


def test_deterministic_compaction_and_recovery():
    """Verify Section 24:
    - deterministic where possible
    - schema-driven
    - versioned
    - recoverable
    - raw history kept locally
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = Path(tmpdir)
        iterations = [
            {
                "iteration_number": 1,
                "lead_decision": {"action": "delegate", "rationale": "Write cache module"},
                "execution_result": {"success": True, "files_changed": ["src/cache.py"], "warnings": ["Cache warning"]},
                "tests_passed": False,
                "test_output": "AssertionError: expected 1 got 0",
            },
            {
                "iteration_number": 2,
                "lead_decision": {"action": "delegate", "rationale": "Fix assertion"},
                "execution_result": {"success": True, "files_changed": ["tests/test_cache.py"], "remaining_risks": ["Risk A"]},
                "tests_passed": True,
                "test_output": "2 passed in 0.05s",
            },
        ]

        compacted = ContextCompactor.compact(
            task_id="task-abc",
            goal="Add fast cache",
            iterations=iterations,
            raw_storage_dir=storage_dir,
            version=1,
        )

        assert compacted.version == 1
        assert compacted.compacted_iterations_count == 2
        assert len(compacted.successful_changes) >= 2
        assert any("src/cache.py" in sc for sc in compacted.successful_changes)
        assert len(compacted.failed_attempts) >= 1
        assert "Risk A" in compacted.known_risks
        assert "PASSED" in compacted.verification_status
        assert compacted.raw_history_ref is not None

        # Verify raw history recovery
        recovered = ContextCompactor.recover_raw_history(compacted)
        assert len(recovered) == 2
        assert recovered[0]["iteration_number"] == 1
        assert recovered[1]["iteration_number"] == 2
