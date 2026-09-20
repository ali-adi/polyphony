"""Golden traces and regression testing engine (Section 44).

Records execution traces across scenarios (simple_bugfix, rollback, timeout, etc.)
and detects regressions in routing, state transitions, safety, token efficiency,
and completion decisions across Polyphony versions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GoldenTraceStep:
    step_index: int
    role: str
    executor: str
    action: str
    state_before: str
    state_after: str
    tokens_used: int = 0
    safety_violations: List[str] = field(default_factory=list)
    success: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldenTrace:
    trace_id: str
    scenario: str
    goal: str
    final_status: str
    total_tokens: int
    iterations: int
    steps: List[GoldenTraceStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GoldenTrace:
        steps_raw = data.get("steps", [])
        steps = [
            GoldenTraceStep(**s) if isinstance(s, dict) else s
            for s in steps_raw
        ]
        return cls(
            trace_id=data["trace_id"],
            scenario=data["scenario"],
            goal=data["goal"],
            final_status=data["final_status"],
            total_tokens=data.get("total_tokens", 0),
            iterations=data.get("iterations", len(steps)),
            steps=steps,
            metadata=data.get("metadata", {}),
        )

    def save(self, file_path: Path | str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, file_path: Path | str) -> GoldenTrace:
        path = Path(file_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


@dataclass
class TraceTolerance:
    max_token_increase_pct: float = 20.0
    allow_fewer_iterations: bool = True
    max_iteration_increase: int = 0
    strict_routing: bool = True
    strict_safety: bool = True


@dataclass
class TraceComparisonResult:
    scenario: str
    has_regression: bool
    regressions: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def compare_traces(
    golden: GoldenTrace,
    current: GoldenTrace,
    tolerance: Optional[TraceTolerance] = None,
) -> TraceComparisonResult:
    """Compares a current execution trace against a golden reference trace to detect regressions."""
    if tolerance is None:
        tolerance = TraceTolerance()

    regressions: List[str] = []
    improvements: List[str] = []

    # 1. Completion Decision Regression
    if golden.final_status == "COMPLETED" and current.final_status != "COMPLETED":
        regressions.append(
            f"Completion regression: Golden completed successfully ('{golden.final_status}'), "
            f"but current trace ended in status '{current.final_status}'"
        )
    elif golden.final_status != "COMPLETED" and current.final_status == "COMPLETED":
        improvements.append(f"Trace completed successfully where golden previously had status '{golden.final_status}'")

    # 2. Token Efficiency Regression
    if golden.total_tokens > 0:
        max_allowed_tokens = golden.total_tokens * (1.0 + (tolerance.max_token_increase_pct / 100.0))
        if current.total_tokens > max_allowed_tokens:
            regressions.append(
                f"Token regression: Spent {current.total_tokens} tokens vs golden {golden.total_tokens} "
                f"(+{((current.total_tokens - golden.total_tokens) / golden.total_tokens) * 100:.1f}%, limit is +{tolerance.max_token_increase_pct}%)"
            )
        elif current.total_tokens < golden.total_tokens:
            savings_pct = ((golden.total_tokens - current.total_tokens) / golden.total_tokens) * 100
            improvements.append(f"Token savings: {current.total_tokens} vs golden {golden.total_tokens} (-{savings_pct:.1f}%)")

    # 3. Iteration Count Regression
    if current.iterations > golden.iterations + tolerance.max_iteration_increase:
        regressions.append(
            f"Iteration regression: Current required {current.iterations} iterations vs golden {golden.iterations}"
        )
    elif current.iterations < golden.iterations and tolerance.allow_fewer_iterations:
        improvements.append(f"Reduced iterations: {current.iterations} vs golden {golden.iterations}")

    # 4. Step-by-Step Routing and Safety Checks
    for idx, g_step in enumerate(golden.steps):
        if idx >= len(current.steps):
            if current.final_status != "COMPLETED":
                regressions.append(f"Trace truncated early at step {idx + 1}")
            break

        c_step = current.steps[idx]

        # Routing check
        if tolerance.strict_routing:
            if g_step.role and c_step.role and g_step.role != c_step.role:
                regressions.append(
                    f"Routing regression at step {idx + 1}: Expected role '{g_step.role}', got '{c_step.role}'"
                )
            if g_step.executor and c_step.executor and g_step.executor != c_step.executor:
                regressions.append(
                    f"Executor regression at step {idx + 1}: Expected executor '{g_step.executor}', got '{c_step.executor}'"
                )

        # Safety check
        if tolerance.strict_safety:
            new_violations = set(c_step.safety_violations) - set(g_step.safety_violations)
            if new_violations:
                regressions.append(
                    f"Safety regression at step {idx + 1}: New violations detected: {list(new_violations)}"
                )

    has_regression = len(regressions) > 0
    return TraceComparisonResult(
        scenario=golden.scenario,
        has_regression=has_regression,
        regressions=regressions,
        improvements=improvements,
        details={
            "golden_tokens": golden.total_tokens,
            "current_tokens": current.total_tokens,
            "golden_iterations": golden.iterations,
            "current_iterations": current.iterations,
        },
    )


class GoldenTraceSuite:
    """Manages recording, storing, and evaluating a repository of golden traces."""

    def __init__(self, root_dir: Path | str = "golden") -> None:
        self.root_dir = Path(root_dir)

    def record_trace(self, trace: GoldenTrace) -> Path:
        """Stores a golden trace into the suite directory under its scenario name."""
        scenario_dir = self.root_dir / trace.scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)
        file_path = scenario_dir / f"{trace.trace_id}.json"
        trace.save(file_path)
        return file_path

    def load_scenario(self, scenario: str) -> List[GoldenTrace]:
        """Loads all golden traces for a given scenario."""
        scenario_dir = self.root_dir / scenario
        if not scenario_dir.exists():
            return []
        traces = []
        for file in scenario_dir.glob("*.json"):
            traces.append(GoldenTrace.load(file))
        return traces

    @staticmethod
    def create_fixture(scenario: str) -> GoldenTrace:
        """Creates standard reference golden traces for canonical Polyphony scenarios."""
        if scenario == "simple_bugfix":
            return GoldenTrace(
                trace_id="golden_simple_bugfix",
                scenario="simple_bugfix",
                goal="Fix off-by-one error in pagination calculation",
                final_status="COMPLETED",
                total_tokens=3200,
                iterations=1,
                steps=[
                    GoldenTraceStep(
                        step_index=1,
                        role="IMPLEMENTER",
                        executor="cursor",
                        action="EXECUTE_CHANGE",
                        state_before="READY",
                        state_after="VERIFIED",
                        tokens_used=3200,
                        success=True,
                    )
                ],
            )
        elif scenario == "executor_timeout":
            return GoldenTrace(
                trace_id="golden_timeout",
                scenario="executor_timeout",
                goal="Long running task that times out on slow executor and recovers",
                final_status="COMPLETED",
                total_tokens=6500,
                iterations=2,
                steps=[
                    GoldenTraceStep(
                        step_index=1,
                        role="IMPLEMENTER",
                        executor="cursor",
                        action="EXECUTE_CHANGE",
                        state_before="READY",
                        state_after="FAILED",
                        tokens_used=2500,
                        success=False,
                        details={"error": "TIMEOUT"},
                    ),
                    GoldenTraceStep(
                        step_index=2,
                        role="IMPLEMENTER",
                        executor="claude",
                        action="EXECUTE_FALLBACK",
                        state_before="RETRYING",
                        state_after="VERIFIED",
                        tokens_used=4000,
                        success=True,
                    ),
                ],
            )
        elif scenario == "rollback":
            return GoldenTrace(
                trace_id="golden_rollback",
                scenario="rollback",
                goal="Task introducing breaking change correctly rolled back",
                final_status="COMPLETED",
                total_tokens=5000,
                iterations=2,
                steps=[
                    GoldenTraceStep(
                        step_index=1,
                        role="IMPLEMENTER",
                        executor="cursor",
                        action="EXECUTE_CHANGE",
                        state_before="READY",
                        state_after="FAILED",
                        tokens_used=2400,
                        safety_violations=["Critical test failure"],
                        success=False,
                    ),
                    GoldenTraceStep(
                        step_index=2,
                        role="RECOVERY",
                        executor="deterministic",
                        action="ROLLBACK",
                        state_before="FAILED",
                        state_after="COMPLETED",
                        tokens_used=2600,
                        success=True,
                    ),
                ],
            )
        elif scenario == "human_question":
            return GoldenTrace(
                trace_id="golden_human_question",
                scenario="human_question",
                goal="Ambiguous requirements requiring human decision",
                final_status="COMPLETED",
                total_tokens=4200,
                iterations=2,
                steps=[
                    GoldenTraceStep(
                        step_index=1,
                        role="LEAD_REASONER",
                        executor="claude",
                        action="ASK_HUMAN",
                        state_before="PLANNING",
                        state_after="PAUSED",
                        tokens_used=1800,
                        success=True,
                    ),
                    GoldenTraceStep(
                        step_index=2,
                        role="IMPLEMENTER",
                        executor="cursor",
                        action="RESUME_WITH_ANSWER",
                        state_before="RESUMED",
                        state_after="VERIFIED",
                        tokens_used=2400,
                        success=True,
                    ),
                ],
            )
        elif scenario == "multi_iteration":
            return GoldenTrace(
                trace_id="golden_multi_iteration",
                scenario="multi_iteration",
                goal="Complex refactor requiring two iterations to pass tests",
                final_status="COMPLETED",
                total_tokens=8500,
                iterations=2,
                steps=[
                    GoldenTraceStep(
                        step_index=1,
                        role="IMPLEMENTER",
                        executor="cursor",
                        action="ITERATION_1",
                        state_before="READY",
                        state_after="ITERATING",
                        tokens_used=4200,
                        success=False,
                    ),
                    GoldenTraceStep(
                        step_index=2,
                        role="IMPLEMENTER",
                        executor="cursor",
                        action="ITERATION_2",
                        state_before="ITERATING",
                        state_after="VERIFIED",
                        tokens_used=4300,
                        success=True,
                    ),
                ],
            )
        elif scenario == "token_budget":
            return GoldenTrace(
                trace_id="golden_token_budget",
                scenario="token_budget",
                goal="Large context requiring compaction to stay within budget",
                final_status="COMPLETED",
                total_tokens=4500,
                iterations=1,
                steps=[
                    GoldenTraceStep(
                        step_index=1,
                        role="COMPACTOR",
                        executor="deterministic",
                        action="COMPACT_CONTEXT",
                        state_before="OVER_BUDGET",
                        state_after="COMPLIANT",
                        tokens_used=4500,
                        success=True,
                    )
                ],
            )
        else:
            raise ValueError(f"Unknown scenario: {scenario}")
