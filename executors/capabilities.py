"""Capability-based routing and executor scoring for Polyphony."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set


class Capability(str, Enum):
    """Standardized executor capability definitions."""
    HIGH_REASONING = "high_reasoning"
    FAST_REASONING = "fast_reasoning"
    CODE_EDITING = "code_editing"
    REPOSITORY_NAVIGATION = "repository_navigation"
    WEB_RESEARCH = "web_research"
    BROWSER_INTERACTION = "browser_interaction"
    SHELL_EXECUTION = "shell_execution"
    DETERMINISTIC_COMPUTATION = "deterministic_computation"
    DETERMINISTIC_VERIFICATION = "deterministic_verification"
    TEST_EXECUTION = "test_execution"
    LARGE_CONTEXT = "large_context"
    LONG_RUNNING = "long_running"
    IMAGE_UNDERSTANDING = "image_understanding"
    STRUCTURED_OUTPUT = "structured_output"
    CHEAP_EXECUTION = "cheap_execution"
    OFFLINE_EXECUTION = "offline_execution"

    @classmethod
    def normalize(cls, val: str) -> str:
        s = val.strip().lower().replace("-", "_").replace(" ", "_")
        # Synonyms
        if s in ("deterministic_verification", "test_execution", "deterministic"):
            return cls.DETERMINISTIC_COMPUTATION.value
        return s


# Relative cost ranking: lower score = cheaper / safer / prefer first
EXECUTOR_COST_SCORES: Dict[str, float] = {
    "python": 0.0,
    "cursor": 1.0,
    "agy": 2.0,
    "claude": 3.0,
}


class CapabilityRouter:
    """Selects the cheapest and safest executor capable of satisfying requirement constraints."""

    def __init__(self, executor_capabilities: Optional[Dict[str, List[str]]] = None):
        self.executor_capabilities: Dict[str, Set[str]] = {}
        if executor_capabilities:
            for ex_name, caps in executor_capabilities.items():
                self.executor_capabilities[ex_name] = {Capability.normalize(c) for c in caps}

    def register_executor(self, name: str, capabilities: List[str]) -> None:
        self.executor_capabilities[name] = {Capability.normalize(c) for c in capabilities}

    def match_executors(
        self,
        required: List[str],
        available_executors: Optional[Dict[str, bool]] = None,
    ) -> List[str]:
        """
        Find all executors that satisfy all required capabilities,
        sorted by cost score (cheapest and safest first).
        """
        req_set = {Capability.normalize(c) for c in required}
        matched: List[tuple[str, float]] = []

        for name, caps in self.executor_capabilities.items():
            # Check availability if provided
            if available_executors and not available_executors.get(name, True):
                continue

            # Check if all required capabilities are satisfied
            if req_set.issubset(caps):
                cost = EXECUTOR_COST_SCORES.get(name, 5.0)
                matched.append((name, cost))

        # Sort by cost ascending
        matched.sort(key=lambda x: x[1])
        return [name for name, _ in matched]
