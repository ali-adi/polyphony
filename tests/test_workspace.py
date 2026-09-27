"""A job's workspace: a private copy of the repository."""

import subprocess

import pytest

from polyphony.workspace import ProvisionError, Workspace, WorkspaceError


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


def test_clone_mode_materializes_a_gitignored_path(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    ws.provision([{"path": "env/", "mode": "clone"}])
    assert (ws.path / "env" / "bin" / "marker").exists()


def test_clone_is_a_copy_not_a_link(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    ws.provision([{"path": "env/", "mode": "clone"}])
    marker = ws.path / "env" / "bin" / "marker"
    assert not marker.is_symlink()
    marker.write_text("changed in the copy\n", encoding="utf-8")
    original = repo / "env" / "bin" / "marker"
    assert original.read_text(encoding="utf-8") == "venv\n", (
        "a clone must not write through to the source"
    )


def test_link_mode_creates_a_symlink(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    ws.provision([{"path": "env/", "mode": "link"}])
    assert (ws.path / "env").is_symlink()


def test_missing_source_path_is_fatal(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    with pytest.raises(ProvisionError) as exc:
        ws.provision([{"path": "does_not_exist/", "mode": "clone"}])
    assert "does_not_exist" in str(exc.value)


def test_escaping_paths_are_refused(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    for bad in ("../outside", "/etc"):
        with pytest.raises(ProvisionError):
            ws.provision([{"path": bad, "mode": "clone"}])


def _git_dir_state(repo):
    """Every file under .git with its size and mtime: any write shows up."""
    return {
        str(p.relative_to(repo)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in (repo / ".git").rglob("*")
        if p.is_file()
    }


def test_copy_has_the_committed_files_outside_the_repo(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    assert (ws.path / "src" / "app.py").read_text() == "x = 1\n"
    assert repo not in ws.path.parents


def test_copy_has_no_remote(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    remotes = subprocess.run(["git", "remote"], cwd=ws.path, capture_output=True, text=True)
    assert remotes.stdout.strip() == ""


def test_creating_and_removing_writes_nothing_to_the_repo(repo, tmp_path):
    before = _git_dir_state(repo)
    ws = Workspace.create(repo, tmp_path / "ws")
    ws.provision([{"path": "env/", "mode": "clone"}])
    (ws.path / "src" / "app.py").write_text("x = 2\n")
    subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-qam",
                    "agent", "--no-verify"], cwd=ws.path)  # may fail; irrelevant
    ws.remove()
    assert _git_dir_state(repo) == before
    assert not ws.path.exists()


def test_gitignored_paths_are_absent_before_provisioning(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    assert not (ws.path / "env").exists()


def test_repo_without_commits_is_refused(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=empty, check=True)
    with pytest.raises(WorkspaceError, match="no commits"):
        Workspace.create(empty, tmp_path / "ws")
    assert not (tmp_path / "ws").exists()


def _dirty(repo):
    """Give the repo every kind of uncommitted state the overlay must carry."""
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")          # unstaged edit
    (repo / "src" / "staged.py").write_text("s = 1\n", encoding="utf-8")        # staged new file
    subprocess.run(["git", "add", "src/staged.py"], cwd=repo, check=True)
    (repo / "notes.txt").write_text("todo\n", encoding="utf-8")                  # untracked
    with open(repo / ".gitignore", "a", encoding="utf-8") as f:
        f.write("local/\nnode_modules/\n")
    (repo / "local").mkdir()
    (repo / "local" / "scratch.md").write_text("ignored\n", encoding="utf-8")    # gitignored
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "index.js").write_text("1\n", encoding="utf-8")


def test_overlay_carries_the_working_tree(repo, tmp_path):
    _dirty(repo)
    ws = Workspace.create(repo, tmp_path / "ws")
    assert (ws.path / "src" / "app.py").read_text() == "x = 2\n"
    assert (ws.path / "src" / "staged.py").exists()
    assert (ws.path / "notes.txt").exists()
    assert (ws.path / "local" / "scratch.md").read_text() == "ignored\n"
    assert not (ws.path / "node_modules").exists()
    assert not (ws.path / "env").exists()


def test_overlay_is_committed_as_a_snapshot_so_the_copy_starts_clean(repo, tmp_path):
    _dirty(repo)
    ws = Workspace.create(repo, tmp_path / "ws")
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=ws.path,
                         capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ws.path,
                            capture_output=True, text=True).stdout
    assert log == "polyphony: working-tree snapshot"
    assert status == ""


def test_overlay_carries_deletions(repo, tmp_path):
    (repo / "src" / "app.py").unlink()
    ws = Workspace.create(repo, tmp_path / "ws")
    assert not (ws.path / "src" / "app.py").exists()


def test_clean_repo_gets_no_snapshot_commit(repo, tmp_path):
    ws = Workspace.create(repo, tmp_path / "ws")
    count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=ws.path,
                           capture_output=True, text=True).stdout.strip()
    assert count == "1"


def test_overlay_writes_nothing_to_the_repo(repo, tmp_path):
    _dirty(repo)
    before = _git_dir_state(repo)
    Workspace.create(repo, tmp_path / "ws").remove()
    assert _git_dir_state(repo) == before


def test_overlay_skips_large_files_and_lists_them(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("polyphony.workspace.OVERLAY_MAX_BYTES", 10)
    (repo / "big.txt").write_text("x" * 100, encoding="utf-8")
    ws = Workspace.create(repo, tmp_path / "ws")
    assert ws.skipped == ["big.txt"]
    assert not (ws.path / "big.txt").exists()


def test_polyphonyignore_and_exclude_are_respected(repo, tmp_path):
    _dirty(repo)
    (repo / ".polyphonyignore").write_text("# comment\nlocal/\n", encoding="utf-8")
    ws = Workspace.create(repo, tmp_path / "ws", exclude=("notes.txt",))
    assert not (ws.path / "local").exists()
    assert not (ws.path / "notes.txt").exists()
    assert (ws.path / "src" / "app.py").read_text() == "x = 2\n"
