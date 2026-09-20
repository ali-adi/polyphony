"""Agent-specific context builders, context hierarchy, and structured output formatting (Sections 15, 16, & 17)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import yaml

from executors.base import ExecutorResult
from orchestrator.state import IterationRecord, TaskState


def format_structured_executor_output(
    result: ExecutorResult,
    remaining_risks: Optional[List[str]] = None,
    recommended_next_action: Optional[str] = None,
) -> str:
    """Formats an executor result into the compact YAML schema specified in Section 17."""
    payload: Dict[str, Any] = {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "summary": result.summary or (result.output[:120].strip() if result.output else "No summary provided"),
        "files_changed": result.files_changed,
        "tests": result.tests if result.tests else {"passed": 0 if not result.success else 1, "failed": 1 if not result.success else 0},
        "verification": [f"pytest {f}" for f in result.files_changed if f.endswith(".py")] or ["pytest"],
        "remaining_risks": remaining_risks or (["Unverified modifications"] if not result.tests else []),
        "recommended_next_action": recommended_next_action or ("VERIFY" if result.success else "INVESTIGATE"),
    }
    return yaml.dump(payload, sort_keys=False, default_flow_style=False)


class ContextHierarchyCompressor:
    """Compresses raw historical execution traces into progressive summaries (Section 15).

    RAW TRANSCRIPT -> STRUCTURED RESULT -> ITERATION SUMMARY -> TASK STATE -> PROJECT MEMORY
    """

    @staticmethod
    def compress_iteration_records(iterations: List[IterationRecord]) -> List[Dict[str, Any]]:
        """Produces compact iteration summaries instead of full conversation transcripts."""
        summaries = []
        for it in iterations:
            lead_dec = it.lead_decision or {}
            exec_res = it.execution_result
            summary_item = {
                "iteration": it.iteration_number,
                "action": lead_dec.get("action", "UNKNOWN"),
                "executor": it.executor_used or lead_dec.get("executor", ""),
                "files_changed": it.files_changed,
                "tests_passed": it.tests_passed,
                "summary": exec_res.summary if (exec_res and exec_res.summary) else lead_dec.get("analysis", "")[:100],
            }
            summaries.append(summary_item)
        return summaries


class AgentContextBuilder:
    """Agent-specific context builders ensuring distinct context tailoring per role (Section 16)."""

    @staticmethod
    def build_lead_context(
        task_state: TaskState,
        relevant_evidence: Optional[List[str]] = None,
        relevant_memory: Optional[List[Dict[str, Any]]] = None,
        failure_history: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
    ) -> str:
        """Context builder for LEAD_REASONER: objective, constraints, architecture, evidence, uncertainty, failure history."""
        parts = [
            "# Lead Reasoner Decision Context",
            "",
            f"## Task Objective:\n{task_state.goal}",
            f"## Current State:\n- Status: {task_state.status.value}\n- Iteration: {task_state.current_iteration}/{task_state.max_iterations}",
        ]

        if constraints:
            parts.append("## Constraints:")
            for c in constraints:
                parts.append(f"- {c}")

        if relevant_memory:
            parts.append("## Relevant Project Memory & Architecture:")
            for m in relevant_memory:
                parts.append(f"- [{m.get('type', 'MEMORY')}] {m.get('content', '')}")

        if relevant_evidence:
            parts.append("## Objective Evidence:")
            for ev in relevant_evidence:
                parts.append(f"- {ev}")

        if failure_history:
            parts.append("## Previous Failure History (Do Not Repeat):")
            for fh in failure_history:
                parts.append(f"- ⚠️ {fh}")

        if task_state.iterations:
            compressed = ContextHierarchyCompressor.compress_iteration_records(task_state.iterations)
            parts.append("## Compact Iteration Summary:")
            for c in compressed:
                status_badge = "✅" if c.get("tests_passed") else "❌"
                parts.append(f"- Step {c['iteration']}: {c['action']} ➔ {c['executor']} {status_badge} | {c['summary']}")

        return "\n\n".join(parts)

    @staticmethod
    def build_implementer_context(
        task_brief: str,
        target_files: List[str],
        acceptance_criteria: List[str],
        conventions: Optional[str] = None,
        relevant_code_snippets: Optional[Dict[str, str]] = None,
        implementation_constraints: Optional[List[str]] = None,
    ) -> str:
        """Context builder for IMPLEMENTER: exact task, acceptance criteria, relevant code, conventions, tests, constraints."""
        parts = [
            "# Implementation Brief",
            "",
            f"## Task Assignment:\n{task_brief}",
            f"## Target Files:\n" + "\n".join(f"- `{f}`" for f in target_files),
            "## Acceptance Criteria:\n" + "\n".join(f"- [ ] {ac}" for ac in acceptance_criteria),
        ]

        if conventions:
            parts.append(f"## Conventions & Style:\n{conventions.strip()}")

        if implementation_constraints:
            parts.append("## Implementation Constraints:\n" + "\n".join(f"- ⛔ {ic}" for ic in implementation_constraints))

        if relevant_code_snippets:
            parts.append("## Relevant Code Context:")
            for file_path, snippet in relevant_code_snippets.items():
                parts.append(f"### `{file_path}`\n```python\n{snippet.strip()}\n```")

        return "\n\n".join(parts)

    @staticmethod
    def build_researcher_context(
        research_question: str,
        known_evidence: List[str],
        source_requirements: List[str],
        desired_format: str,
        unresolved_questions: Optional[List[str]] = None,
    ) -> str:
        """Context builder for RESEARCHER: research question, known evidence, source requirements, output format, unresolved questions."""
        parts = [
            "# Research Specification",
            "",
            f"## Research Question:\n{research_question}",
            "## Known Evidence:\n" + "\n".join(f"- {ke}" for ke in known_evidence),
            "## Source Requirements:\n" + "\n".join(f"- 📖 {sr}" for sr in source_requirements),
            f"## Desired Output Format:\n{desired_format}",
        ]

        if unresolved_questions:
            parts.append("## Unresolved Uncertainties:\n" + "\n".join(f"- ❓ {uq}" for uq in unresolved_questions))

        return "\n\n".join(parts)

    @staticmethod
    def build_verifier_context(
        expected_behavior: str,
        changed_files: List[str],
        acceptance_criteria: List[str],
        test_commands: List[str],
        objective_evidence: Optional[str] = None,
    ) -> str:
        """Context builder for VERIFIER: expected behavior, changed files, acceptance criteria, test commands, objective evidence."""
        parts = [
            "# Verification Plan",
            "",
            f"## Expected Behavior:\n{expected_behavior}",
            "## Changed Files to Verify:\n" + "\n".join(f"- `{f}`" for f in changed_files),
            "## Acceptance Criteria:\n" + "\n".join(f"- [ ] {ac}" for ac in acceptance_criteria),
            "## Deterministic Test Commands:\n" + "\n".join(f"- `{cmd}`" for cmd in test_commands),
        ]

        if objective_evidence:
            parts.append(f"## Objective Evidence Collected:\n{objective_evidence}")

        return "\n\n".join(parts)
