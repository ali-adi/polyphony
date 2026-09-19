"""Translator for converting discovered AI configurations into orchestrator format."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from migrate.classifier import ClassifiedItem, ClassificationScope
from migrate.scanner import ScannedItem


@dataclass
class MigrationReport:
    project_name: str
    project_path: Path
    total_scanned: int
    total_migrated: int
    total_ignored: int
    total_blocked: int
    global_skills_created: List[str] = field(default_factory=list)
    project_skills_created: List[str] = field(default_factory=list)
    inventory_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    project_yaml_path: Optional[Path] = None
    safety_md_path: Optional[Path] = None
    context_md_path: Optional[Path] = None


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_original_snapshot(
    classified_items: List[ClassifiedItem],
    snapshot_dir: Path,
) -> None:
    """Copy original discovered config files into migration/<project>/original/ snapshot."""
    _ensure_dir(snapshot_dir)
    for c in classified_items:
        if c.scope == ClassificationScope.SENSITIVE:
            continue
        src = c.item.abs_path
        if not src.exists() or src.is_dir():
            continue
        dest = snapshot_dir / c.item.rel_path
        _ensure_dir(dest.parent)
        shutil.copy2(src, dest)


def _write_inventory_md(
    classified_items: List[ClassifiedItem],
    project_name: str,
    dest_path: Path,
) -> None:
    """Generate human-readable inventory.md."""
    lines = [
        f"# Migration Inventory: `{project_name}`",
        "",
        f"Generated automatically by `ai-orch migrate`.",
        "",
        "## Summary",
        "",
        f"- **Total Discovered Assets**: {len(classified_items)}",
        f"- **Global Assets**: {sum(1 for c in classified_items if c.scope == ClassificationScope.GLOBAL)}",
        f"- **Project Assets**: {sum(1 for c in classified_items if c.scope == ClassificationScope.PROJECT)}",
        f"- **Executor Configs**: {sum(1 for c in classified_items if c.scope == ClassificationScope.EXECUTOR)}",
        f"- **Sensitive/Blocked Items**: {sum(1 for c in classified_items if c.scope == ClassificationScope.SENSITIVE)}",
        f"- **Ephemeral/Ignored Items**: {sum(1 for c in classified_items if c.scope == ClassificationScope.EPHEMERAL)}",
        "",
        "## Discovered AI Configurations",
        "",
        "| Source Tool | Category | Scope | File Path | Action | Target Destination | Rationale |",
        "|---|---|---|---|---|---|---|",
    ]

    for c in classified_items:
        tool = c.item.source_tool.title()
        cat = c.item.category.title()
        scope = c.scope.value.title()
        path = f"`{c.item.rel_path}`"
        action = c.action
        dest = f"`{c.target_destination}`"
        rationale = c.rationale.replace("|", "/")
        lines.append(f"| {tool} | {cat} | {scope} | {path} | {action} | {dest} | {rationale} |")

    lines.extend([
        "",
        "## Safety Policies Identified",
        "",
        "- **Database Protection**: Denies edits to `database/` snapshots.",
        "- **Cost Controls**: Prohibits full Gemini API pipeline evaluation runs without explicit approval.",
        "- **Git Integrity**: Blocks bulk adds (`git add -A`, `git add .`) and removes AI co-author attribution.",
        "- **Database Integrity**: Validates SQLite queries are read-only (`-readonly`).",
        "- **Stop Verification**: Runs test suite before completing task execution.",
        "",
    ])

    _ensure_dir(dest_path.parent)
    dest_path.write_text("\n".join(lines), encoding="utf-8")


def _write_manifest_yaml(
    classified_items: List[ClassifiedItem],
    project_name: str,
    project_path: Path,
    dest_path: Path,
) -> None:
    """Generate machine-readable manifest.yaml."""
    manifest = {
        "project": {
            "name": project_name,
            "path": str(project_path),
        },
        "stats": {
            "total_items": len(classified_items),
            "global_count": sum(1 for c in classified_items if c.scope == ClassificationScope.GLOBAL),
            "project_count": sum(1 for c in classified_items if c.scope == ClassificationScope.PROJECT),
            "executor_count": sum(1 for c in classified_items if c.scope == ClassificationScope.EXECUTOR),
            "sensitive_count": sum(1 for c in classified_items if c.scope == ClassificationScope.SENSITIVE),
            "ephemeral_count": sum(1 for c in classified_items if c.scope == ClassificationScope.EPHEMERAL),
        },
        "items": [
            {
                "rel_path": c.item.rel_path,
                "source_tool": c.item.source_tool,
                "category": c.item.category,
                "scope": c.scope.value,
                "action": c.action,
                "target_destination": c.target_destination,
                "rationale": c.rationale,
                "size_bytes": c.item.size_bytes,
            }
            for c in classified_items
        ],
    }

    _ensure_dir(dest_path.parent)
    with open(dest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, sort_keys=False)


def _generate_project_yaml(
    project_name: str,
    project_path: Path,
    dest_path: Path,
) -> None:
    """Generate projects/<project>/project.yaml."""
    # Check if project has a virtualenv or test runner
    has_env = (project_path / "env").exists()
    python_bin = "env/bin/python" if has_env else "python3"

    config_data = {
        "name": project_name,
        "path": str(project_path.resolve()),
        "description": "ICD-10 medical coding system using Gemini for taxonomy ranking",
        "executors": {
            "lead": "claude",
            "primary": "agy",
            "secondary": "cursor",
        },
        "safety": {
            "protected_paths": [
                "database/",
                "**/database/**",
                "configs/smoke.yml",
            ],
            "blocked_commands": [
                "git push",
                "git merge",
                "git add -A",
                "git add .",
                "git add --all",
                "git add -u",
                "git commit -a",
                "git commit -am",
            ],
            "require_tests_before_stop": True,
            "require_approval_for": [
                "full pipeline runs (--config configs/full.yml)",
                "tune_level.py --force-full",
                "external paid API calls",
            ],
        },
        "testing": {
            "command": f"{python_bin} -m unittest discover -s tests -t .",
            "interpreter": python_bin,
        },
        "git": {
            "automatic_commit": False,
            "automatic_push": False,
            "block_bulk_add": True,
            "block_ai_attribution": True,
        },
    }

    _ensure_dir(dest_path.parent)
    with open(dest_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, sort_keys=False)


def _generate_context_md(
    project_path: Path,
    project_name: str,
    dest_path: Path,
) -> None:
    """Generate projects/<project>/context.md extracting domain and architectural knowledge."""
    readme_path = project_path / "README.md"
    readme_content = ""
    if readme_path.exists():
        readme_content = readme_path.read_text(encoding="utf-8")

    content = f"""# Project Context: {project_name}

