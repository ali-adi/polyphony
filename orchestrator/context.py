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
    knowledge["path"] = str(knowledge["config"].get("path", ""))

    context_file = proj_dir / "context.md"
    if context_file.exists():
        raw_ctx = context_file.read_text(encoding="utf-8")
        knowledge["context"] = smart_truncate(raw_ctx, 2500)

    conventions_file = proj_dir / "conventions.md"
    if conventions_file.exists():
        raw_conv = conventions_file.read_text(encoding="utf-8")
        knowledge["conventions"] = smart_truncate(raw_conv, 2000)

    safety_file = proj_dir / "safety.md"
    if safety_file.exists():
        raw_safe = safety_file.read_text(encoding="utf-8")
        knowledge["safety"] = smart_truncate(raw_safe, 2000)

    arch_file = proj_dir / "architecture.md"
    if arch_file.exists():
        raw_arch = arch_file.read_text(encoding="utf-8")
        knowledge["architecture"] = smart_truncate(raw_arch, 2000)

    decisions_file = proj_dir / "decisions.md"
    if decisions_file.exists():
        raw_dec = decisions_file.read_text(encoding="utf-8")
        knowledge["decisions"] = smart_truncate(raw_dec, 2000)

    known_issues_file = proj_dir / "known_issues.md"
    if known_issues_file.exists():
        raw_ki = known_issues_file.read_text(encoding="utf-8")
        knowledge["known_issues"] = smart_truncate(raw_ki, 2000)

    knowledge["skill_descriptions"] = {}

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
                desc = get_skill_description(s / "SKILL.md")
                if desc:
                    knowledge["skill_descriptions"][s.name] = desc

    # List global skills
    global_skills_dir = root_dir / "skills"
    if global_skills_dir.exists():
        for s in sorted(global_skills_dir.iterdir()):
            if s.is_dir():
                knowledge["global_skills"].append(s.name)
                if s.name not in knowledge["skill_descriptions"]:
                    desc = get_skill_description(s / "SKILL.md")
                    if desc:
                        knowledge["skill_descriptions"][s.name] = desc

    return knowledge


