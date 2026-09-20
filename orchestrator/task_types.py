"""Explicit Task Types and standard workflow stages for Polyphony (Section 9)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Union


class TaskType(str, Enum):
    """Core task types recognized by Polyphony."""
    FEATURE = "FEATURE"
    BUGFIX = "BUGFIX"
    REFACTOR = "REFACTOR"
    RESEARCH = "RESEARCH"
    EXPERIMENT = "EXPERIMENT"
    AUDIT = "AUDIT"
    VERIFICATION = "VERIFICATION"
    MAINTENANCE = "MAINTENANCE"

    @classmethod
    def from_str(cls, val: str) -> TaskType:
        norm = val.strip().upper().replace("-", "_").replace(" ", "_")
        for t in cls:
            if t.value == norm or t.name == norm:
                return t
        raise ValueError(f"Unknown task type: '{val}'")


@dataclass
class WorkflowDefinition:
    """Standard workflow blueprint for a specific task type."""
    task_type: TaskType
    stages: List[str]
    read_only_default: bool
    requires_capabilities: List[str]
    description: str


DEFAULT_WORKFLOWS: Dict[TaskType, WorkflowDefinition] = {
    TaskType.BUGFIX: WorkflowDefinition(
        task_type=TaskType.BUGFIX,
        stages=["reproduce", "implement", "test", "verify"],
        read_only_default=False,
        requires_capabilities=["code_editing", "test_execution"],
        description="Reproduce failure, implement targeted fix, run tests, and verify.",
    ),
    TaskType.FEATURE: WorkflowDefinition(
        task_type=TaskType.FEATURE,
        stages=["plan", "implement", "test", "verify"],
        read_only_default=False,
        requires_capabilities=["code_editing", "high_reasoning"],
        description="Architecture plan, implementation across files, tests, and verification.",
    ),
    TaskType.REFACTOR: WorkflowDefinition(
        task_type=TaskType.REFACTOR,
        stages=["analyze", "refactor", "test", "verify"],
        read_only_default=False,
        requires_capabilities=["code_editing", "diff_analysis"],
        description="Analyze code smell, refactor while preserving behavior, verify tests pass.",
    ),
    TaskType.RESEARCH: WorkflowDefinition(
        task_type=TaskType.RESEARCH,
        stages=["gather_evidence", "synthesize", "identify_uncertainty", "recommendations"],
        read_only_default=True,
        requires_capabilities=["web_research", "high_reasoning"],
        description="Gather evidence, synthesize findings, identify uncertainty, and produce recommendations.",
    ),
    TaskType.EXPERIMENT: WorkflowDefinition(
        task_type=TaskType.EXPERIMENT,
        stages=["formulate_hypothesis", "configure", "run_experiment", "measure_metrics", "report"],
        read_only_default=False,
        requires_capabilities=["high_reasoning", "deterministic_computation"],
        description="Formulate hypothesis, run trials, measure metrics, and report results.",
    ),
    TaskType.AUDIT: WorkflowDefinition(
        task_type=TaskType.AUDIT,
        stages=["inspect", "collect_evidence", "report"],
        read_only_default=True,
        requires_capabilities=["repository_navigation", "structured_output"],
        description="Inspect codebase/infrastructure, collect objective evidence, report without mutation.",
    ),
    TaskType.VERIFICATION: WorkflowDefinition(
        task_type=TaskType.VERIFICATION,
        stages=["inspect_changes", "run_tests", "verify_acceptance"],
        read_only_default=True,
        requires_capabilities=["deterministic_computation", "test_execution"],
        description="Inspect modifications, execute deterministic tests, verify acceptance criteria.",
    ),
    TaskType.MAINTENANCE: WorkflowDefinition(
        task_type=TaskType.MAINTENANCE,
        stages=["inspect_health", "update_dependencies", "test", "report"],
        read_only_default=False,
        requires_capabilities=["shell_execution", "test_execution"],
        description="Inspect health, apply dependency updates or chores, verify and report.",
    ),
}


def classify_task_type(goal: str) -> TaskType:
    """Classifies a goal description into the most appropriate TaskType based on semantic intent."""
    text = goal.lower()

    if re.search(r"\b(fix|bug|issue|crash|error|broken|fail|reproduce|patch)\b", text):
        return TaskType.BUGFIX
    if re.search(r"\b(refactor|clean\s*up|extract|restructure|rename|deduplicate)\b", text):
        return TaskType.REFACTOR
    if re.search(r"\b(research|investigate|explore|survey|literature|compare)\b", text):
        return TaskType.RESEARCH
    if re.search(r"\b(audit|inspect|security\s*check|review\s*only|vulnerability)\b", text):
        return TaskType.AUDIT
    if re.search(r"\b(experiment|benchmark|measure|eval|evaluate|trials)\b", text):
        return TaskType.EXPERIMENT
    if re.search(r"\b(verify|test\s*only|validate|check\s*status|assert)\b", text):
        return TaskType.VERIFICATION
    if re.search(r"\b(maintenance|upgrade|dependency|deps|chore|housekeeping)\b", text):
        return TaskType.MAINTENANCE
    return TaskType.FEATURE


def get_workflow_definition(task_type: Union[TaskType, str]) -> WorkflowDefinition:
    """Returns the standard workflow definition for a given task type."""
    t = TaskType.from_str(task_type) if isinstance(task_type, str) else task_type
    return DEFAULT_WORKFLOWS[t]