## High-Level Objective

Medicoder is an autonomous ICD-10 medical coding system that maps free-text clinical notes and diagnosis strings to standardized taxonomy codes (ICD-10-AM, ICD-10-PCS, ACHI) using hierarchical ranking and large language models.

## Architectural Components

- **Core Taxonomy Database**: Pre-built, versioned SQLite taxonomy snapshots located in `database/`. These tables are immutable references and must never be edited directly.
- **Pipeline Runner**: `medicoder/main.py` runs batch evaluation against clinical case sets. Configured via YAML in `configs/` (`smoke.yml`, `sample.yml`, `full.yml`).
- **Tuning Harness**: `scripts/tune_level.py` tunes prompt structures and level-by-level decision accuracy with strict run budgets.
- **Test Suite**: Standard unittest suite under `tests/`. Verified using `python -m unittest discover -s tests -t .`.

## Key Technical Conventions

- **Python Runtime**: Python 3.11+ virtualenv located at `env/`.
- **Database Access**: Read-only SQLite queries (`sqlite3 -safe -readonly`).
- **Code Edits**: Minimal, focused surgical changes. Always run tests to verify green status before marking tasks complete.
- **Git Protocol**: Individual explicit file adds only (`git add <file>`). Never run `git add -A` or indiscriminate staging.

---

## Extracted README Reference

{readme_content}
"""

    _ensure_dir(dest_path.parent)
    dest_path.write_text(content, encoding="utf-8")


def _generate_safety_md(
    project_name: str,
    dest_path: Path,
) -> None:
    """Generate projects/<project>/safety.md consolidating all safety rules."""
    content = f"""# Safety & Operational Policies: {project_name}

These policies are strictly enforced across all executor engines (`claude`, `agy`, `cursor`) before, during, and after task execution.

## 1. Protected Database Snapshots
- **Rule**: Never edit, modify, truncate, or overwrite any file under `database/` or `*/database/*`.
- **Rationale**: These are pre-computed taxonomy database snapshots. Corrupting them invalidates ICD-10 codings.
- **Action on Violation**: Immediate execution block and task abort.

