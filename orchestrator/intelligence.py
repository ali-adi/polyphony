"""Long-Term Intelligence and Learned Routing (Sections 46 & 47).

Provides:
- Task characteristics extraction
- Complexity estimation (simple / medium / complex)
- Failure prediction before execution
- Adaptive budget allocation
- Workflow selection and scoring
- Historical data store learning from benchmark runs
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ComplexityLevel(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class LearnedWorkflowType(str, Enum):
    DIRECT_EXECUTION = "direct_execution"        # e.g., Cursor -> pytest
    REASON_EXECUTE = "reason_execute"            # e.g., Claude -> Cursor -> pytest
    RESEARCH_EXECUTE = "research_execute"        # e.g., Research -> Claude -> Cursor
    MULTI_AGENT = "multi_agent"                  # e.g., Multi-agent review & consensus
    DAG = "dag"                                  # e.g., Decomposed parallel DAG stages
    HUMAN_APPROVAL = "human_approval"            # e.g., Gated on human confirmation


@dataclass
class TaskCharacteristics:
    goal: str
    task_type: str = "FEATURE"
    file_count: int = 1
    touches_critical_paths: bool = False
    has_clear_criteria: bool = True
    is_ambiguous: bool = False
    is_research_needed: bool = False
    dependency_count: int = 0
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_task(
        cls,
        goal: str,
        target_files: Optional[List[str]] = None,
        task_type: str = "FEATURE",
        is_ambiguous: bool = False,
        touches_critical_paths: bool = False,
    ) -> TaskCharacteristics:
        files = target_files or []
        g_lower = goal.lower()
        research_needed = any(kw in g_lower for kw in ["investigate", "research", "survey", "explore", "compare approaches"])
        ambiguous = is_ambiguous or any(kw in g_lower for kw in ["maybe", "might", "tbd", "unclear", "figure out"])
        critical = touches_critical_paths or any(
            kw in f.lower() for f in files for kw in ["auth", "security", "payment", "billing", "policy", "core/db"]
        )

        return cls(
            goal=goal,
            task_type=task_type,
            file_count=max(len(files), 1),
            touches_critical_paths=critical,
            has_clear_criteria=not ambiguous,
            is_ambiguous=ambiguous,
            is_research_needed=research_needed,
            dependency_count=len(files) - 1 if len(files) > 1 else 0,
        )


@dataclass
class HistoricalRunRecord:
    task_id: str
    workflow: LearnedWorkflowType
    complexity: ComplexityLevel
    success: bool
    safety_violations: int = 0
    tokens_used: int = 0
    latency_seconds: float = 0.0
    iterations: int = 1


@dataclass
class WorkflowMetrics:
    workflow: LearnedWorkflowType
    sample_count: int
    success_rate: float
    safety_rate: float
    median_tokens: int
    median_latency_seconds: float


class HistoricalExperienceStore:
    """Collects and aggregates benchmark and run execution history to power learned routing."""

    def __init__(self, persistence_path: Optional[Path | str] = None) -> None:
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self._records: List[HistoricalRunRecord] = []
        self._seed_default_priors()

    def _seed_default_priors(self) -> None:
        """Seeds empirical priors from Section 47 benchmark data."""
        # Simple refactors: Cursor -> pytest: 97% success, 9k median tokens
        for i in range(30):
            self._records.append(
                HistoricalRunRecord(
                    task_id=f"prior_simple_{i}",
                    workflow=LearnedWorkflowType.DIRECT_EXECUTION,
                    complexity=ComplexityLevel.SIMPLE,
                    success=(i != 0),  # 29/30 = 96.7%
                    safety_violations=0,
                    tokens_used=9000,
                    latency_seconds=15.0,
                    iterations=1,
                )
            )
        # Ambiguous/Complex architecture: Claude -> Cursor -> Review: 89% success, 42k median tokens
        for i in range(20):
            self._records.append(
                HistoricalRunRecord(
                    task_id=f"prior_complex_{i}",
                    workflow=LearnedWorkflowType.REASON_EXECUTE,
                    complexity=ComplexityLevel.COMPLEX,
                    success=(i >= 2),  # 18/20 = 90%
                    safety_violations=0,
                    tokens_used=42000,
                    latency_seconds=95.0,
                    iterations=2,
                )
            )

    def record_run(self, record: HistoricalRunRecord) -> None:
        self._records.append(record)
        if self.persistence_path:
            self.save()

    def get_metrics(
        self,
        workflow: LearnedWorkflowType,
        complexity: Optional[ComplexityLevel] = None,
    ) -> Optional[WorkflowMetrics]:
        matching = [
            r for r in self._records
            if r.workflow == workflow and (complexity is None or r.complexity == complexity)
        ]
        if not matching:
            return None

        sample_count = len(matching)
        successes = sum(1 for r in matching if r.success)
        safe_runs = sum(1 for r in matching if r.safety_violations == 0)
        tokens = sorted(r.tokens_used for r in matching)
        latencies = sorted(r.latency_seconds for r in matching)

        median_tokens = tokens[len(tokens) // 2]
        median_latency = latencies[len(latencies) // 2]

        return WorkflowMetrics(
            workflow=workflow,
            sample_count=sample_count,
            success_rate=successes / sample_count,
            safety_rate=safe_runs / sample_count,
            median_tokens=median_tokens,
            median_latency_seconds=median_latency,
        )

    def save(self) -> None:
        if not self.persistence_path:
            return
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        raw = [asdict(r) for r in self._records]
        self.persistence_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


class ComplexityEstimator:
    """Predicts task complexity (SIMPLE / MEDIUM / COMPLEX) based on scope, ambiguity, and risks."""

    @staticmethod
    def estimate(characteristics: TaskCharacteristics) -> ComplexityLevel:
        if characteristics.touches_critical_paths or characteristics.is_ambiguous or characteristics.file_count > 4:
            return ComplexityLevel.COMPLEX
        if characteristics.file_count > 1 or characteristics.is_research_needed or characteristics.task_type in ("FEATURE", "REFACTOR"):
            return ComplexityLevel.MEDIUM
        return ComplexityLevel.SIMPLE


class FailurePredictor:
    """Identifies tasks likely to fail before execution begins."""

    @staticmethod
    def predict_risk(characteristics: TaskCharacteristics) -> Tuple[float, List[str]]:
        risk_score = 0.05
        factors: List[str] = []

        if characteristics.is_ambiguous:
            risk_score += 0.35
            factors.append("Ambiguous requirements without precise acceptance criteria")

        if characteristics.touches_critical_paths:
            risk_score += 0.25
            factors.append("Modifies critical security or infrastructure paths")

        if characteristics.file_count > 5:
            risk_score += 0.20
            factors.append(f"Large surface area touching {characteristics.file_count} files")

        if not characteristics.has_clear_criteria:
            risk_score += 0.15
            factors.append("Missing explicit verification criteria")

        return min(risk_score, 0.95), factors


class BudgetAllocator:
    """Predicts how much reasoning and token budget each task requires."""

    BASE_BUDGETS = {
        ComplexityLevel.SIMPLE: 12000,
        ComplexityLevel.MEDIUM: 30000,
        ComplexityLevel.COMPLEX: 65000,
    }

    WORKFLOW_MULTIPLIERS = {
        LearnedWorkflowType.DIRECT_EXECUTION: 0.8,
        LearnedWorkflowType.REASON_EXECUTE: 1.2,
        LearnedWorkflowType.RESEARCH_EXECUTE: 1.4,
        LearnedWorkflowType.MULTI_AGENT: 1.8,
        LearnedWorkflowType.DAG: 2.0,
        LearnedWorkflowType.HUMAN_APPROVAL: 1.0,
    }

    @classmethod
    def predict_budget(cls, complexity: ComplexityLevel, workflow: LearnedWorkflowType) -> int:
        base = cls.BASE_BUDGETS.get(complexity, 25000)
        multiplier = cls.WORKFLOW_MULTIPLIERS.get(workflow, 1.0)
        return int(base * multiplier)


class WorkflowSelector:
    """Selects candidate workflows based on characteristics and policy constraints."""

    @staticmethod
    def select_candidates(characteristics: TaskCharacteristics, complexity: ComplexityLevel) -> List[LearnedWorkflowType]:
        candidates: List[LearnedWorkflowType] = []

        if characteristics.touches_critical_paths:
            candidates.append(LearnedWorkflowType.HUMAN_APPROVAL)

        if characteristics.is_research_needed:
            candidates.append(LearnedWorkflowType.RESEARCH_EXECUTE)

        if complexity == ComplexityLevel.SIMPLE and not characteristics.touches_critical_paths:
            candidates.append(LearnedWorkflowType.DIRECT_EXECUTION)
            candidates.append(LearnedWorkflowType.REASON_EXECUTE)
        elif complexity == ComplexityLevel.MEDIUM:
            candidates.append(LearnedWorkflowType.REASON_EXECUTE)
            if characteristics.file_count > 2:
                candidates.append(LearnedWorkflowType.DAG)
        else:  # COMPLEX
            candidates.append(LearnedWorkflowType.REASON_EXECUTE)
            candidates.append(LearnedWorkflowType.MULTI_AGENT)
            if characteristics.file_count > 3:
                candidates.append(LearnedWorkflowType.DAG)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique or [LearnedWorkflowType.REASON_EXECUTE]


@dataclass
class LearnedRoutingDecision:
    selected_workflow: LearnedWorkflowType
    complexity: ComplexityLevel
    predicted_failure_risk: float
    risk_factors: List[str]
    allocated_token_budget: int
    candidate_scores: Dict[str, float]
    explanation: str


class LearnedRouter:
    """High-level learned router implementing Section 47 pipeline:

    task characteristics
           ↓
    complexity estimate
           ↓
    candidate workflows
           ↓
    expected: success, safety, latency, token usage
           ↓
    select workflow
    """

    def __init__(self, store: Optional[HistoricalExperienceStore] = None) -> None:
        self.store = store or HistoricalExperienceStore()

    def route(self, characteristics: TaskCharacteristics) -> LearnedRoutingDecision:
        # 1. Complexity estimate
        complexity = ComplexityEstimator.estimate(characteristics)

        # 2. Failure prediction
        risk, factors = FailurePredictor.predict_risk(characteristics)

        # 3. Candidate workflows
        candidates = WorkflowSelector.select_candidates(characteristics, complexity)

        # 4. Score candidates based on expected success, safety, and token cost
        candidate_scores: Dict[str, float] = {}
        best_workflow = candidates[0]
        best_score = -9999.0

        for wf in candidates:
            metrics = self.store.get_metrics(wf, complexity)
            if not metrics:
                metrics = self.store.get_metrics(wf)  # Fallback to general workflow metrics

            if metrics:
                expected_success = metrics.success_rate
                safety = metrics.safety_rate
                tokens = metrics.median_tokens
            else:
                # Default heuristics
                expected_success = 0.85
                safety = 0.95
                tokens = BudgetAllocator.predict_budget(complexity, wf)

            # Scoring function: maximize success and safety, penalize token cost (normalized)
            token_penalty = (tokens / 50000.0) * 0.20
            score = (expected_success * 0.55) + (safety * 0.35) - token_penalty
            candidate_scores[wf.value] = round(score, 3)

            if score > best_score:
                best_score = score
                best_workflow = wf

        # 5. Allocate token budget
        budget = BudgetAllocator.predict_budget(complexity, best_workflow)

        # 6. Build explanation
        explanation = (
            f"Selected workflow '{best_workflow.value}' for {complexity.value} task "
            f"(Score: {best_score:.3f}, Predicted failure risk: {risk * 100:.1f}%, Budget: {budget} tokens). "
            f"Evaluated candidates: {list(candidate_scores.keys())}."
        )

        return LearnedRoutingDecision(
            selected_workflow=best_workflow,
            complexity=complexity,
            predicted_failure_risk=risk,
            risk_factors=factors,
            allocated_token_budget=budget,
            candidate_scores=candidate_scores,
            explanation=explanation,
        )
