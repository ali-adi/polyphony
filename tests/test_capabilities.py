"""Tests for Capability-Based Routing (Section 8)."""

from unittest.mock import MagicMock
import pytest

from executors.base import ExecutorResult
from executors.capabilities import Capability, CapabilityRouter
from executors.router import ExecutorRouter


def test_capability_router_cheapest_selection():
    cap_router = CapabilityRouter({
        "claude": ["high_reasoning", "code_editing", "large_context"],
        "cursor": ["code_editing", "fast_reasoning"],
        "python": ["deterministic_computation", "test_execution"],
    })

    # When code_editing is needed, cursor is cheaper (1.0) than claude (3.0)
    matched = cap_router.match_executors(["code_editing"])
    assert matched == ["cursor", "claude"]

    # When high_reasoning is needed, only claude matches
    matched_reasoning = cap_router.match_executors(["high_reasoning"])
    assert matched_reasoning == ["claude"]

    # When deterministic_computation is needed, python matches
    matched_det = cap_router.match_executors(["deterministic_computation"])
    assert matched_det == ["python"]


def test_router_execute_with_capabilities(tmp_path):
    router = ExecutorRouter()
    mock_python = MagicMock()
    mock_python.is_available.return_value = True
    mock_python.capabilities.return_value = ["deterministic_computation", "test_execution"]
    mock_python.execute.return_value = ExecutorResult(
        executor_name="python",
        success=True,
        output="Deterministic run done",
        error="",
    )
    router.executors["python"] = mock_python

    # Route by capability
    res, used = router.execute_with_capabilities(
        required_capabilities=["deterministic_computation"],
        instruction="run tests",
        cwd=str(tmp_path),
    )
    assert res.success is True
    assert used == "python"
    assert "Deterministic run done" in res.output


def test_router_capability_unsatisfied():
    router = ExecutorRouter()
    with pytest.raises(ValueError, match="No available executor satisfies"):
        router.execute_with_capabilities(
            required_capabilities=["quantum_computing_capability"],
            instruction="factor primes",
            cwd=".",
        )
