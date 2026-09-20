"""Tests for AgentRole and role-based execution routing (Section 7)."""

from unittest.mock import MagicMock
import pytest

from executors.base import ExecutorResult
from executors.roles import AgentRole, RoleRegistry, DEFAULT_ROLE_PROVIDERS
from executors.router import ExecutorRouter


def test_agent_role_from_str():
    assert AgentRole.from_str("lead_reasoner") == AgentRole.LEAD_REASONER
    assert AgentRole.from_str("implementer") == AgentRole.IMPLEMENTER
    assert AgentRole.from_str("LEAD") == AgentRole.LEAD_REASONER
    assert AgentRole.from_str("researcher") == AgentRole.RESEARCHER
    assert AgentRole.from_str("verifier") == AgentRole.VERIFIER
    assert AgentRole.from_str("deterministic") == AgentRole.DETERMINISTIC_EXECUTOR


def test_role_registry_defaults():
    registry = RoleRegistry()
    assert registry.get_providers(AgentRole.LEAD_REASONER) == ["claude", "agy"]
    assert registry.get_providers(AgentRole.IMPLEMENTER) == ["cursor", "agy", "claude"]
    assert registry.get_providers(AgentRole.VERIFIER) == ["python", "claude"]
    assert registry.get_providers(AgentRole.DETERMINISTIC_EXECUTOR) == ["python"]


def test_role_registry_custom_bindings():
    registry = RoleRegistry()
    # Rebind LEAD_REASONER to AGY first
    registry.bind(AgentRole.LEAD_REASONER, ["agy", "claude"])
    assert registry.get_providers(AgentRole.LEAD_REASONER) == ["agy", "claude"]
    assert registry.get_primary_provider(AgentRole.LEAD_REASONER) == "agy"


def test_router_execute_role(tmp_path):
    router = ExecutorRouter()
    # Mock python executor
    mock_python = MagicMock()
    mock_python.is_available.return_value = True
    mock_python.execute.return_value = ExecutorResult(
        executor_name="python",
        success=True,
        output="test verified",
        error="",
    )
    router.executors["python"] = mock_python

    # Execute VERIFIER role
    res, used = router.execute_role(
        role=AgentRole.VERIFIER,
        instruction="pytest",
        cwd=str(tmp_path),
    )
    assert res.success is True
    assert used == "python"
    assert "test verified" in res.output
