"""Dynamic Task Decomposition and clean evidence aggregation (Section 36).

Section 36: Dynamic Task Decomposition
The lead produces:
TASK
├── investigate
├── implement
├── test
├── benchmark
└── review

Each child gets:
- objective
- constraints
- inputs
- expected output
- dependency information
- budget
- deadline
- capabilities

The parent aggregates evidence rather than blindly concatenating transcripts.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("polyphony.decomposition")


@dataclass
class ChildTaskSpec:
    """Specification given to each child subtask in the decomposition."""
    id: str
    name: str  # investigate, implement, test, benchmark, review
    objective: str
    constraints: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    dependency_information: List[str] = field(default_factory=list)
    budget: int = 10000
    deadline: float = 300.0
    capabilities: List[str] = field(default_factory=list)
    status: str = "PENDING"
    result_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecompositionPlan:
    task_id: str
    goal: str
    children: List[ChildTaskSpec] = field(default_factory=list)
    aggregated_evidence: Dict[str, Any] = field(default_factory=dict)

    def get_child(self, name_or_id: str) -> Optional[ChildTaskSpec]:
        for c in self.children:
            if c.name == name_or_id or c.id == name_or_id:
                return c
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "children": [c.to_dict() for c in self.children],
            "aggregated_evidence": self.aggregated_evidence,
        }


class TaskDecomposer:
    """Decomposes goals into specialized subtasks with explicit contracts and clean evidence aggregation."""

    @staticmethod
    def decompose(
        task_id: str,
        goal: str,
        total_budget: int = 50000,
        deadline_seconds: float = 300.0,
        constraints: Optional[List[str]] = None,
    ) -> DecompositionPlan:
        """Section 36 decomposition:
        TASK
        ├── investigate
        ├── implement
        ├── test
        ├── benchmark
        └── review
        """
        now = time.time()
        c_list = constraints or ["Follow repository conventions", "Do not modify unrelated files"]

        investigate = ChildTaskSpec(
            id=f"{task_id}-investigate",
            name="investigate",
            objective=f"Analyze codebase and architecture required to: {goal}",
            constraints=c_list + ["Read-only inspection"],
            inputs={"goal": goal},
            expected_output="Architecture findings, target files, and implementation blueprint",
            dependency_information=[],
            budget=int(total_budget * 0.15),
            deadline=now + (deadline_seconds * 0.20),
            capabilities=["repository_navigation", "web_research"],
        )

        implement = ChildTaskSpec(
            id=f"{task_id}-implement",
            name="implement",
            objective=f"Write code and file changes to satisfy: {goal}",
            constraints=c_list + ["Maintain backward compatibility"],
            inputs={"goal": goal, "blueprint": f"Output of {investigate.id}"},
            expected_output="Code diff and list of modified files",
            dependency_information=[investigate.id],
            budget=int(total_budget * 0.45),
            deadline=now + (deadline_seconds * 0.60),
            capabilities=["code_editing", "fast_reasoning"],
        )

        test = ChildTaskSpec(
            id=f"{task_id}-test",
            name="test",
            objective="Execute and write automated tests verifying code changes",
            constraints=c_list + ["All existing and new tests must pass"],
            inputs={"code_changes": f"Output of {implement.id}"},
            expected_output="Test execution report with pass/fail counts",
            dependency_information=[implement.id],
            budget=int(total_budget * 0.15),
            deadline=now + (deadline_seconds * 0.75),
            capabilities=["test_execution", "deterministic_computation"],
        )

        benchmark = ChildTaskSpec(
            id=f"{task_id}-benchmark",
            name="benchmark",
            objective="Measure execution latency, memory footprint, and token efficiency",
            constraints=c_list + ["No performance regressions"],
            inputs={"code_changes": f"Output of {implement.id}"},
            expected_output="Performance and token benchmark metrics",
            dependency_information=[test.id],
            budget=int(total_budget * 0.10),
            deadline=now + (deadline_seconds * 0.85),
            capabilities=["deterministic_computation"],
        )

        review = ChildTaskSpec(
            id=f"{task_id}-review",
            name="review",
            objective="Review diff, security risks, test results, and benchmark evidence",
            constraints=c_list + ["Zero unhandled security risks"],
            inputs={
                "diff": f"Output of {implement.id}",
                "tests": f"Output of {test.id}",
                "benchmarks": f"Output of {benchmark.id}",
            },
            expected_output="Review verdict (approved/rejected) and remaining risks",
            dependency_information=[implement.id, test.id, benchmark.id],
            budget=int(total_budget * 0.15),
            deadline=now + deadline_seconds,
            capabilities=["high_reasoning", "structured_output"],
        )

        return DecompositionPlan(
            task_id=task_id,
            goal=goal,
            children=[investigate, implement, test, benchmark, review],
            aggregated_evidence={},
        )

    @staticmethod
    def aggregate_child_evidence(
        plan: DecompositionPlan,
        child_name: str,
        raw_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Aggregates objective evidence rather than blindly concatenating transcripts (Section 36)."""
        child = plan.get_child(child_name)
        if not child:
            raise KeyError(f"Child task '{child_name}' not found in decomposition plan")

        # Extract only objective evidence
        evidence: Dict[str, Any] = {}
        if child_name == "investigate":
            evidence = {
                "target_files": raw_result.get("target_files", []),
                "summary": raw_result.get("summary", ""),
            }
        elif child_name == "implement":
            evidence = {
                "files_changed": raw_result.get("files_changed", []),
                "summary": raw_result.get("summary", ""),
                "has_diff": bool(raw_result.get("diff")),
            }
        elif child_name == "test":
            evidence = {
                "passed": raw_result.get("passed", 0),
                "failed": raw_result.get("failed", 0),
                "status": "PASS" if raw_result.get("failed", 0) == 0 else "FAIL",
            }
        elif child_name == "benchmark":
            evidence = {
                "latency_ms": raw_result.get("latency_ms", 0.0),
                "tokens_spent": raw_result.get("tokens_spent", 0),
                "pass_rate": raw_result.get("pass_rate", 1.0),
            }
        elif child_name == "review":
            evidence = {
                "approved": raw_result.get("approved", False),
                "score": raw_result.get("score", 1.0),
                "risks": raw_result.get("risks", []),
            }
        else:
            evidence = {"summary": raw_result.get("summary", "")}

        child.status = "COMPLETED"
        child.result_evidence = evidence
        plan.aggregated_evidence[child_name] = evidence
        return plan.aggregated_evidence
