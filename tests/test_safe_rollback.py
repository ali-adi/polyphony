"""Tests for SafeRollbackManager distinguishing user work from Polyphony changes."""

import subprocess
from pathlib import Path
import pytest

from orchestrator.rollback import SafeRollbackManager


def _init_git_repo(path: Path):
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=str(path), capture_output=True, check=True)

    # Initial committed file
    f = path / "committed.txt"
    f.write_text("initial commit content\n", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(path), capture_output=True, check=True)


def test_safe_rollback_preserves_user_preexisting_untracked_files(tmp_path):
    _init_git_repo(tmp_path)

    # User creates their own untracked work
    user_untracked = tmp_path / "user_notes.txt"
    user_untracked.write_text("important user notes that must survive\n", encoding="utf-8")

    mgr = SafeRollbackManager()
    baseline = mgr.record_baseline(tmp_path)
    assert "user_notes.txt" in baseline.untracked_files

    # Polyphony executes and adds an untracked file + touches committed.txt
    poly_file = tmp_path / "polyphony_tmp.py"
    poly_file.write_text("polyphony generated\n", encoding="utf-8")
    (tmp_path / "committed.txt").write_text("polyphony modified\n", encoding="utf-8")

    # Safe rollback
    report = mgr.safe_rollback(baseline)
    assert report.success is True
    assert "polyphony_tmp.py" in report.deleted_untracked_files
    assert not poly_file.exists()

    # User's untracked file MUST be preserved!
    assert user_untracked.exists()
    assert user_untracked.read_text(encoding="utf-8") == "important user notes that must survive\n"
    assert "user_notes.txt" in report.preserved_user_files

    # Committed file is restored to baseline
    assert (tmp_path / "committed.txt").read_text(encoding="utf-8") == "initial commit content\n"


def test_safe_rollback_preserves_user_preexisting_modified_tracked_file(tmp_path):
    _init_git_repo(tmp_path)

    # User modified committed.txt BEFORE Polyphony ran
    committed = tmp_path / "committed.txt"
    committed.write_text("user uncommitted modification\n", encoding="utf-8")

    mgr = SafeRollbackManager()
    # Baseline records user uncommitted edit
    baseline = mgr.record_baseline(tmp_path, relevant_files=["committed.txt"])
    assert "committed.txt" in baseline.tracked_modified_files

    # Polyphony further modifies committed.txt and adds an untracked file
    committed.write_text("polyphony clobbered this\n", encoding="utf-8")
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("bad\n", encoding="utf-8")

    # Safe rollback
    report = mgr.safe_rollback(baseline)
    assert report.success is True

    # User's uncommitted modification must be restored, NOT reset to HEAD!
    assert committed.read_text(encoding="utf-8") == "user uncommitted modification\n"
    assert not bad_file.exists()