## 2. Cost Safety & API Pipeline Throttling
- **Rule**: Autonomous agents may only run pipeline commands targeting `configs/smoke.yml` or `configs/sample.yml` without `--cases`.
- **Blocked Commands**:
  - Direct runs of `--config configs/full.yml`
  - Running `scripts/tune_level.py --force-full`
- **Rationale**: Full pipeline sweeps make dozens of paid external Gemini API calls. Full evaluations must be explicitly initiated by the human operator.

## 3. Git Operations & Repository Integrity
- **Rule**:
  - Bulk staging (`git add -A`, `git add .`, `git add --all`, `git add -u`) is strictly forbidden. Files must be added explicitly by path.
  - Automatic `git push` or `git merge` is disabled.
  - AI attribution signatures (`Co-authored-by: ...`) in git commit messages are blocked.
- **Rationale**: Prevent accidental inclusion of credentials, temporary evaluation artifacts, or unintended commits.

## 4. Database Query Safety
- **Rule**: SQLite database queries must be strictly read-only (`sqlite3 -safe -readonly` or `SELECT` statements only). `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER` are blocked.

## 5. Verification Before Stop (Quality Gate)
- **Rule**: Before any task or iteration is declared successful, the full test suite must pass (`python -m unittest discover -s tests -t .`).
- **Action on Failure**: Agent must inspect failures and fix them or halt with a report.
"""

    _ensure_dir(dest_path.parent)
    dest_path.write_text(content, encoding="utf-8")


def _migrate_project_skills(
    project_path: Path,
    project_name: str,
    target_skills_dir: Path,
) -> List[str]:
    """Migrate project-specific Claude agents into project skills."""
    _ensure_dir(target_skills_dir)
    created: List[str] = []

    claude_agents_dir = project_path / ".claude" / "agents"
    if claude_agents_dir.exists():
        for agent_file in claude_agents_dir.glob("*.md"):
            skill_name = agent_file.stem
            skill_dir = target_skills_dir / skill_name
            _ensure_dir(skill_dir)
            target_skill_file = skill_dir / "SKILL.md"

            raw_content = agent_file.read_text(encoding="utf-8")
            # Format as SKILL.md
            if not raw_content.startswith("---"):
                header = f"""---
name: {skill_name}
description: Migrated domain agent {skill_name} for {project_name}
---

"""
                content = header + raw_content
            else:
                content = raw_content

            target_skill_file.write_text(content, encoding="utf-8")
            created.append(skill_name)

    # Also migrate audit-eval-contamination workflow
    audit_wf = project_path / ".claude" / "workflows" / "audit-eval-contamination.js"
    if audit_wf.exists():
        wf_name = "audit-eval-contamination"
        wf_dir = target_skills_dir / wf_name
        _ensure_dir(wf_dir)
        wf_skill_file = wf_dir / "SKILL.md"
        wf_code = audit_wf.read_text(encoding="utf-8")
        wf_content = f"""---
name: {wf_name}
description: Audit case files for evaluation contamination against ICD-10 taxonomy
---

## Objective
Audit clinical case files and evaluation sets to detect any data leakage or eval contamination.

## Workflow Implementation Reference
```javascript
{wf_code}
```
"""
        wf_skill_file.write_text(wf_content, encoding="utf-8")
        created.append(wf_name)

    return created


def _migrate_global_skills(
    project_path: Path,
    target_global_skills_dir: Path,
) -> List[str]:
    """Migrate reusable global skills and workflows into root skills/."""
    _ensure_dir(target_global_skills_dir)
    created: List[str] = []

    # 1. catchup
    claude_catchup = project_path / ".claude" / "skills" / "catchup" / "SKILL.md"
    catchup_dir = target_global_skills_dir / "catchup"
    _ensure_dir(catchup_dir)
    if claude_catchup.exists():
        shutil.copy2(claude_catchup, catchup_dir / "SKILL.md")
    else:
        (catchup_dir / "SKILL.md").write_text("""---
name: catchup
description: Summarize what changed on this branch and why
---

## Commits on this branch (vs main)
!`git log --oneline main..HEAD`

## Files changed on this branch vs main
!`git diff --stat main...HEAD | tail -25`

## Uncommitted changes
!`git status --short`
!`git diff --stat`

