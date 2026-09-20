"""Cost-Aware Routing and 'Don't Call an LLM' routing decisions (Sections 26 & 27).

Section 26: Cost-Aware Routing
Considers:
- capability
- quality
- latency
- token expenditure
- failure rate
- availability
- task complexity

Conceptually:
required capability -> candidate executors -> expected quality/cost/latency -> select strategy.
Do not optimize for cheapness alone: A cheap executor that fails 3 times costs more
than a strong executor succeeding once.

Section 27: 'Don't Call an LLM' as a Routing Decision
Router returns:
DETERMINISTIC (instead of CLAUDE, CURSOR, AGY)
Examples:
- "Are all tests passing?" -> pytest
- "What files changed?" -> git diff
- "How many benchmark cases passed?" -> Python
- "Is this task complete according to a simple rule?" -> policy engine
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from executors.capabilities import Capability

logger = logging.getLogger("polyphony.cost_aware")


class RoutingTarget(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    CLAUDE = "CLAUDE"
    CURSOR = "CURSOR"
    AGY = "AGY"
    PYTHON = "PYTHON"


@dataclass
class ExecutorProfile:
    """Historical and expected metrics for an executor."""
    name: str
    capabilities: Set[str]
    quality_score: float         # 0.0 to 1.0
    latency_seconds: float       # typical response latency
    token_expenditure: int       # expected tokens per call
    failure_rate: float          # 0.0 to 1.0 historical failure probability
    available: bool = True

    def effective_cost(self, task_complexity: str = "medium") -> float:
        """Calculates expected cost factoring in repeat attempts on failure.

        Section 26:
        'A cheap executor that fails three times may cost more than a strong executor succeeding once.'
        Expected total tokens = token_expenditure / (1 - failure_rate).
        If complexity is high, failure penalty is amplified.
        """
        success_prob = max(0.05, 1.0 - self.failure_rate)
        complexity_mult = 2.0 if task_complexity == "high" else (1.0 if task_complexity == "medium" else 0.5)
        # Expected iterations to success = 1 / success_prob
        expected_attempts = 1.0 / success_prob
        return self.token_expenditure * expected_attempts * complexity_mult


DEFAULT_PROFILES: Dict[str, ExecutorProfile] = {
    "deterministic": ExecutorProfile(
        name="deterministic",
        capabilities={
            Capability.DETERMINISTIC_COMPUTATION.value,
            Capability.DETERMINISTIC_VERIFICATION.value,
            Capability.TEST_EXECUTION.value,
            Capability.OFFLINE_EXECUTION.value,
            Capability.CHEAP_EXECUTION.value,
        },
        quality_score=1.0,
        latency_seconds=1.0,
        token_expenditure=0,
        failure_rate=0.01,
        available=True,
    ),
    "cursor": ExecutorProfile(
        name="cursor",
        capabilities={
            Capability.CODE_EDITING.value,
            Capability.FAST_REASONING.value,
            Capability.CHEAP_EXECUTION.value,
            Capability.REPOSITORY_NAVIGATION.value,
        },
        quality_score=0.85,
        latency_seconds=12.0,
        token_expenditure=3000,
        failure_rate=0.15,
        available=True,
    ),
    "agy": ExecutorProfile(
        name="agy",
        capabilities={
            Capability.CODE_EDITING.value,
            Capability.HIGH_REASONING.value,
            Capability.WEB_RESEARCH.value,
            Capability.BROWSER_INTERACTION.value,
            Capability.SHELL_EXECUTION.value,
        },
        quality_score=0.90,
        latency_seconds=15.0,
        token_expenditure=4500,
        failure_rate=0.10,
        available=True,
    ),
    "claude": ExecutorProfile(
        name="claude",
        capabilities={
            Capability.HIGH_REASONING.value,
            Capability.FAST_REASONING.value,
            Capability.CODE_EDITING.value,
            Capability.LARGE_CONTEXT.value,
            Capability.STRUCTURED_OUTPUT.value,
        },
        quality_score=0.98,
        latency_seconds=10.0,
        token_expenditure=8000,
        failure_rate=0.03,
        available=True,
    ),
}


@dataclass
class CostAwareRoutingDecision:
    target: RoutingTarget
    executor_name: str
    is_deterministic: bool
    deterministic_tool: Optional[str] = None
    expected_quality: float = 1.0
    expected_cost: float = 0.0
    expected_latency: float = 0.0
    rationale: str = ""
    candidate_scores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["target"] = self.target.value
        return d


class CostAwareRouter:
    """Intelligent router selecting candidates considering quality, cost, latency, failure rate, and deterministic shortcuts."""

    def __init__(self, profiles: Optional[Dict[str, ExecutorProfile]] = None):
        self.profiles = profiles or DEFAULT_PROFILES.copy()

    def detect_deterministic_shortcut(self, instruction: str) -> Optional[Tuple[str, str]]:
        """Section 27: 'Don't Call an LLM' as a Routing Decision.

        Examples:
        - 'Are all tests passing?' -> pytest
        - 'What files changed?' -> git diff
        - 'How many benchmark cases passed?' -> Python
        - 'Is this task complete according to a simple rule?' -> policy engine
        """
        inst = instruction.strip().lower()

        # 1. Tests passing
        if re.search(r"\b(are all tests passing|run tests|verify tests|pytest)\b", inst):
            return ("pytest", "Deterministic test runner resolves test pass status without LLM.")

        # 2. Files changed
        if re.search(r"\b(what files changed|files changed|git diff|show changes|check diff)\b", inst):
            return ("git_diff", "Deterministic git diff inspects changed files without LLM.")

        # 3. Benchmark cases
        if re.search(r"\b(how many benchmark|benchmark cases passed|aggregate benchmarks)\b", inst):
            return ("python", "Deterministic benchmark calculation aggregates results without LLM.")

        # 4. Simple rule / status check
        if re.search(r"\b(is this task complete|clean tree|git status|lint status)\b", inst):
            return ("policy_engine", "Deterministic rule engine evaluates status without LLM.")

        return None

    def route(
        self,
        instruction: str,
        required_capabilities: Optional[List[str]] = None,
        task_complexity: str = "medium",
        availability: Optional[Dict[str, bool]] = None,
    ) -> CostAwareRoutingDecision:
        """Evaluate instruction and route to DETERMINISTIC or optimal LLM executor."""
        # Step 1: Section 27: Check if deterministic tool can answer directly
        shortcut = self.detect_deterministic_shortcut(instruction)
        if shortcut:
            tool_name, rationale = shortcut
            logger.info(f"Routing to DETERMINISTIC tool '{tool_name}' (LLM call avoided)")
            return CostAwareRoutingDecision(
                target=RoutingTarget.DETERMINISTIC,
                executor_name="python",
                is_deterministic=True,
                deterministic_tool=tool_name,
                expected_quality=1.0,
                expected_cost=0.0,
                expected_latency=1.0,
                rationale=rationale,
            )

        # Step 2: Section 26: Cost-Aware candidate selection
        req_caps = {Capability.normalize(c) for c in (required_capabilities or [Capability.CODE_EDITING.value])}
        scores: Dict[str, float] = {}
        candidates: List[Tuple[str, float, ExecutorProfile]] = []

        avail = availability or {}

        for name, profile in self.profiles.items():
            if name == "deterministic":
                continue
            if not avail.get(name, profile.available):
                continue
            # Capability check
            norm_caps = {Capability.normalize(c) for c in profile.capabilities}
            if not req_caps.issubset(norm_caps):
                continue

            eff_cost = profile.effective_cost(task_complexity)

            # Score: we want high quality, low effective cost, and low latency.
            # composite_cost = effective_cost * (1.0 + (1.0 - profile.quality_score) * 3.0) + (profile.latency_seconds * 50)
            quality_weight = 200000.0 if task_complexity == "high" else (40000.0 if task_complexity == "medium" else 5000.0)
            quality_penalty = (1.0 - profile.quality_score) * quality_weight
            score = eff_cost + quality_penalty + (profile.latency_seconds * 50.0)

            scores[name] = round(score, 2)
            candidates.append((name, score, profile))

        if not candidates:
            # Fallback to claude if registered, or first available
            best_name = "claude" if "claude" in self.profiles else list(self.profiles.keys())[0]
            best_profile = self.profiles[best_name]
        else:
            candidates.sort(key=lambda x: x[1])
            best_name, _, best_profile = candidates[0]

        target_enum = RoutingTarget.CLAUDE
        if best_name == "cursor":
            target_enum = RoutingTarget.CURSOR
        elif best_name == "agy":
            target_enum = RoutingTarget.AGY
        elif best_name == "python":
            target_enum = RoutingTarget.PYTHON

        rationale = (
            f"Selected '{best_name}' (quality={best_profile.quality_score}, "
            f"failure_rate={best_profile.failure_rate}, complexity={task_complexity}) "
            f"minimizing expected cost factoring retry risk."
        )

        return CostAwareRoutingDecision(
            target=target_enum,
            executor_name=best_name,
            is_deterministic=False,
            deterministic_tool=None,
            expected_quality=best_profile.quality_score,
            expected_cost=round(best_profile.effective_cost(task_complexity), 2),
            expected_latency=best_profile.latency_seconds,
            rationale=rationale,
            candidate_scores=scores,
        )
