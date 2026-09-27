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


# --- Secrets: secret-looking untracked and ignored files stay out of the copy. ---


def _secrets(repo):
    with open(repo / ".gitignore", "a", encoding="utf-8") as f:
        f.write(".env\nconfig/\n")
    (repo / ".env").write_text("API_KEY=real\n", encoding="utf-8")                # ignored
    (repo / ".env.example").write_text("API_KEY=\n", encoding="utf-8")            # untracked
    (repo / ".env.local").write_text("API_KEY=real\n", encoding="utf-8")          # untracked
    (repo / "config").mkdir()
    (repo / "config" / "server.pem").write_text("-----BEGIN-----\n", encoding="utf-8")
    (repo / "config" / "settings.toml").write_text("debug = true\n", encoding="utf-8")
    (repo / "src" / "deep").mkdir()
    (repo / "src" / "deep" / ".env").write_text("TOKEN=real\n", encoding="utf-8")
    (repo / "id_ed25519").write_text("private\n", encoding="utf-8")
    (repo / "id_ed25519.pub").write_text("public\n", encoding="utf-8")


def test_secret_looking_files_are_withheld_and_listed(repo, tmp_path):
    _secrets(repo)
    ws = Workspace.create(repo, tmp_path / "ws")
    for gone in (".env", ".env.local", "config/server.pem", "src/deep/.env", "id_ed25519"):
        assert not (ws.path / gone).exists(), gone
    for kept in (".env.example", "config/settings.toml", "id_ed25519.pub"):
        assert (ws.path / kept).exists(), kept
    assert ws.withheld == sorted(
        [".env", ".env.local", "config/server.pem", "src/deep/.env", "id_ed25519"])


def test_allow_secrets_lets_matching_paths_through(repo, tmp_path):
    _secrets(repo)
    ws = Workspace.create(repo, tmp_path / "ws", allow_secrets=(".env", "config/*.pem"))
    assert (ws.path / ".env").read_text() == "API_KEY=real\n"
    assert (ws.path / "src" / "deep" / ".env").exists()  # a basename pattern matches at any depth
    assert (ws.path / "config" / "server.pem").exists()
    assert ws.withheld == [".env.local", "id_ed25519"]


def test_secret_matching_ignores_case(repo, tmp_path):
    (repo / "config").mkdir()
    for name in (".ENV", "config/Server.PEM", "Id_Rsa", ".Env.Example"):
        (repo / name).write_text("x\n", encoding="utf-8")
    ws = Workspace.create(repo, tmp_path / "ws")
    assert ws.withheld == [".ENV", "Id_Rsa", "config/Server.PEM"]
    assert (ws.path / ".Env.Example").exists()  # a template in any case is still a template


def test_allow_secrets_ignores_case_too(repo, tmp_path):
    (repo / "config").mkdir()
    (repo / ".ENV").write_text("A=1\n", encoding="utf-8")
    (repo / "config" / "Server.PEM").write_text("x\n", encoding="utf-8")
    ws = Workspace.create(repo, tmp_path / "ws", allow_secrets=(".env", "CONFIG/*.pem"))
    assert ws.withheld == []
    assert (ws.path / ".ENV").exists() and (ws.path / "config" / "Server.PEM").exists()

def test_a_staged_new_secret_is_withheld_too(repo, tmp_path):
    (repo / "prod.key").write_text("secret\n", encoding="utf-8")
    (repo / "notes.txt").write_text("todo\n", encoding="utf-8")
    subprocess.run(["git", "add", "prod.key", "notes.txt"], cwd=repo, check=True)
    ws = Workspace.create(repo, tmp_path / "ws")
    assert not (ws.path / "prod.key").exists()
    assert (ws.path / "notes.txt").exists()
    assert ws.withheld == ["prod.key"]


def test_a_tracked_secret_is_already_in_the_clone(repo, tmp_path):
    (repo / ".env").write_text("A=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "env"],
                   cwd=repo, check=True)
    ws = Workspace.create(repo, tmp_path / "ws")
    assert (ws.path / ".env").exists()
    assert ws.withheld == []


# Lane: workspace review fixes.

def _untracked(repo, rel, text="x\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_a_provision_exclude_matches_only_that_repo_path(repo, tmp_path):
    """Provisioning `models` must not drop an untracked src/models/*.py."""
    _untracked(repo, "models/weights.bin")
    _untracked(repo, "src/models/transformer.py")
    ws = Workspace.create(repo, tmp_path / "ws", exclude=("models",))
    assert (ws.path / "src" / "models" / "transformer.py").exists()
    assert not (ws.path / "models").exists()


def test_a_provision_exclude_is_normalized(repo, tmp_path):
    _untracked(repo, "data/big.bin")
    ws = Workspace.create(repo, tmp_path / "ws", exclude=("./data/",))
    assert not (ws.path / "data").exists()


def test_clone_fallback_replaces_what_a_failed_clonefile_left(repo, tmp_path, monkeypatch):
    """macOS `cp -Rc` can create dst before clonefile fails; `cp -R` onto it
    would then copy into dst/<name>."""
    import os
    import shutil
    real_cp = shutil.which("cp")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "cp"
    fake.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "-Rc" ]; then mkdir -p "$3"; echo partial > "$3/leftover"; exit 1; fi\n'
        f'exec {real_cp} "$@"\n'
    )
    fake.chmod(0o755)
    ws = Workspace.create(repo, tmp_path / "ws")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert ws.provision([{"path": "env/", "mode": "clone"}]) == ["env/"]
    assert (ws.path / "env" / "bin" / "marker").exists()
    assert not (ws.path / "env" / "env").exists()
    assert not (ws.path / "env" / "leftover").exists()


def test_a_relative_destination_is_made_absolute(repo, tmp_path, monkeypatch):
    """The clone runs from the source's parent and the rest from the cwd; a
    relative path must mean the same place to both."""
    monkeypatch.chdir(repo)
    ws = Workspace.create(repo, "../jobs/x/repo", git_dir="../jobs/x/git")
    assert ws.path == tmp_path / "jobs" / "x" / "repo"
    assert (ws.path / "src" / "app.py").exists()
    assert not (tmp_path.parent / "jobs").exists()


def test_a_non_utf8_untracked_name_is_copied(repo, tmp_path):
    import os
    name = os.fsdecode(b"caf\xe9.txt")
    (repo / name).write_text("latin-1 name\n", encoding="utf-8")
    ws = Workspace.create(repo, tmp_path / "ws")
    assert (ws.path / name).read_text(encoding="utf-8") == "latin-1 name\n"


def test_environment_names_are_skipped_only_where_they_are_environments(repo, tmp_path):
    _untracked(repo, "src/env/server.ts")
    _untracked(repo, "web/venv/index.ts")
    _untracked(repo, "tools/venv/pyvenv.cfg", "home = /usr\n")
    _untracked(repo, "tools/venv/lib/site.py")
    _untracked(repo, "pkg/node_modules/dep/index.js")
    ws = Workspace.create(repo, tmp_path / "ws")
    assert (ws.path / "src" / "env" / "server.ts").exists()
    assert (ws.path / "web" / "venv" / "index.ts").exists()
    assert not (ws.path / "tools" / "venv").exists()
    assert not (ws.path / "pkg" / "node_modules").exists()
    assert not (ws.path / "env").exists(), "a top-level env/ is still an environment"
