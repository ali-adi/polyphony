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
    hooks_migrated: List[str] = field(default_factory=list)
    rules_migrated: List[str] = field(default_factory=list)
    inventory_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    project_yaml_path: Optional[Path] = None
    safety_md_path: Optional[Path] = None
    context_md_path: Optional[Path] = None
    conventions_md_path: Optional[Path] = None


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_original_snapshot(
    classified_items: List[ClassifiedItem],
    snapshot_dir: Path,
) -> None:
    """Copy original discovered config files into migration/<project>/original/ snapshot, cleaning prior state."""
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
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
        f"Generated automatically by `polyphony migrate`.",
        "",
        "## Summary",
        "",
        f"- **Total Discovered Assets**: {len(classified_items)}",
        f"- **Global Skills & Workflows**: {sum(1 for c in classified_items if c.scope == ClassificationScope.GLOBAL)}",
        f"- **Project Domain Assets**: {sum(1 for c in classified_items if c.scope == ClassificationScope.PROJECT)}",
        f"- **Executor Adapter Configs**: {sum(1 for c in classified_items if c.scope == ClassificationScope.EXECUTOR)}",
        f"- **Sensitive/Blocked Credentials**: {sum(1 for c in classified_items if c.scope == ClassificationScope.SENSITIVE)}",
        f"- **Ephemeral/Ignored State**: {sum(1 for c in classified_items if c.scope == ClassificationScope.EPHEMERAL)}",
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
        "## Consolidated Policies & Artifacts",
        "",
        "- **Hooks**: Executable safety hook scripts preserved in `projects/<project>/hooks/` with executable bits.",
        "- **Rules**: Enforced operational policies saved in `projects/<project>/rules/`.",
        "- **Conventions & Style**: Coding standards, prompt structure, notes authoring syntax in `projects/<project>/conventions.md`.",
        "- **Safety Engine**: Unified safety gates in `projects/<project>/safety.md`.",
        "- **Domain Skills**: Specialized agents and schemas in `projects/<project>/skills/`.",
        "- **Global Skills**: Reusable engineering workflows in `skills/`.",
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
    has_env = (project_path / "env").exists() or (project_path / ".venv").exists()
    python_bin = "env/bin/python" if (project_path / "env").exists() else (".venv/bin/python" if (project_path / ".venv").exists() else "python3")

    readme = project_path / "README.md"
    desc = f"Autonomous orchestrator workspace for {project_name}"
    if readme.exists():
        try:
            for line in readme.read_text(encoding="utf-8").splitlines():
                clean = line.strip().lstrip("#").strip()
                if clean:
                    desc = clean
                    break
        except Exception:
            pass

    test_cmd = f"{python_bin} -m unittest discover -s tests -t ." if (project_path / "tests").exists() else "pytest"

    approvals = ["external paid API calls", "unbudgeted production sweeps"]
    if (project_path / "configs" / "full.yml").exists():
        approvals.append("configs/full.yml")
    if (project_path / "scripts" / "tune_level.py").exists():
        approvals.append("tune_level.py --force-full")

    config_data = {
        "name": project_name,
        "path": str(project_path.resolve()),
        "description": desc,
        "executors": {
            "lead": "claude",
            "primary": "agy",
            "secondary": "cursor",
        },
        "safety": {
            "protected_paths": [
                "database/",
                "**/database/**",
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
            "require_approval_for": approvals,
        },
        "testing": {
            "command": test_cmd,
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
        try:
            readme_content = readme_path.read_text(encoding="utf-8")
        except Exception:
            pass

    components = []
    for item in sorted(project_path.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and item.name not in ("env", "venv", ".venv", "__pycache__", "node_modules"):
            components.append(f"- **`{item.name}/`**: Directory module component")

    comp_str = "\n".join(components) if components else "- Flat workspace or single-module structure."

    content = f"""# Project Context: {project_name}

## High-Level Objective
Autonomous project workspace for `{project_name}` managed by Polyphony.

## Discovered Project Structure
{comp_str}

## Key Technical Conventions
- **Code Edits**: Minimal, focused surgical changes. Always run tests to verify green status before marking tasks complete.
- **Git Protocol**: Individual explicit file adds only (`git add <file>`). Never run `git add -A` or indiscriminate staging.
- **Safety Gate**: Never alter protected databases or configuration assets without operator verification.

---

## Extracted README Reference
{readme_content or "No README.md found in repository root."}
"""
    _ensure_dir(dest_path.parent)
    dest_path.write_text(content, encoding="utf-8")


def _generate_conventions_md(
    project_path: Path,
    project_name: str,
    dest_path: Path,
) -> None:
    """Generate projects/<project>/conventions.md detailing coding standards, style, and rules."""
    has_env = (project_path / "env").exists() or (project_path / ".venv").exists()
    py_runtime = "env/bin/python" if (project_path / "env").exists() else (".venv/bin/python" if (project_path / ".venv").exists() else "python3")

    runbook_path = project_path / "tuning" / "runbook.md"
    runbook_excerpt = ""
    if runbook_path.exists():
        try:
            rb_lines = runbook_path.read_text(encoding="utf-8").splitlines()
            runbook_excerpt = "\n".join(rb_lines[:40])
        except Exception:
            pass

    content = f"""# Engineering & Authoring Conventions: {project_name}

## 1. Code Style & Architecture
- **Language**: Python 3 adhering to standard PEP 8 conventions.
- **Type Annotations**: Mandatory type hints for public signatures and critical data models.
- **Docstrings & Comments**: Preserved at all times. Do not strip or alter unrelated comments during edits.
- **Edits**: Minimal, surgical modifications. Fix the implementation code rather than altering tests, unless the test specification itself is explicitly proven obsolete.

## 2. Testing & Quality Discipline
- **Virtual Environment**: All commands, scripts, and tests must be executed using `{py_runtime}`.
- **Green Suite Guarantee**: Keep the unit tests passing at all times. Verify tests pass after any modification.
- **Zero Broken Changes**: Never declare a task or PR complete if tests are failing.

## 3. Database Interaction Conventions
- **Read-Only SQLite**: Database access is strictly read-only (`sqlite3 -safe -readonly`).
- **Immutable References**: Never edit database files directly without explicit authorization.

## 4. Git Discipline & Safety
- **Explicit File Staging**: Only stage explicit file paths (`git add <path>`). Indiscriminate staging (`git add -A`, `git add .`, `git add -u`, `git commit -a`) is prohibited.
- **Commit Authorship**: Never append AI attribution trailers (`Co-authored-by: ...`).
- **Commit Responsibility**: Autonomous agents stage and verify; operator reviews and pushes.
"""
    if runbook_excerpt:
        content += f"\n---\n\n## Reference Runbook Excerpt\n```markdown\n{runbook_excerpt}\n```\n"

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
- **Rationale**: Pre-computed database snapshots are treated as immutable references.
- **Action on Violation**: Immediate execution block and task abort.

## 2. Cost Safety & Rate Throttling
- **Rule**: Autonomous agents must not execute unbudgeted full sweeps or large paid external API jobs.
- **Rationale**: Avoid uncontrolled quota or credit consumption without operator approval.

## 3. Git Operations & Repository Integrity
- **Rule**:
  - Bulk staging (`git add -A`, `git add .`, `git add --all`, `git add -u`) is strictly forbidden. Files must be added explicitly by path.
  - Automatic `git push` or `git merge` is disabled.
  - AI attribution signatures (`Co-authored-by: ...`) in git commit messages are blocked.
- **Rationale**: Prevent accidental leakage of sensitive files or unintended commits.

## 4. Database Query Safety
- **Rule**: SQLite database queries must be strictly read-only (`sqlite3 -safe -readonly` or `SELECT` statements only). `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER` are blocked.

## 5. Verification Before Stop (Quality Gate)
- **Rule**: Before any task or iteration is declared successful, verification checks must pass.
- **Action on Failure**: Agent must inspect failures and fix them or halt with a report.
"""
    _ensure_dir(dest_path.parent)
    dest_path.write_text(content, encoding="utf-8")


def _migrate_hooks(
    project_path: Path,
    target_hooks_dir: Path,
) -> List[str]:
    """Copy all safety hooks into projects/<project>/hooks/ and ensure chmod +x."""
    _ensure_dir(target_hooks_dir)
    migrated: List[str] = []

    hook_sources = [
        project_path / ".claude" / "hooks",
        project_path / ".cursor" / "hooks",
        project_path / ".agents" / "hooks",
    ]

    for h_dir in hook_sources:
        if not h_dir.exists():
            continue
        for h_file in h_dir.glob("*.sh"):
            target_file = target_hooks_dir / h_file.name
            shutil.copy2(h_file, target_file)
            target_file.chmod(target_file.stat().st_mode | 0o111)
            if h_file.name not in migrated:
                migrated.append(h_file.name)

    return sorted(migrated)


def _migrate_rules(
    project_path: Path,
    target_rules_dir: Path,
) -> List[str]:
    """Migrate operational rules into projects/<project>/rules/."""
    _ensure_dir(target_rules_dir)
    migrated: List[str] = []

    # 1. Cursor rules
    cursor_rules_dir = project_path / ".cursor" / "rules"
    if cursor_rules_dir.exists():
        for r_file in cursor_rules_dir.glob("*.mdc"):
            rule_stem = r_file.stem
            dest_file = target_rules_dir / f"{rule_stem}.md"
            content = r_file.read_text(encoding="utf-8")
            dest_file.write_text(content, encoding="utf-8")
            migrated.append(rule_stem)

    # 2. Add standard safety rules
    db_rule = target_rules_dir / "protected-databases.md"
    db_rule.write_text("""# Rule: Protected Taxonomy Database Snapshots
Files under `database/` are versioned SQLite taxonomy snapshots built outside this repository.
Never edit or overwrite anything under `database/`. Any modification attempt is immediately blocked.
""", encoding="utf-8")
    if "protected-databases" not in migrated:
        migrated.append("protected-databases")

    git_rule = target_rules_dir / "git-discipline.md"
    git_rule.write_text("""# Rule: Git Discipline & Staging
1. Never use `git add -A`, `git add .`, or `git add -u`. Stage files explicitly by path.
2. Never commit with AI co-authorship tags (`Co-authored-by:`).
3. The human operator controls pushing to remote (`git push`).
""", encoding="utf-8")
    if "git-discipline" not in migrated:
        migrated.append("git-discipline")

    return sorted(migrated)


def _migrate_project_skills(
    project_path: Path,
    project_name: str,
    target_skills_dir: Path,
) -> List[str]:
    """Migrate domain skills from Claude agents, Cursor skills, and workflows."""
    _ensure_dir(target_skills_dir)
    created: List[str] = []

    # 1. Claude agents
    claude_agents_dir = project_path / ".claude" / "agents"
    if claude_agents_dir.exists():
        for agent_file in claude_agents_dir.glob("*.md"):
            skill_name = agent_file.stem
            skill_dir = target_skills_dir / skill_name
            _ensure_dir(skill_dir)
            target_skill_file = skill_dir / "SKILL.md"

            raw_content = agent_file.read_text(encoding="utf-8")
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
            if skill_name not in created:
                created.append(skill_name)

    # 2. Cursor skills (e.g. icd10am-achi, icd10cm-pcs, analyze-runs)
    cursor_skills_dir = project_path / ".cursor" / "skills"
    if cursor_skills_dir.exists():
        for c_skill_dir in cursor_skills_dir.iterdir():
            if c_skill_dir.is_dir():
                s_name = c_skill_dir.name
                target_dir = target_skills_dir / s_name
                _ensure_dir(target_dir)
                for item in c_skill_dir.glob("*"):
                    if item.is_file():
                        shutil.copy2(item, target_dir / item.name)
                if s_name not in created:
                    created.append(s_name)

    # 3. Claude workflows
    claude_wf_dir = project_path / ".claude" / "workflows"
    if claude_wf_dir.exists():
        for wf_file in sorted(claude_wf_dir.glob("*.js")):
            wf_name = wf_file.stem
            wf_dir = target_skills_dir / wf_name
            _ensure_dir(wf_dir)
            wf_skill_file = wf_dir / "SKILL.md"
            wf_code = wf_file.read_text(encoding="utf-8")
            wf_content = f"""---
name: {wf_name}
description: Migrated workflow {wf_name} for {project_name}
---

## Objective
Automated workflow migrated from Claude configuration.

## Workflow Implementation
```javascript
{wf_code}
```
"""
            wf_skill_file.write_text(wf_content, encoding="utf-8")
            if wf_name not in created:
                created.append(wf_name)

    return sorted(created)


def _migrate_global_skills(
    project_path: Path,
    target_global_skills_dir: Path,
) -> List[str]:
    """Migrate reusable global engineering skills into root skills/."""
    _ensure_dir(target_global_skills_dir)
    created: List[str] = []

    # 1. catchup
    claude_catchup = project_path / ".claude" / "skills" / "catchup" / "SKILL.md"
    catchup_dir = target_global_skills_dir / "catchup"
    _ensure_dir(catchup_dir)
    if claude_catchup.exists():
        shutil.copy2(claude_catchup, catchup_dir / "SKILL.md")
    created.append("catchup")

    # 2. pr
    claude_pr = project_path / ".claude" / "skills" / "pr" / "SKILL.md"
    pr_dir = target_global_skills_dir / "pr"
    _ensure_dir(pr_dir)
    if claude_pr.exists():
        shutil.copy2(claude_pr, pr_dir / "SKILL.md")
    created.append("pr")

    # 3. fix-until-green
    fix_dir = target_global_skills_dir / "fix-until-green"
    _ensure_dir(fix_dir)
    fix_skill = fix_dir / "SKILL.md"
    fix_content = """---
name: fix-until-green
description: Iterative test fixing loop until all tests pass or 2 stalled rounds
---

## Procedure
1. Run test suite: `env/bin/python -m unittest discover -s tests -t .`.
2. If all tests pass, mark green and complete.
3. If failures occur:
   - Analyze failure tracebacks.
   - Apply minimal correct fix to the implementation code.
   - Rerun test suite.
4. If 2 consecutive rounds make no progress, halt and report.
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
1. Run repository test suite (`env/bin/python -m unittest discover -s tests -t .`).
2. Verify git status has no stray, dirty, or broken edits.
3. If tests fail, report failure and do NOT complete task.
"""
    stop_skill.write_text(stop_content, encoding="utf-8")
    created.append("verify-before-stop")

    # 5. Selected global skills from .agents/skills/
    agents_skills_dir = project_path / ".agents" / "skills"
    promoted_global_skills = [
        "tdd",
        "code-review",
        "diagnosing-bugs",
        "grill-me",
        "grill-with-docs",
        "git-guardrails-claude-code",
    ]
    if agents_skills_dir.exists():
        for skill_name in promoted_global_skills:
            src_skill_dir = agents_skills_dir / skill_name
            if src_skill_dir.exists() and src_skill_dir.is_dir():
                dest_skill_dir = target_global_skills_dir / skill_name
                _ensure_dir(dest_skill_dir)
                for f in src_skill_dir.glob("*"):
                    if f.is_file():
                        shutil.copy2(f, dest_skill_dir / f.name)
                if skill_name not in created:
                    created.append(skill_name)

    return sorted(created)


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

    migration_dir = out_root / "migration" / p_name
    snapshot_dir = migration_dir / "original"
    project_dir = out_root / "projects" / p_name
    project_skills_dir = project_dir / "skills"
    project_hooks_dir = project_dir / "hooks"
    project_rules_dir = project_dir / "rules"
    global_skills_dir = out_root / "skills"

    # 1. Clean snapshot of original files
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

    conventions_md_file = project_dir / "conventions.md"
    _generate_conventions_md(src_proj, p_name, conventions_md_file)

    safety_md_file = project_dir / "safety.md"
    _generate_safety_md(p_name, safety_md_file)

    # 4. Hooks & Rules
    migrated_hooks = _migrate_hooks(src_proj, project_hooks_dir)
    migrated_rules = _migrate_rules(src_proj, project_rules_dir)

    # 5. Project-specific skills
    project_skills = _migrate_project_skills(src_proj, p_name, project_skills_dir)

    # 6. Global skills
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
        hooks_migrated=migrated_hooks,
        rules_migrated=migrated_rules,
        inventory_path=inventory_file,
        manifest_path=manifest_file,
        project_yaml_path=project_yaml_file,
        safety_md_path=safety_md_file,
        context_md_path=context_md_file,
        conventions_md_path=conventions_md_file,
    )
