"""Separation of abstract orchestration roles from concrete agent providers."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union


class AgentRole(str, Enum):
    """Core orchestration roles in Polyphony."""
    LEAD_REASONER = "LEAD_REASONER"
    IMPLEMENTER = "IMPLEMENTER"
    RESEARCHER = "RESEARCHER"
    REVIEWER = "REVIEWER"
    VERIFIER = "VERIFIER"
    DETERMINISTIC_EXECUTOR = "DETERMINISTIC_EXECUTOR"

    @classmethod
    def from_str(cls, val: str) -> AgentRole:
        """Parse string into AgentRole, case-insensitively."""
        normalized = val.strip().upper().replace("-", "_").replace(" ", "_")
        for role in cls:
            if role.value == normalized or role.name == normalized:
                return role
        # Common aliases
        aliases = {
            "LEAD": cls.LEAD_REASONER,
            "REASONER": cls.LEAD_REASONER,
            "PLANNER": cls.LEAD_REASONER,
            "CODER": cls.IMPLEMENTER,
            "EXECUTOR": cls.IMPLEMENTER,
            "RESEARCH": cls.RESEARCHER,
            "REVIEW": cls.REVIEWER,
            "VERIFY": cls.VERIFIER,
            "TESTER": cls.VERIFIER,
            "DETERMINISTIC": cls.DETERMINISTIC_EXECUTOR,
            "PYTHON": cls.DETERMINISTIC_EXECUTOR,
            "SHELL": cls.DETERMINISTIC_EXECUTOR,
        }
        if normalized in aliases:
            return aliases[normalized]
        raise ValueError(f"Unknown agent role: '{val}'")


DEFAULT_ROLE_PROVIDERS: Dict[AgentRole, List[str]] = {
    AgentRole.LEAD_REASONER: ["claude", "agy"],
    AgentRole.IMPLEMENTER: ["cursor", "agy", "claude"],
    AgentRole.RESEARCHER: ["agy", "claude"],
    AgentRole.REVIEWER: ["claude", "agy"],
    AgentRole.VERIFIER: ["python", "claude"],
    AgentRole.DETERMINISTIC_EXECUTOR: ["python"],
}


class RoleRegistry:
    """Manages role-to-provider mappings and resolution."""

    def __init__(self, custom_mappings: Optional[Dict[Union[AgentRole, str], Any]] = None):
        self._role_map: Dict[AgentRole, List[str]] = {
            role: list(providers) for role, providers in DEFAULT_ROLE_PROVIDERS.items()
        }
        if custom_mappings:
            for k, v in custom_mappings.items():
                self.bind(k, v)

    def bind(self, role: Union[AgentRole, str], providers: Union[str, List[str]]) -> None:
        """Bind one or more providers to an abstract role."""
        r = AgentRole.from_str(role) if isinstance(role, str) else role
        if isinstance(providers, str):
            providers = [providers]
        self._role_map[r] = [p.lower() for p in providers]

    def get_providers(self, role: Union[AgentRole, str]) -> List[str]:
        """Return provider chain assigned to a role."""
        r = AgentRole.from_str(role) if isinstance(role, str) else role
        return list(self._role_map.get(r, []))

    def get_primary_provider(self, role: Union[AgentRole, str]) -> Optional[str]:
        """Return preferred primary provider for a role."""
        providers = self.get_providers(role)
        return providers[0] if providers else None
