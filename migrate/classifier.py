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


# Known patterns for classification
GLOBAL_SKILL_NAMES = {"catchup", "pr", "fix-until-green", "verify-before-stop"}
GLOBAL_HOOK_NAMES = {"verify-before-stop.sh"}
GLOBAL_WORKFLOW_NAMES = {"fix-until-green.js"}

SAFETY_HOOK_PATTERNS = {
    "protect-databases.sh": "File protection: prevents modifications to taxonomy database snapshots",
    "block-paid-runs.sh": "Cost protection: blocks costly external API runs without explicit flags",
    "block-ai-attribution.sh": "Git safety: prevents co-authored AI commit metadata",
    "validate-readonly-query.sh": "Database safety: validates SQLite queries are strictly SELECT statements",
    "block-bulk-git-add.sh": "Git safety: prevents indiscriminate git add -A or git add .",
    "readonly-sqlite.sh": "Database safety: ensures sqlite connections are opened in readonly mode",
    "am-full-runs.mdc": "Cost safety: prohibits running full evaluation pipeline without approval",
}

PROJECT_AGENT_NAMES = {
    "db-reader": "Read-only database inspector agent for taxonomy tables",
    "pcs-editor": "Precise ICD-10-PCS code editor agent",
    "am-achi-notes-author": "Authoring agent for ICD-10-AM and ACHI notes",
    "pcs-notes-author": "Authoring agent for ICD-10-PCS notes",
}


def classify_item(item: ScannedItem, project_name: str) -> ClassifiedItem:
    """Classify a single scanned item."""
    p = Path(item.rel_path)
    name = p.name

    # 1. Sensitive items
    if item.category == "secret" or name in (".env", ".env.local"):
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.SENSITIVE,
            target_destination="DO_NOT_MIGRATE",
            rationale="Contains API keys or secrets (e.g. GEMINI_API_KEY). Must not be migrated.",
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

    # 3. Global skills and workflows
    skill_or_wf_name = p.stem.lower()
    if p.parent.name in GLOBAL_SKILL_NAMES or skill_or_wf_name in GLOBAL_SKILL_NAMES or name in GLOBAL_HOOK_NAMES:
        skill_id = p.parent.name if p.parent.name in GLOBAL_SKILL_NAMES else skill_or_wf_name
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.GLOBAL,
            target_destination=f"skills/{skill_id}/",
            rationale=f"Generic reusable workflow or skill across engineering repos: {skill_id}",
            action="translate",
        )

    # 4. Safety hooks and rules (Project-level safety)
    if name in SAFETY_HOOK_PATTERNS:
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/safety.md",
            rationale=SAFETY_HOOK_PATTERNS[name],
            action="translate",
        )

    # 5. Project-specific Agents
    agent_stem = p.stem
    if item.category == "agent" or agent_stem in PROJECT_AGENT_NAMES:
        desc = PROJECT_AGENT_NAMES.get(agent_stem, f"Specialized agent for {project_name}")
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/skills/{agent_stem}/SKILL.md",
            rationale=f"Project domain agent: {desc}",
            action="translate",
        )

    # 6. Project-specific workflows
    if item.category == "workflow":
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/skills/{p.stem}/",
            rationale=f"Project-specific automated workflow: {name}",
            action="translate",
        )

    # 7. Tool adapter shims & executor-level configurations
    if name in ("claude-adapter.sh", "hooks.json") or item.category == "setting":
        if name == "settings.json":
            return ClassifiedItem(
                item=item,
                scope=ClassificationScope.PROJECT,
                target_destination=f"projects/{project_name}/project.yaml",
                rationale="Claude Code workspace permissions and command allow/deny lists.",
                action="translate",
            )
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.EXECUTOR,
            target_destination=f"migration/{project_name}/original/{item.rel_path}",
            rationale=f"Executor adapter / tool-specific configuration ({item.source_tool}).",
            action="copy_as_is",
        )

    # 8. MCP server configs
    if item.category == "mcp" or name == ".mcp.json":
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/project.yaml",
            rationale="MCP tools configuration.",
            action="translate",
        )

    # 9. Project documentation & rules
    if item.category in ("doc", "rule") or name in ("README.md", "CLAUDE.md", "AGENTS.md", "GEMINI.md"):
        return ClassifiedItem(
            item=item,
            scope=ClassificationScope.PROJECT,
            target_destination=f"projects/{project_name}/context.md",
            rationale=f"Project context and instructions: {name}",
            action="translate",
        )

    # Default fallback
    return ClassifiedItem(
        item=item,
        scope=ClassificationScope.PROJECT,
        target_destination=f"projects/{project_name}/misc/{name}",
        rationale=f"Unclassified AI asset from {item.source_tool}",
        action="copy_as_is",
    )


def classify_items(items: List[ScannedItem], project_name: str) -> List[ClassifiedItem]:
    """Classify all scanned items for a given project."""
    return [classify_item(item, project_name) for item in items]
