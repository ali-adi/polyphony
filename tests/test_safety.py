"""Tests for SafetyEngine."""

import pytest
from orchestrator.safety import SafetyEngine, SafetyConfig


def test_safety_blocked_commands():
    engine = SafetyEngine()

    safe_cmd = "python -m unittest discover -s tests -t ."
    ok, reason = engine.validate_command(safe_cmd)
    assert ok is True
    assert reason is None

    blocked_cmds = [
        "git push origin main",
        "git merge feature-branch",
        "git add -A",
        "git add .",
        "git commit -am 'test'",
        "rm -rf /",
    ]
    for cmd in blocked_cmds:
        ok, reason = engine.validate_command(cmd)
        assert ok is False
        assert "Blocked by safety policy" in reason


def test_safety_cost_controls():
    config = SafetyConfig(require_approval_for=["configs/full.yml", "--force-full"])
    engine = SafetyEngine(config=config)

    expensive_cmd = "python -m medicoder.main --config configs/full.yml"
    ok, reason = engine.validate_command(expensive_cmd)
    assert ok is False
    assert "operator approval" in reason

    tuning_cmd = "python scripts/tune_level.py --force-full"
    ok, reason = engine.validate_command(tuning_cmd)
    assert ok is False


def test_safety_protected_paths(tmp_path):
    config = SafetyConfig(protected_paths=["database/", "**/database/**"])
    engine = SafetyEngine(config=config, project_root=str(tmp_path))

    db_path = str(tmp_path / "database" / "snapshot.db")
    ok, reason = engine.validate_path_modification(db_path)
    assert ok is False
    assert "protected location" in reason

    safe_path = str(tmp_path / "medicoder" / "pipeline.py")
    ok, reason = engine.validate_path_modification(safe_path)
    assert ok is True


def test_safety_read_only_mode(tmp_path):
    config = SafetyConfig(read_only=True)
    engine = SafetyEngine(config=config, project_root=str(tmp_path))

    ok, reason = engine.validate_path_modification(str(tmp_path / "file.py"))
    assert ok is False
    assert "read-only mode" in reason

    ok, reason = engine.validate_command("git commit -m 'hello'")
    assert ok is False
    assert "read-only mode" in reason
