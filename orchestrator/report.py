"""Generates comprehensive markdown reports for completed tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from orchestrator.state import TaskState


def estimate_iteration_tokens(rec) -> int:
    """Approximate tokens consumed during an iteration (chars // 4)."""
    chars = len(rec.instruction or "") + len(rec.lead_decision.get("analysis", "") or "")
    if rec.execution_result:
        chars += len(rec.execution_result.output or "") + len(rec.execution_result.error or "")
    return max(1, chars // 4)


def generate_task_report(task_state: TaskState, dest_path: Optional[Path] = None) -> str:
    """Produce a structured Markdown report from a TaskState."""

    total_est_tokens = sum(estimate_iteration_tokens(rec) for rec in task_state.iterations)

    lines = [
        f"# Task Report: {task_state.goal}",
        "",
        "## Overview",
        "",
        f"- **Task ID**: `{task_state.task_id}`",
        f"- **Project**: `{task_state.project_name}` ({task_state.project_path})",
        f"- **Status**: `{task_state.status.value.upper()}`",
        f"- **Mode**: {'Read-Only' if task_state.read_only else 'Write / Autonomous'}",
        f"- **Started**: {task_state.start_time}",
        f"- **Completed**: {task_state.end_time or 'In Progress'}",
        f"- **Iterations Completed**: {len(task_state.iterations)} / {task_state.max_iterations}",
        f"- **Estimated Token Usage**: ~{total_est_tokens:,} tokens",
        "",
        "## Summary",
        "",
        task_state.final_summary or (f"Halted with error: {task_state.error}" if task_state.error else "Task ended without summary."),
        "",
        "## Iterations Breakdown",
        "",
    ]

    for rec in task_state.iterations:
        action = rec.lead_decision.get("action", "UNKNOWN")
        analysis = rec.lead_decision.get("analysis", "")
        analysis_preview = analysis[:300] + ("..." if len(analysis) > 300 else "")

        exec_status = "Skipped"
        if rec.execution_result:
            exec_status = "Success" if rec.execution_result.success else "Failed"

        lines.extend([
            f"### Iteration {rec.iteration_number}",
            f"- **Reasoner**: `{rec.reasoner_used}`",
            f"- **Decision / Action**: `{action}` (Executor: `{rec.executor_used or 'none'}`)",
            f"- **Analysis**: {analysis_preview}",
            f"- **Instruction**: `{rec.instruction}`",
            f"- **Execution Result**: `{exec_status}`",
            f"- **Safety Checks**: {'✅ Passed' if rec.safety_passed else f'❌ Blocked ({rec.safety_message})'}",
            f"- **Verification Tests**: {'✅ Passed' if rec.tests_passed is True else ('❌ Failed' if rec.tests_passed is False else 'N/A')}",
            f"- **Files Modified**: {', '.join(f'`{f}`' for f in rec.files_changed) if rec.files_changed else 'None'}",
            "",
        ])

    lines.extend([
        "## Files Changed",
        "",
    ])
    if task_state.all_files_changed:
        for f in task_state.all_files_changed:
            lines.append(f"- `{f}`")
    else:
        lines.append("No files modified during this task execution.")

    # Tally safety checks and tests across iterations
    total_safety_violations = sum(1 for rec in task_state.iterations if not rec.safety_passed)
    tests_run = sum(1 for rec in task_state.iterations if rec.tests_passed is not None)
    tests_passed_count = sum(1 for rec in task_state.iterations if rec.tests_passed is True)
    tests_failed_count = sum(1 for rec in task_state.iterations if rec.tests_passed is False)

    safety_lines = [
        "",
        "## Safety Enforcement",
        "",
    ]
    if total_safety_violations == 0:
        safety_lines.append("- Safety Policies: ✅ All operations complied with safety policies (0 violations).")
    else:
        safety_lines.append(f"- Safety Policies: ⚠️ {total_safety_violations} operation(s) blocked by safety policies.")
        for rec in task_state.iterations:
            if not rec.safety_passed:
                safety_lines.append(f"  • Iteration {rec.iteration_number}: {rec.safety_message or 'Safety violation'}")

    if tests_run > 0:
        if tests_failed_count == 0:
            safety_lines.append(f"- Verification Tests: ✅ Enforced and passed ({tests_passed_count}/{tests_run} test runs).")
        else:
            safety_lines.append(f"- Verification Tests: ⚠️ {tests_failed_count} test failure(s) recorded across {tests_run} run(s).")
    else:
        safety_lines.append("- Verification Tests: ℹ️ No verification test suites executed.")

    if task_state.read_only:
        safety_lines.append("- Mode Enforcement: 🔒 Task executed strictly in read-only mode (no file edits made).")

    lines.extend(safety_lines)
    lines.append("")

    report_text = "\n".join(lines)

    if dest_path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(report_text, encoding="utf-8")

    return report_text