def get_skill_description(skill_path: Path) -> Optional[str]:
    """Extract 1-line description from SKILL.md YAML frontmatter."""
    try:
        if not skill_path.exists():
            return None
        with open(skill_path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
            if first == "---":
                lines = []
                for _ in range(25):
                    l = f.readline()
                    if not l or l.strip() == "---":
                        break
                    lines.append(l)
                fm = yaml.safe_load("".join(lines))
                if isinstance(fm, dict) and fm.get("description"):
                    return str(fm["description"]).strip()
    except Exception:
        pass
    return None


def load_skill_content(skill_name: str, root_dir: Path, project_name: Optional[str] = None) -> Optional[str]:
    """Retrieve the SKILL.md documentation for a project or global skill."""
    candidates = []
    if project_name:
        candidates.append(root_dir / "projects" / project_name / "skills" / skill_name / "SKILL.md")
    candidates.append(root_dir / "skills" / skill_name / "SKILL.md")

    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def classify_failure(error_text: str, exit_code: int = 1) -> str:
    """Classify execution failure into an actionable diagnostic category."""
    if not error_text and exit_code == 124:
        return "TIMEOUT"
    text = (error_text or "").lower()
    if "syntaxerror" in text or "indentationerror" in text:
        return "SYNTAX_ERROR"
    if "assertionerror" in text or "assert " in text or "failed" in text:
        return "TEST_BUG"
    if "modulenotfounderror" in text or "importerror" in text or "command not found" in text or "no such file" in text:
        return "ENVIRONMENT"
    if "timed out" in text or "timeoutexpired" in text or exit_code == 124:
        return "TIMEOUT"
    if "permission" in text or "access denied" in text or exit_code == 126:
        return "PERMISSION"
    if "quota" in text or "rate limit" in text or "resource exhausted" in text:
        return "INFRASTRUCTURE"
    return "CODE_BUG"


def compress_execution_output(text: Optional[str], max_lines: int = 15, max_chars: int = 600) -> str:
    """Retain the most informative error/traceback or tail lines of an execution output to minimize token bloat."""
    if not text:
        return ""
    lines = text.strip().splitlines()

    # Prioritize error and traceback sites over trailing test-runner summaries
    error_markers = ("FAILED", "ERROR", "AssertionError", "Traceback (most recent call last):", "SyntaxError", "NameError", "TypeError")
    error_indices = [i for i, line in enumerate(lines) if any(m in line for m in error_markers)]
    if error_indices:
        start_idx = max(0, error_indices[0] - 1)
        selected_lines = lines[start_idx : start_idx + max_lines]
        res = "\n".join(selected_lines)
        return smart_truncate(res, max_chars=max_chars)

    # Normalize clean passing test summaries to save tokens
    import re
    pass_match = re.search(r"(=+\s*\d+\s+passed[^\n=]*=+|Ran \d+ tests? in [^\n]*OK)", text)
    if pass_match:
        return f"[Test Suite Passed: {pass_match.group(0).strip(' =')}]"

    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    res = "\n".join(lines)
    return smart_truncate(res, max_chars=max_chars)



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
    skills_items = []
    descs = knowledge.get("skill_descriptions", {})
    all_skills = sorted(list(set(knowledge.get("project_skills", []) + knowledge.get("global_skills", []))))
    for s in all_skills:
        desc = descs.get(s)
        if desc:
            skills_items.append(f"- `{s}`: {desc}")
        else:
            skills_items.append(f"- `{s}`")
    skills_text = "\n".join(skills_items) + "\n" if skills_items else "None\n"

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
            m_lines.append(f"- Subagent Default: model={sub.default_model or 'default'}, thinking_level={sub.default_thinking_level or 'default'}")
            if sub.roles:
                m_lines.append("  Subagent Roles:")
                for r_name, r_prof in sub.roles.items():
                    desc = f" ({r_prof.description})" if r_prof.description else ""
                    m_lines.append(f"  • {r_name}: model={r_prof.model or 'default'}, thinking={r_prof.thinking_level or 'default'}{desc}")
        models_text = "\n".join(m_lines) + "\n"

    context_str = knowledge.get("context", "No context file found.")
    architecture_str = f"\n\n## Architecture\n{knowledge['architecture']}" if knowledge.get("architecture") else ""
    decisions_str = f"\n\n## Durable Decisions & Institutional Memory\n{knowledge['decisions']}" if knowledge.get("decisions") else ""
    known_issues_str = f"\n\n## Known Issues\n{knowledge['known_issues']}" if knowledge.get("known_issues") else ""

    conventions_str = knowledge.get("conventions", "Follow standard engineering conventions.")
    safety_str = knowledge.get("safety", "Follow repository conventions.")
    path_str = project_path or knowledge.get("path", "")

    rules_hooks = []
    if knowledge.get("project_rules"):
        rules_hooks.append(f"- Rules: {', '.join(knowledge['project_rules'])}")
    if knowledge.get("project_hooks"):
        rules_hooks.append(f"- Safety Hooks: {', '.join(knowledge['project_hooks'])}")
    rules_hooks_text = ("## Active Rules & Hooks\n" + "\n".join(rules_hooks) + "\n\n") if rules_hooks else ""

    return f"""You are the Lead Reasoning Agent in `Polyphony`, a local-first multi-agent orchestrator.
Your role is to reason, plan, and coordinate task execution. You analyze the project context, evaluate progress, and delegate concrete steps to execution engines or deterministic Python scripts.

# PROJECT INFORMATION
Name: {knowledge.get('name')}
Path: {path_str}

## Context & Baseline
{context_str}{architecture_str}{decisions_str}{known_issues_str}

## Conventions & Style
{conventions_str}

## Safety & Operational Policies
{safety_str}

{rules_hooks_text}{models_text}## Available Skills
{skills_text}
## Available Executors
{', '.join(available_executors)}

---

# INSTRUCTIONS & DELEGATION CONTRACT
Analyze the current situation against the goal. Determine the best next step.

## Strict Delegation Contract for Coding Agents (cursor, agy, claude):
When delegating to coding engines (`cursor`, `agy`, `claude`):
1. **Target Files**: You MUST specify `target_files` with concrete file paths. Never issue vague requests like "Refactor the auth layer" or "Fix the tests".
2. **Tightly-Scoped Brief**: Your `instruction` must explicitly define:
   - Specific file paths and line ranges/functions to modify.
   - Negative constraints (e.g. "Do NOT modify middleware.py or database schema").
   - Expected behavior/signature changes.
   - Verification test command (e.g. "Run pytest tests/test_auth.py to verify").
3. Delegations without target files or file references will be rejected by the orchestrator.

You MUST respond ONLY with a JSON object matching this exact schema:

```json
{{
  "analysis": "Thorough explanation of findings, current state, and rationale for next step",
  "action": "DELEGATE | VERIFY | USE_SKILL | ASK_HUMAN | COMPLETE | ABORT",
  "executor": "agy | cursor | python | claude",
  "target_files": ["path/to/target1.py", "path/to/target2.py"],
  "skill": "optional skill name when action is USE_SKILL",
  "question": "question for human operator when action is ASK_HUMAN",
  "instruction": "Tightly-scoped task brief for executor (specific files, negative constraints, and verification command)",
  "learnings": "optional architectural decision or finding to persist to project decisions.md",
  "allow_zero_changes": false,
  "model": "optional model override for executor if needed",
  "thinking_level": "optional thinking effort override (low | medium | high)",
  "success_criteria": ["list of concrete criteria"],
  "verification_needed": true | false
}}
```

- If the goal has been fully achieved, set "action": "COMPLETE" with a thorough summary in "analysis" and optional "learnings". Note: for tasks requesting code modifications, if no files were touched, provide explicit justification in "analysis" and set "allow_zero_changes": true.
- If verification is needed, choose action "VERIFY" or "DELEGATE" with executor "python" to run test suites or assertions.
- If delegating implementation, provide a scoped task brief and set "target_files".
- If human decision, clarification, or credentials are required, set "action": "ASK_HUMAN" with "question".
- If specialized skill instructions are required, set "action": "USE_SKILL" with "skill": "<skill_name>".
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
            files_str = f" ({len(rec.files_changed)} files changed)" if rec.files_changed else ""
            tests_str = f" (tests {'passed' if rec.tests_passed else 'failed'})" if rec.tests_passed is not None else ""
            history_blocks.append(
                f"[Iteration {rec.iteration_number}] Action: {rec.lead_decision.get('action')} | "
                f"Executor: {rec.executor_used} | Status: {exec_status}{files_str}{tests_str} | "
                f"{(rec.instruction or '')[:45]}... | {analysis_preview}..."
            )
        else:
            exec_res_summary = ""
            if rec.execution_result:
                is_skill_record = (rec.lead_decision.get("action") == "USE_SKILL" or rec.executor_used == "orchestrator")
                if is_skill_record and rec.execution_result.output:
                    out_sample = smart_truncate(rec.execution_result.output, max_chars=2500)
                else:
                    out_sample = compress_execution_output(rec.execution_result.output, max_lines=12, max_chars=500) if rec.execution_result.output else ""
                err_sample = compress_execution_output(rec.execution_result.error, max_lines=12, max_chars=500) if rec.execution_result.error else ""
                exec_res_summary = f"Status: {'Success' if rec.execution_result.success else 'Failed'} (exit code {rec.execution_result.exit_code})"
                if out_sample:
                    exec_res_summary += f"\nOutput: {out_sample}"
                if err_sample:
                    exec_res_summary += f"\nError: {err_sample}"

            details = [
                f"--- Iteration {rec.iteration_number} ---",
                f"Reasoner Action: {rec.lead_decision.get('action')}",
                f"Executor Used: {rec.executor_used}",
                f"Instruction: {rec.instruction}",
            ]
            if rec.lead_decision.get("target_files"):
                details.append(f"Target Files: {rec.lead_decision.get('target_files')}")
            if exec_res_summary:
                details.append(exec_res_summary)
            if rec.metrics:
                m_str = ", ".join(f"{k}={v}" for k, v in sorted(rec.metrics.items()))
                details.append(f"Metrics: {m_str}")
            if rec.tests_passed is not None:
                details.append(f"Tests Passed: {rec.tests_passed}")
            if rec.files_changed:
                details.append(f"Files Changed: {rec.files_changed}")

            history_blocks.append("\n".join(details) + "\n")

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
