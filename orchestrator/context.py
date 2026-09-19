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

    knowledge["models"] = knowledge["config"].get("models", {})

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


def smart_truncate(text: str, max_chars: int = 2000, boundary: str = "\n\n") -> str:
    """Truncate text at nearest structural boundary (paragraph, section, or line) to avoid corrupted fragments."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Check paragraph boundary
    last_boundary = truncated.rfind(boundary)
    if last_boundary > max_chars * 0.5:
        truncated = truncated[:last_boundary]
    else:
        # Check single newline boundary
        last_line = truncated.rfind("\n")
        if last_line > max_chars * 0.5:
            truncated = truncated[:last_line]
    return truncated.rstrip() + "\n\n[... truncated ...]"


def build_system_prompt(
    knowledge: Dict[str, Any],
    available_executors: List[str],
    models_config: Optional[Any] = None,
    project_path: Optional[str] = None,
) -> str:
    """Build static system prompt containing project context, conventions, safety rules, and schema."""
    skills_text = (
        f"Project Skills: {', '.join(knowledge.get('project_skills', [])) or 'None'}\n"
        f"Global Skills: {', '.join(knowledge.get('global_skills', [])) or 'None'}\n"
    )

    models_text = ""
    if models_config:
        m_lines = ["## Active Model & Thinking Configuration"]
        if hasattr(models_config, "lead") and models_config.lead:
            for k, prof in models_config.lead.items():
                if prof.model:
                    m_lines.append(f"- Lead ({k}): model={prof.model}, thinking_level={prof.thinking_level or 'default'}")
        if hasattr(models_config, "executors") and models_config.executors:
            for k, prof in models_config.executors.items():
                if prof.model:
                    m_lines.append(f"- Executor ({k}): model={prof.model}, thinking_level={prof.thinking_level or 'default'}")
        if hasattr(models_config, "subagents") and models_config.subagents:
            sub = models_config.subagents
            if sub.default_model or sub.default_thinking_level:
                m_lines.append(f"- Subagents Default: model={sub.default_model or 'default'}, thinking_level={sub.default_thinking_level or 'default'}")
            if sub.roles:
                m_lines.append("  Subagent Roles:")
                for r_name, r_prof in sub.roles.items():
                    desc = f" ({r_prof.description})" if r_prof.description else ""
                    m_lines.append(f"  • {r_name}: model={r_prof.model or 'default'}, thinking={r_prof.thinking_level or 'default'}{desc}")
        models_text = "\n".join(m_lines) + "\n"

    context_str = smart_truncate(knowledge.get("context", "No context file found."), 2500)
    conventions_str = smart_truncate(knowledge.get("conventions", "Follow standard engineering conventions."), 2000)
    safety_str = smart_truncate(knowledge.get("safety", "Follow repository conventions."), 2000)
    path_str = project_path or knowledge.get("path", "")

    return f"""You are the Lead Reasoning Agent in `Polyphony`, a local-first multi-agent orchestrator.
Your role is to reason, plan, and coordinate task execution. You analyze the project context, evaluate progress, and delegate concrete steps to execution engines or deterministic Python scripts.

# PROJECT INFORMATION
Name: {knowledge.get('name')}
Path: {path_str}

## Context & Architecture
{context_str}

## Conventions & Style
{conventions_str}

## Safety & Operational Policies
{safety_str}

## Active Rules & Hooks
- Rules: {', '.join(knowledge.get('project_rules', [])) or 'None'}
- Safety Hooks: {', '.join(knowledge.get('project_hooks', [])) or 'None'}

{models_text}
## Available Skills
{skills_text}

## Available Executors
{', '.join(available_executors)}

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
  "model": "optional model override for executor (or subagent) if needed",
  "thinking_level": "optional thinking effort override (low | medium | high)",
  "success_criteria": ["list of concrete criteria"],
  "verification_needed": true | false
}}
```

- If the goal has been fully achieved, set "action": "COMPLETE" with a thorough summary in "analysis".
- If verification is needed, choose action "VERIFY" or "DELEGATE" with executor "python" to run test suites or assertions.
- If delegating implementation or analysis, select the most appropriate executor ("agy", "cursor", "python", or "claude").
- Output ONLY the JSON block. Do not include markdown preamble before or after the JSON."""


def build_user_prompt(
    task_state: TaskState,
    history_window: int = 3,
) -> str:
    """Build dynamic user prompt containing task goal, iteration number, and sliding history."""
    history_blocks = []
    total_iters = len(task_state.iterations)
    for i, rec in enumerate(task_state.iterations):
        if i < total_iters - history_window:
            analysis_preview = (rec.lead_decision.get("analysis") or "").strip().replace("\n", " ")[:80]
            exec_status = "Success" if (rec.execution_result and rec.execution_result.success) else ("Failed" if rec.execution_result else "Skipped")
            history_blocks.append(
                f"[Iteration {rec.iteration_number}] Action: {rec.lead_decision.get('action')} | "
                f"Executor: {rec.executor_used} | Status: {exec_status} | "
                f"Analysis: {analysis_preview}..."
            )
        else:
            exec_res_summary = ""
            if rec.execution_result:
                out_sample = smart_truncate(rec.execution_result.output, 800) if rec.execution_result.output else ""
                err_sample = smart_truncate(rec.execution_result.error, 800) if rec.execution_result.error else ""
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

    read_only_note = (
        "\nIMPORTANT: This task is RUNNING IN READ-ONLY MODE. Do NOT propose file edits, writes, or deletions. "
        "Only inspection, analysis, search, or read-only execution is allowed.\n"
        if task_state.read_only
        else ""
    )

    return f"""# CURRENT TASK
Task ID: {task_state.task_id}
Objective / Goal: {task_state.goal}
Read-Only: {task_state.read_only}
Current Iteration: {task_state.current_iteration + 1} of max {task_state.max_iterations}
{read_only_note}

# EXECUTION HISTORY SO FAR
{history_text}"""


def build_reasoning_prompt(
    task_state: TaskState,
    knowledge: Dict[str, Any],
    available_executors: List[str],
    models_config: Optional[Any] = None,
    history_window: int = 3,
) -> str:
    """Build complete prompt for lead reasoning agent (Claude / AGY) with sliding window history and smart truncation."""
    sys_prompt = build_system_prompt(
        knowledge=knowledge,
        available_executors=available_executors,
        models_config=models_config,
        project_path=str(task_state.project_path),
    )
    user_prompt = build_user_prompt(
        task_state=task_state,
        history_window=history_window,
    )
    return f"{sys_prompt}\n\n---\n\n{user_prompt}"


def build_delegation_context_header(knowledge: Dict[str, Any], max_chars: int = 600) -> str:
    """Build a lightweight context header with project conventions and safety constraints to prepend to delegated instructions."""
    name = knowledge.get("name", "Project")
    conventions = (knowledge.get("conventions") or "").strip()
    safety = (knowledge.get("safety") or "").strip()

    parts = [f"[Project Context: {name}]"]
    if conventions:
        summary_conv = smart_truncate(conventions, max_chars // 2)
        parts.append(f"Conventions:\n{summary_conv}")
    if safety:
        summary_safety = smart_truncate(safety, max_chars // 2)
        parts.append(f"Safety Constraints:\n{summary_safety}")

    return "\n\n".join(parts) + "\n\n---\n\n"


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
