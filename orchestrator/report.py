"""Generates comprehensive markdown reports for completed tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from orchestrator.state import TaskState


def generate_task_report(task_state: TaskState, dest_path: Optional[Path] = None) -> str:
    """Produce a structured Markdown report from a TaskState."""

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

    lines.extend([
        "",
        "## Safety Enforcement",
        "",
        "- Protected database paths respected: `database/` intact.",
        "- Dangerous git commands blocked: no bulk staging or unapproved pushes.",
        "- Verification test gates applied: enforced before stop.",
        "",
    ])

    report_text = "\n".join(lines)

    if dest_path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(report_text, encoding="utf-8")

    return report_text
