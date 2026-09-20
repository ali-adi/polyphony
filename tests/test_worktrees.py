"""Tests for Worktree-Based Parallelism (Section 33: Worktree-Based Parallelism)."""

import subprocess
import tempfile
from pathlib import Path
import pytest

from orchestrator.worktrees import WorktreeManager


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@polyphony.ai"], cwd=repo, check=True, capture_output=True)

    init_file = repo / "README.md"
    init_file.write_text("# Initial Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)
    return repo


def test_section_33_worktree_parallelism_and_merge_decision(git_repo):
    """Verify Section 33 workflow:
    main working tree
          │
          ├── worktree A → implementation
          ├── worktree B → alternative implementation
          └── worktree C → investigation
                             ↓
                         reviewer
                             ↓
                        merge decision
    """
    mgr = WorktreeManager(git_repo)

    # 1. Create worktree A (implementation)
    wt_a = mgr.create_worktree(purpose="implementation")
    assert wt_a.path.exists()

    # 2. Create worktree B (alternative implementation)
    wt_b = mgr.create_worktree(purpose="alternative")
    assert wt_b.path.exists()

    # 3. Create worktree C (investigation)
    wt_c = mgr.create_worktree(purpose="investigation")
    assert wt_c.path.exists()

    # Make change in Worktree A
    file_a = wt_a.path / "feature.py"
    file_a.write_text("# Implementation A\ndef run(): return 'A'\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.py"], cwd=wt_a.path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add feature A"], cwd=wt_a.path, check=True, capture_output=True)

    # Make change in Worktree B
    file_b = wt_b.path / "feature.py"
    file_b.write_text("# Implementation B (Alternative)\ndef run(): return 'B'\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.py"], cwd=wt_b.path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add feature B"], cwd=wt_b.path, check=True, capture_output=True)

    # Verify main working tree was NOT modified yet!
    assert not (git_repo / "feature.py").exists()

    # 4. Reviewer decides to merge Worktree A
    decision = mgr.merge_decision(chosen_wt_id=wt_a.id, target_branch="main")
    assert decision["success"] is True
    assert decision["chosen_worktree"] == wt_a.id
    assert wt_b.id in decision["cleaned_up_candidates"]

    # Verify main working tree now has feature.py from Implementation A
    assert (git_repo / "feature.py").exists()
    assert "Implementation A" in (git_repo / "feature.py").read_text(encoding="utf-8")

    # Verify non-chosen worktrees were cleaned up
    assert not wt_b.path.exists()

    mgr.cleanup_all()
