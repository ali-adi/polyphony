"""Tests for migration scanner, classifier, and translator."""

import tempfile
from pathlib import Path
import pytest
import yaml

from migrate.scanner import scan_project
from migrate.classifier import classify_items, ClassificationScope
from migrate.translator import translate_project


@pytest.fixture
def mock_repo(tmp_path):
    """Create a mock repository with Claude, Cursor, and AGY AI configurations."""
    # .claude/
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "db-reader.md").write_text("# DB Reader Agent\nInspect taxonomy tables in readonly mode.")
    (tmp_path / ".claude" / "agents" / "pcs-editor.md").write_text("# PCS Editor Agent\nSurgical code edits.")

    (tmp_path / ".claude" / "skills" / "catchup").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "catchup" / "SKILL.md").write_text("---\nname: catchup\n---\nSummarize branch")

    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "protect-databases.sh").write_text("#!/bin/bash\necho blocked database edit")
    (tmp_path / ".claude" / "hooks" / "verify-before-stop.sh").write_text("#!/bin/bash\necho verify tests")

    (tmp_path / ".claude" / "workflows").mkdir(parents=True)
    (tmp_path / ".claude" / "workflows" / "fix-until-green.js").write_text("// fix until green workflow")

    (tmp_path / ".claude" / "settings.json").write_text('{"permissions": {"deny": ["Edit(/database/**)"]}}')

    # .cursor/
    (tmp_path / ".cursor" / "hooks").mkdir(parents=True)
    (tmp_path / ".cursor" / "hooks" / "claude-adapter.sh").write_text("#!/bin/bash\necho cursor hook adapter")
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    (tmp_path / ".cursor" / "rules" / "am-full-runs.mdc").write_text("Rule: block unbudgeted full runs")

    # .agents/
    (tmp_path / ".agents").mkdir(parents=True)
    (tmp_path / ".agents" / "hooks.json").write_text('{"hooks": []}')

    # .mcp.json and .env and README.md
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {}}')
    (tmp_path / ".env").write_text('SECRET_GEMINI_KEY="super-secret-key"')
    (tmp_path / "README.md").write_text("# Mock Project\nTest project documentation.")

    return tmp_path


def test_scan_project(mock_repo):
    items = scan_project(mock_repo)
    rel_paths = [item.rel_path for item in items]

    assert ".claude/agents/db-reader.md" in rel_paths
    assert ".claude/skills/catchup/SKILL.md" in rel_paths
    assert ".claude/hooks/protect-databases.sh" in rel_paths
    assert ".cursor/rules/am-full-runs.mdc" in rel_paths
    assert ".mcp.json" in rel_paths
    assert ".env" in rel_paths
    assert "README.md" in rel_paths


def test_classify_items(mock_repo):
    items = scan_project(mock_repo)
    classified = classify_items(items, "mock_project")

    classified_by_path = {c.item.rel_path: c for c in classified}

    # Sensitive
    assert classified_by_path[".env"].scope == ClassificationScope.SENSITIVE
    assert classified_by_path[".env"].action == "security_block"

    # Global skills
    assert classified_by_path[".claude/skills/catchup/SKILL.md"].scope == ClassificationScope.GLOBAL
    # Hooks
    assert classified_by_path[".claude/hooks/verify-before-stop.sh"].scope == ClassificationScope.PROJECT
    assert classified_by_path[".claude/hooks/protect-databases.sh"].scope == ClassificationScope.PROJECT
    assert classified_by_path[".cursor/rules/am-full-runs.mdc"].scope == ClassificationScope.PROJECT

    # Executor adapter
    assert classified_by_path[".cursor/hooks/claude-adapter.sh"].scope == ClassificationScope.EXECUTOR


def test_translate_project(mock_repo, tmp_path):
    out_root = tmp_path / "orch_root"
    out_root.mkdir()

    items = scan_project(mock_repo)
    classified = classify_items(items, "mock_project")

    report = translate_project(
        project_path=mock_repo,
        output_root=out_root,
        classified_items=classified,
        project_name="mock_project",
    )

    assert report.inventory_path.exists()
    assert report.manifest_path.exists()
    assert report.project_yaml_path.exists()
    assert report.safety_md_path.exists()
    assert report.context_md_path.exists()

    # Verify original snapshot does NOT contain .env
    original_env = out_root / "migration" / "mock_project" / "original" / ".env"
    assert not original_env.exists()

    # Verify project.yaml is valid YAML and has safety rules
    with open(report.project_yaml_path) as f:
        proj_yaml = yaml.safe_load(f)
    assert proj_yaml["name"] == "mock_project"
    assert "database/" in proj_yaml["safety"]["protected_paths"]
    assert "git push" in proj_yaml["safety"]["blocked_commands"]

    # Verify global skills created
    assert "catchup" in report.global_skills_created
    assert (out_root / "skills" / "catchup" / "SKILL.md").exists()
    assert (out_root / "skills" / "fix-until-green" / "SKILL.md").exists()

    # Verify project skills created
    assert "db-reader" in report.project_skills_created
    assert (out_root / "projects" / "mock_project" / "skills" / "db-reader" / "SKILL.md").exists()
