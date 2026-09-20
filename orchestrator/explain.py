"""Task Explainability engine answering the 9 core diagnostic questions for any task (Section 12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from orchestrator.events import EventStream, EventType
from orchestrator.state import StateManager, TaskState, TaskStatus


@dataclass
class TaskExplanation:
    """Structured explanation answering the 9 core autonomous questions."""
    task_id: str
    goal: str
    status: str
    executor_selection_reasons: List[str]
    lead_action_reasons: List[str]
    iteration_reasons: List[str]
    stopping_rationale: str
    blocked_rationale: Optional[str]
    human_escalation_rationale: Optional[str]
    completion_evidence: Dict[str, Any]
    tokens_and_cost: Dict[str, Any]
    failures_encountered: List[Dict[str, Any]]

    def format_cli(self) -> str:
        lines = [
            f"=== Explanation for Task: {self.task_id} ===",
            f"Goal: {self.goal}",
            f"Status: {self.status.upper()}",
            "-" * 60,
            "\n1. Why was each executor selected?",
        ]
        for r in self.executor_selection_reasons or ["No executor selections recorded."]:
            lines.append(f"   • {r}")

        lines.append("\n2. Why did the lead choose these actions?")
        for r in self.lead_action_reasons or ["No lead actions recorded."]:
            lines.append(f"   • {r}")

        lines.append("\n3. Why were subsequent iterations performed?")
        for r in self.iteration_reasons or ["Single iteration completed."]:
            lines.append(f"   • {r}")

        lines.append(f"\n4. Why did Polyphony stop?\n   • {self.stopping_rationale}")

        if self.blocked_rationale:
            lines.append(f"\n5. Why was the task blocked?\n   • {self.blocked_rationale}")
        else:
            lines.append("\n5. Why was the task blocked?\n   • Task was not blocked by safety policies.")

        if self.human_escalation_rationale:
            lines.append(f"\n6. Why was human input requested?\n   • {self.human_escalation_rationale}")
        else:
            lines.append("\n6. Why was human input requested?\n   • No human escalation required.")

        lines.append("\n7. What evidence established completion?")
        ev = self.completion_evidence
        lines.append(f"   • Files changed ({len(ev.get('files_changed', []))}): {', '.join(ev.get('files_changed', [])) or 'none'}")
        lines.append(f"   • Tests passed: {ev.get('tests_passed', 'N/A')}")
        lines.append(f"   • Summary: {ev.get('summary', 'N/A')}")

        lines.append("\n8. How many tokens & cost were spent?")
        tc = self.tokens_and_cost
        lines.append(f"   • Total tokens: {tc.get('total_tokens', 0):,}")
        lines.append(f"   • Estimated cost: ${tc.get('total_cost_usd', 0.0):.4f}")
        lines.append(f"   • Iterations: {tc.get('iterations_count', 0)}")

        lines.append("\n9. Where did failures occur?")
        if self.failures_encountered:
            for f in self.failures_encountered:
                lines.append(f"   • Iteration {f.get('iteration')}: [{f.get('type')}] {f.get('error')}")
        else:
            lines.append("   • Zero execution failures recorded.")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


class TaskExplainer:
    """Answers explainability queries by synthesizing state, iterations, and event stream."""

    def __init__(self, root_dir: Union[str, Path] = "."):
        self.root_dir = Path(root_dir).resolve()
        self.state_manager = StateManager(self.root_dir)

    def find_task(self, task_id: str, project_name: Optional[str] = None) -> Optional[TaskState]:
        if project_name:
            return self.state_manager.load_state(project_name, task_id)
        # Search across all project folders in tasks/
        tasks_dir = self.root_dir / "tasks"
        if tasks_dir.exists():
            for proj_dir in tasks_dir.iterdir():
                if proj_dir.is_dir():
                    st = self.state_manager.load_state(proj_dir.name, task_id)
                    if st:
                        return st
        return None

    def explain(self, task_id: str, project_name: Optional[str] = None) -> TaskExplanation:
        state = self.find_task(task_id, project_name)
        if not state:
            raise ValueError(f"Task '{task_id}' not found.")

        # Read event stream if available
        task_dir = self.root_dir / "tasks" / state.project_name / task_id
        events = EventStream(task_dir).read_events()

        executor_reasons = []
        lead_reasons = []
        iteration_reasons = []
        failures = []
        blocked_reason = None
        human_reason = None

        for it in state.iterations:
            lead_dec = it.lead_decision or {}
            act = lead_dec.get("action", "UNKNOWN")
            analysis = lead_dec.get("analysis", "")
            target_ex = it.executor_used or lead_dec.get("executor", "")

            if target_ex:
                executor_reasons.append(
                    f"Iteration {it.iteration_number}: Selected '{target_ex}' based on action {act} to execute: {it.instruction[:80]}"
                )

            lead_reasons.append(
                f"Iteration {it.iteration_number}: Lead chose {act} because: {analysis[:120]}"
            )

            # Failure checks
            if it.execution_result and not it.execution_result.success:
                failures.append({
                    "iteration": it.iteration_number,
                    "type": "EXECUTOR_FAILURE",
                    "error": it.execution_result.error or it.execution_result.output[:100],
                })
            if it.tests_passed is False:
                failures.append({
                    "iteration": it.iteration_number,
                    "type": "TEST_FAILURE",
                    "error": (it.test_output or "")[:100],
                })
            if not it.safety_passed:
                blocked_reason = it.safety_message or "Blocked by safety policy"
                failures.append({
                    "iteration": it.iteration_number,
                    "type": "SAFETY_BLOCKED",
                    "error": blocked_reason,
                })

            if act == "ASK_HUMAN":
                human_reason = lead_dec.get("question", analysis)

        # Iteration continuation reasons
        for i in range(len(state.iterations) - 1):
            curr = state.iterations[i]
            reason = "Previous step required further verification or error resolution."
            if curr.tests_passed is False:
                reason = "Tests failed in previous step, necessitating bug fix."
            elif not curr.files_changed:
                reason = "No files were changed; lead refined delegation instructions."
            iteration_reasons.append(f"Iteration {i + 1} ➔ {i + 2}: {reason}")

        # Stopping rationale
        if state.status == TaskStatus.COMPLETED:
            stopping_rationale = (
                f"Completed: {state.final_summary or 'All acceptance criteria met and verified.'}"
            )
        elif state.status == TaskStatus.ABORTED:
            stopping_rationale = f"Aborted: {state.error or 'Halted by iteration budget limit or user request.'}"
        elif state.status in (TaskStatus.NEEDS_HUMAN, TaskStatus.PAUSED):
            stopping_rationale = f"Paused: Awaiting human decision ({human_reason or 'clarification required'})."
        elif state.status == TaskStatus.FAILED:
            stopping_rationale = f"Failed: {state.error or 'Unrecoverable execution or policy error.'}"
        else:
            stopping_rationale = f"Status is {state.status.value}."

        completion_evidence = {
            "files_changed": state.all_files_changed,
            "tests_passed": state.iterations[-1].tests_passed if state.iterations else None,
            "summary": state.final_summary,
        }

        tokens_and_cost = {
            "total_tokens": state.total_tokens,
            "total_cost_usd": state.total_cost_usd,
            "iterations_count": len(state.iterations),
        }

        return TaskExplanation(
            task_id=state.task_id,
            goal=state.goal,
            status=state.status.value,
            executor_selection_reasons=executor_reasons,
            lead_action_reasons=lead_reasons,
            iteration_reasons=iteration_reasons,
            stopping_rationale=stopping_rationale,
            blocked_rationale=blocked_reason,
            human_escalation_rationale=human_reason,
            completion_evidence=completion_evidence,
            tokens_and_cost=tokens_and_cost,
            failures_encountered=failures,
        )
