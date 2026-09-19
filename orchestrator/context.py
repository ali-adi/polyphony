"""Context builder for lead reasoning agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from orchestrator.state import TaskState, IterationRecord


def load_project_knowledge(project_name: str, root_dir: Path) -> Dict[str, Any]:
    """Load project.yaml, context.md, safety.md, and skills list for a project."""
    proj_dir = root_dir / "projects" / project_name
    knowledge = {
        "name": project_name,
        "config": {},
        "context": "",
        "conventions": "",
        "safety": "",
        "project_skills": [],
        "project_rules": [],
        "project_hooks": [],
        "global_skills": [],
    }

    yaml_file = proj_dir / "project.yaml"
    if yaml_file.exists():
        with open(yaml_file, "r", encoding="utf-8") as f:
            knowledge["config"] = yaml.safe_load(f) or {}

    context_file = proj_dir / "context.md"
    if context_file.exists():
        knowledge["context"] = context_file.read_text(encoding="utf-8")

    conventions_file = proj_dir / "conventions.md"
    if conventions_file.exists():
        knowledge["conventions"] = conventions_file.read_text(encoding="utf-8")

    safety_file = proj_dir / "safety.md"
    if safety_file.exists():
        knowledge["safety"] = safety_file.read_text(encoding="utf-8")

    # List project rules
    rules_dir = proj_dir / "rules"
    if rules_dir.exists():
        for r in sorted(rules_dir.glob("*.md")):
            knowledge["project_rules"].append(r.stem)

    # List project hooks
    hooks_dir = proj_dir / "hooks"
    if hooks_dir.exists():
        for h in sorted(hooks_dir.glob("*.sh")):
            knowledge["project_hooks"].append(h.name)

    # List project skills
    skills_dir = proj_dir / "skills"
    if skills_dir.exists():
        for s in sorted(skills_dir.iterdir()):
            if s.is_dir():
                knowledge["project_skills"].append(s.name)

    # List global skills
    global_skills_dir = root_dir / "skills"
    if global_skills_dir.exists():
        for s in sorted(global_skills_dir.iterdir()):
            if s.is_dir():
                knowledge["global_skills"].append(s.name)

    return knowledge


def build_reasoning_prompt(
    task_state: TaskState,
    knowledge: Dict[str, Any],
    available_executors: List[str],
) -> str:
    """Build complete prompt for lead reasoning agent (Claude / AGY)."""

    # Summarize iteration history
    history_blocks = []
    for rec in task_state.iterations:
        exec_res_summary = ""
        if rec.execution_result:
            out_sample = rec.execution_result.output[:500] if rec.execution_result.output else ""
            err_sample = rec.execution_result.error[:500] if rec.execution_result.error else ""
            exec_res_summary = (
                f"Status: {'Success' if rec.execution_result.success else 'Failed'} (exit code {rec.execution_result.exit_code})\n"
                f"Output: {out_sample}\n"
            )
            if err_sample:
                exec_res_summary += f"Error: {err_sample}\n"

        history_blocks.append(
            f"--- Iteration {rec.iteration_number} ---\n"
            f"Reasoner Action: {rec.lead_decision.get('action')}\n"
            f"Executor Used: {rec.executor_used}\n"
            f"Instruction: {rec.instruction}\n"
            f"{exec_res_summary}"
            f"Tests Passed: {rec.tests_passed}\n"
            f"Files Changed: {rec.files_changed}\n"
        )

    history_text = "\n".join(history_blocks) if history_blocks else "None (starting first iteration)."

    skills_text = (
        f"Project Skills: {', '.join(knowledge.get('project_skills', [])) or 'None'}\n"
        f"Global Skills: {', '.join(knowledge.get('global_skills', [])) or 'None'}\n"
    )

    read_only_note = (
        "\nIMPORTANT: This task is RUNNING IN READ-ONLY MODE. Do NOT propose file edits, writes, or deletions. "
        "Only inspection, analysis, search, or read-only execution is allowed.\n"
        if task_state.read_only
        else ""
    )

    prompt = f"""You are the Lead Reasoning Agent in `ai-orch`, a local-first multi-agent orchestrator.
Your role is to reason, plan, and coordinate task execution. You analyze the project context, evaluate progress, and delegate concrete steps to execution engines or deterministic Python scripts.

# PROJECT INFORMATION
Name: {knowledge.get('name')}
Path: {task_state.project_path}

## Context & Architecture
{knowledge.get('context', 'No context file found.')[:2000]}

## Conventions & Style
{knowledge.get('conventions', 'Follow standard engineering conventions.')[:2000]}

## Safety & Operational Policies
{knowledge.get('safety', 'Follow repository conventions.')[:2000]}

## Active Rules & Hooks
- Rules: {', '.join(knowledge.get('project_rules', [])) or 'None'}
- Safety Hooks: {', '.join(knowledge.get('project_hooks', [])) or 'None'}

## Available Skills
{skills_text}

## Available Executors
{', '.join(available_executors)}

---

# CURRENT TASK
Task ID: {task_state.task_id}
Objective / Goal: {task_state.goal}
Read-Only: {task_state.read_only}
Current Iteration: {task_state.current_iteration + 1} of max {task_state.max_iterations}
{read_only_note}

# EXECUTION HISTORY SO FAR
{history_text}

---

# INSTRUCTIONS
Analyze the current situation against the goal. Determine the best next step.
You MUST respond ONLY with a JSON object matching this exact schema:

```json
{{
  "analysis": "Thorough explanation of findings, current state, and rationale for next step",
  "action": "DELEGATE | VERIFY | COMPLETE | ABORT",
  "executor": "agy | cursor | python | claude",
  "instruction": "Specific, actionable instruction or command for the executor",
  "success_criteria": ["list of concrete criteria"],
  "verification_needed": true | false
}}
```

- If the goal has been fully achieved, set "action": "COMPLETE" with a thorough summary in "analysis".
- If verification is needed, choose action "VERIFY" or "DELEGATE" with executor "python" to run test suites or assertions.
- If delegating implementation or analysis, select the most appropriate executor ("agy", "cursor", "python", or "claude").
- Output ONLY the JSON block. Do not include markdown preamble before or after the JSON.
"""
    return prompt


def parse_reasoner_decision(output_text: str) -> Dict[str, Any]:
    """Parse JSON decision from reasoner output, tolerating markdown wrappers."""
    text = output_text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting markdown ```json ... ```
    if "```" in text:
        blocks = text.split("```")
        for b in blocks:
            b_clean = b.strip()
            if b_clean.startswith("json"):
                b_clean = b_clean[4:].strip()
            try:
                return json.loads(b_clean)
            except json.JSONDecodeError:
                continue

    # Fallback to simple extraction with curly braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # If completely unparseable, return safe fallback decision
    return {
        "analysis": text,
        "action": "ABORT",
        "executor": "python",
        "instruction": "",
        "success_criteria": [],
        "verification_needed": False,
        "raw_text": text,
    }
