"""Classifier for categorizing discovered AI configuration items into orchestrator scopes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

from migrate.scanner import ScannedItem


class ClassificationScope(str, Enum):
    GLOBAL = "global"          # Reusable across any project
    PROJECT = "project"        # Specific to this project's code/domain
    EXECUTOR = "executor"      # Tool/adapter specific config or shim
    SENSITIVE = "sensitive"    # Secrets / keys (.env)
    EPHEMERAL = "ephemeral"    # Caches, IDE temp states


@dataclass
class ClassifiedItem:
    item: ScannedItem
    scope: ClassificationScope
    target_destination: str
    rationale: str
    action: str  # "translate" | "copy_as_is" | "ignore" | "security_block"


GLOBAL_SKILL_NAMES = {
    "catchup",
    "pr",
    "fix-until-green",
    "verify-before-stop",
    "tdd",
    "code-review",
    "diagnosing-bugs",
    "grill-me",
    "grill-with-docs",
    "git-guardrails-claude-code",
    "resolving-merge-conflicts",
    "improve-codebase-architecture",
}

PROJECT_DOMAIN_SKILLS = {
    "am-achi-notes-author",
    "pcs-notes-author",
    "db-reader",
    "pcs-editor",
    "audit-eval-contamination",
    "analyze-runs",
    "icd10am-achi",
    "icd10cm-pcs",
}

SAFETY_HOOKS = {
    "protect-databases.sh": "File protection: prevents modifications to taxonomy database snapshots",
    "block-paid-runs.sh": "Cost protection: blocks costly external API runs without explicit flags",
    "block-ai-attribution.sh": "Git safety: prevents co-authored AI commit metadata",
    "validate-readonly-query.sh": "Database safety: validates SQLite queries are strictly SELECT statements",
    "verify-before-stop.sh": "Quality gate: enforces running test suite before completing tasks",
    "block-bulk-git-add.sh": "Git safety: prevents indiscriminate git add -A or git add .",
    "readonly-sqlite.sh": "Database safety: ensures sqlite connections are opened in readonly mode",
}


def classify_item(item: ScannedItem, project_name: str) -> ClassifiedItem:
    """Classify a single scanned item."""
    p = Path(item.rel_path)
    name = p.name
    parts = p.parts

    # 1. Sensitive items
    if item.category == "secret" or name in (".env", ".env.local"):
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.SENSITIVE,
            target_destination="DO_NOT_MIGRATE",
            rationale="Contains API keys or secrets (e.g. GEMINI_API_KEY). Blocked from copying.",
            action="security_block",
        )

    # 2. Ephemeral items
    if ".gemini/antigravity-ide" in item.rel_path or "scratch" in item.rel_path:
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.EPHEMERAL,
            target_destination="IGNORE",
            rationale="IDE ephemeral state or scratch workspace.",
            action="ignore",
        )

    # 3. Tool adapter shims & executor-level configurations
    if name in ("claude-adapter.sh", "hooks.json", "settings.local.json"):
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.EXECUTOR,
            target_destination=f"migration/{project_name}/original/{item.rel_path}",
            rationale=f"Executor adapter / tool-specific configuration ({item.source_tool}).",
            action="copy_as_is",
        )

    # 4. Executable Safety Hooks
    if item.category == "hook" or name in SAFETY_HOOKS:
        rationale = SAFETY_HOOKS.get(name, f"Safety hook: {name}")
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/hooks/{name}",
            rationale=rationale,
            action="translate",
        )

    # 4. Rules
    if item.category == "rule" or name.endswith(".mdc"):
        rule_name = p.stem
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/rules/{rule_name}.md",
            rationale=f"Project operational rule: {rule_name}",
            action="translate",
        )

    # 5. Project Domain Agents & Skills (am-achi-notes-author, db-reader, pcs-editor, icd10am-achi, etc.)
    # Check if inside a skill/agent folder or matches known project domain skills
    skill_parent = parts[2] if len(parts) > 2 and parts[1] == "skills" else p.stem
    if p.stem in PROJECT_DOMAIN_SKILLS or skill_parent in PROJECT_DOMAIN_SKILLS or item.category == "agent":
        skill_id = skill_parent if skill_parent in PROJECT_DOMAIN_SKILLS else p.stem
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/skills/{skill_id}/",
            rationale=f"Medicoder domain skill/agent: {skill_id}",
            action="translate",
        )

    # 6. Project-specific workflows (e.g. audit-eval-contamination)
    if name == "audit-eval-contamination.js":
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/skills/audit-eval-contamination/SKILL.md",
            rationale="Project audit workflow for eval set contamination",
            action="translate",
        )

    # 7. Global Skills and Workflows
    if p.stem in GLOBAL_SKILL_NAMES or skill_parent in GLOBAL_SKILL_NAMES or name == "fix-until-green.js":
        skill_id = skill_parent if skill_parent in GLOBAL_SKILL_NAMES else p.stem
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.GLOBAL,
            target_destination=f"skills/{skill_id}/",
            rationale=f"Global reusable engineering skill: {skill_id}",
            action="translate",
        )

    # 8. Conventions, Runbooks, Guidelines
    if item.category == "convention" or "runbook" in name.lower() or "convention" in name.lower():
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/conventions.md",
            rationale=f"Project conventions, notes rules, and hard constraints: {name}",
            action="translate",
        )

    # 9. Tool settings & adapters
    if name == "settings.json":
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/project.yaml",
            rationale="Workspace permissions and command allow/deny lists.",
            action="translate",
        )

    # 10. MCP configuration
    if name == ".mcp.json":
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/project.yaml",
            rationale="MCP tools configuration.",
            action="translate",
        )

    # 11. Project documentation
    if name in ("README.md", "CLAUDE.md", "AGENTS.md", "GEMINI.md"):
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/context.md",
            rationale=f"Project architecture and overview: {name}",
            action="translate",
        )

    # Default fallback for other skills in .agents/skills/
    if len(parts) > 1 and parts[1] == "skills":
        s_name = parts[2]
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.GLOBAL,
            target_destination=f"skills/{s_name}/",
            rationale=f"Global skill asset: {s_name}",
            action="translate",
        )

    return ClassifiedItem(
        item=item,
        scope=ClassificationScope.PROJECT,
        target_destination=f"projects/{project_name}/conventions.md",
        rationale=f"Project reference asset: {name}",
        action="copy_as_is",
    )


def classify_items(items: List[ScannedItem], project_name: str) -> List[ClassifiedItem]:
    """Classify all scanned items for a given project."""
    return [classify_item(item, project_name) for item in items]