## Instructions
Summarize what changed, why, and anything that looks unfinished.
""", encoding="utf-8")
    created.append("catchup")

    # 2. pr
    claude_pr = project_path / ".claude" / "skills" / "pr" / "SKILL.md"
    pr_dir = target_global_skills_dir / "pr"
    _ensure_dir(pr_dir)
    if claude_pr.exists():
        shutil.copy2(claude_pr, pr_dir / "SKILL.md")
    else:
        (pr_dir / "SKILL.md").write_text("""---
name: pr
description: Verify, stage, commit, and open a PR for the current branch
---

1. Verify git and auth status (`gh auth status`).
2. Run test suite: tests must pass.
3. Stage files explicitly by path. Never use bulk add.
4. Commit with descriptive message.
5. Push and open pull request.
""", encoding="utf-8")
    created.append("pr")

    # 3. fix-until-green
    fix_wf = project_path / ".claude" / "workflows" / "fix-until-green.js"
    fix_dir = target_global_skills_dir / "fix-until-green"
    _ensure_dir(fix_dir)
    fix_skill = fix_dir / "SKILL.md"
    fix_content = """---
name: fix-until-green
description: Iterative test fixing loop until all tests pass or 2 stalled rounds
---

## Procedure
1. Run the test suite: `python -m unittest discover -s tests -t .` or `pytest`.
2. If all tests pass, stop and mark green.
3. If failures occur:
   - Identify the failing test cases.
   - Apply the smallest correct change to fix the code, not the test (unless test is obsolete).
   - Rerun suite.
4. If stalled for 2 consecutive rounds without reducing failures, halt and report.
"""
    fix_skill.write_text(fix_content, encoding="utf-8")
    created.append("fix-until-green")

    # 4. verify-before-stop
    stop_dir = target_global_skills_dir / "verify-before-stop"
    _ensure_dir(stop_dir)
    stop_skill = stop_dir / "SKILL.md"
    stop_content = """---
name: verify-before-stop
description: Enforce full test suite verification before completing task
---

## Quality Gate Procedure
Before declaring any task or iteration DONE:
1. Run repository test suite (`python -m unittest discover -s tests -t .` or `pytest`).
2. Verify git status has no stray or broken edits.
3. If tests fail, report failure and do NOT complete task.
"""
    stop_skill.write_text(stop_content, encoding="utf-8")
    created.append("verify-before-stop")

    return created


def translate_project(
    project_path: str | Path,
    output_root: str | Path,
    classified_items: List[ClassifiedItem],
    project_name: Optional[str] = None,
) -> MigrationReport:
    """Translate classified AI items into orchestrator project knowledge and migration artifacts."""
    src_proj = Path(project_path).resolve()
    out_root = Path(output_root).resolve()
    p_name = project_name or src_proj.name

    # Target directories
    migration_dir = out_root / "migration" / p_name
    snapshot_dir = migration_dir / "original"
    project_dir = out_root / "projects" / p_name
    project_skills_dir = project_dir / "skills"
    global_skills_dir = out_root / "skills"

    # 1. Snapshot original files
    _copy_original_snapshot(classified_items, snapshot_dir)

    # 2. Inventory and Manifest
    inventory_file = migration_dir / "inventory.md"
    _write_inventory_md(classified_items, p_name, inventory_file)

    manifest_file = migration_dir / "manifest.yaml"
    _write_manifest_yaml(classified_items, p_name, src_proj, manifest_file)

    # 3. Project knowledge layer
    project_yaml_file = project_dir / "project.yaml"
    _generate_project_yaml(p_name, src_proj, project_yaml_file)

    context_md_file = project_dir / "context.md"
    _generate_context_md(src_proj, p_name, context_md_file)

    safety_md_file = project_dir / "safety.md"
    _generate_safety_md(p_name, safety_md_file)

    # 4. Project-specific skills (e.g. agents)
    project_skills = _migrate_project_skills(src_proj, p_name, project_skills_dir)

    # 5. Global skills
    global_skills = _migrate_global_skills(src_proj, global_skills_dir)

    return MigrationReport(
        project_name=p_name,
        project_path=src_proj,
        total_scanned=len(classified_items),
        total_migrated=sum(1 for c in classified_items if c.action in ("translate", "copy_as_is")),
        total_ignored=sum(1 for c in classified_items if c.action == "ignore"),
        total_blocked=sum(1 for c in classified_items if c.action == "security_block"),
        global_skills_created=global_skills,
        project_skills_created=project_skills,
        inventory_path=inventory_file,
        manifest_path=manifest_file,
        project_yaml_path=project_yaml_file,
        safety_md_path=safety_md_file,
        context_md_path=context_md_file,
    )
