"""Worktree lifecycle for task isolation."""

import subprocess
from pathlib import Path

import pytest

from orchestrator.workspace import Workspace


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one commit and a gitignored env/ directory."""
    r = tmp_path / "proj"
    (r / "src").mkdir(parents=True)
    (r / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (r / ".gitignore").write_text("env/\n", encoding="utf-8")
    (r / "env" / "bin").mkdir(parents=True)
    (r / "env" / "bin" / "marker").write_text("venv\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        cwd=r, check=True,
    )
    return r


def test_worktree_is_created_outside_the_repo(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    assert ws.path.exists()
    assert repo not in ws.path.parents, "worktree must not live inside the target repo"
    assert (ws.path / "src" / "app.py").exists()


def test_target_repo_stays_clean(repo, tmp_path):
    Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    res = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    )
    assert res.stdout.strip() == "", f"target repo dirtied: {res.stdout!r}"


def test_gitignored_paths_are_absent_before_provisioning(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    assert not (ws.path / "env").exists(), "a fresh worktree has only tracked files"


def test_branch_is_namespaced_by_task(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    assert ws.branch == "polyphony/task-abc"


def test_remove_leaves_no_trace(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    ws.remove()
    assert not ws.path.exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "polyphony/task-abc"],
        cwd=repo, capture_output=True, text=True,
    )
    assert branches.stdout.strip() == "", "branch should be deleted on removal"


from orchestrator.workspace import ProvisionError


def test_clone_mode_materializes_a_gitignored_path(repo, tmp_path):
    ws = Workspace.create("proj", "task-p1", repo, root=tmp_path / "poly")
    ws.provision([{"path": "env/", "mode": "clone"}])
    assert (ws.path / "env" / "bin" / "marker").exists()


def test_clone_is_a_copy_not_a_link(repo, tmp_path):
    ws = Workspace.create("proj", "task-p2", repo, root=tmp_path / "poly")
    ws.provision([{"path": "env/", "mode": "clone"}])
    marker = ws.path / "env" / "bin" / "marker"
    assert not marker.is_symlink()
    marker.write_text("changed in worktree\n", encoding="utf-8")
    original = repo / "env" / "bin" / "marker"
    assert original.read_text(encoding="utf-8") == "venv\n", (
        "a clone must not write through to the source"
    )


def test_link_mode_creates_a_symlink(repo, tmp_path):
    ws = Workspace.create("proj", "task-p3", repo, root=tmp_path / "poly")
    ws.provision([{"path": "env/", "mode": "link"}])
    assert (ws.path / "env").is_symlink()


def test_missing_source_path_is_fatal(repo, tmp_path):
    ws = Workspace.create("proj", "task-p4", repo, root=tmp_path / "poly")
    with pytest.raises(ProvisionError) as exc:
        ws.provision([{"path": "does_not_exist/", "mode": "clone"}])
    assert "does_not_exist" in str(exc.value)


def test_escaping_paths_are_refused(repo, tmp_path):
    ws = Workspace.create("proj", "task-p5", repo, root=tmp_path / "poly")
    for bad in ("../outside", "/etc"):
        with pytest.raises(ProvisionError):
            ws.provision([{"path": bad, "mode": "clone"}])
