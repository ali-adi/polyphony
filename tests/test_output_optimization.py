"""Tests for Output Optimization (Section 23: Output Optimization)."""

import yaml
import pytest
from executors.base import ExecutorResult, ExecutorStatus


def test_concise_executor_contract():
    """Verify Section 23 requirement:
    Agents should report:
    - status
    - summary
    - files changed
    - tests
    - errors
    - warnings
    - artifacts
    - remaining risks
    - next action
    """
    res = ExecutorResult(
        executor_name="cursor",
        status=ExecutorStatus.SUCCESS,
        summary="Fixed ICD-10 cache normalization bug.",
        files_changed=["coder/cache.py", "tests/test_cache.py"],
        tests={"passed": 19, "failed": 0},
        errors=[],
        warnings=["Deprecation warning in pytest"],
        artifacts=["diff.patch"],
        remaining_risks=["No performance benchmark performed"],
        next_action="VERIFY",
    )

    contract = res.to_concise_contract()

    assert contract["status"] == "SUCCESS"
    assert contract["summary"] == "Fixed ICD-10 cache normalization bug."
    assert contract["files_changed"] == ["coder/cache.py", "tests/test_cache.py"]
    assert contract["tests"] == {"passed": 19, "failed": 0}
    assert contract["errors"] == []
    assert contract["warnings"] == ["Deprecation warning in pytest"]
    assert contract["artifacts"] == ["diff.patch"]
    assert contract["remaining_risks"] == ["No performance benchmark performed"]
    assert contract["next_action"] == "VERIFY"

    yaml_str = res.format_concise_contract()
    parsed = yaml.safe_load(yaml_str)
    assert parsed["status"] == "SUCCESS"
    assert parsed["remaining_risks"] == ["No performance benchmark performed"]
    assert parsed["next_action"] == "VERIFY"
