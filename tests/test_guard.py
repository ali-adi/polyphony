import os
import shutil
import subprocess
import sys

import pytest

from polyphony.guard import ForbiddenGitCommand, run_git


def test_plain_push_is_refused(tmp_path):
    with pytest.raises(ForbiddenGitCommand):
        run_git(["push"], cwd=str(tmp_path))


def test_push_behind_global_flags_is_refused(tmp_path):
    for args in (
        ["--no-pager", "push"],
        ["-C", "/somewhere", "push"],
        ["-c", "user.name=x", "push", "origin", "main"],
        ["--git-dir", "/x/.git", "push"],
    ):
        with pytest.raises(ForbiddenGitCommand):
            run_git(args, cwd=str(tmp_path))


def test_push_is_refused_before_spawning(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a))
    with pytest.raises(ForbiddenGitCommand):
        run_git(["push"], cwd=str(tmp_path))
    assert spawned == [], "guard must refuse before any process is created"


def test_ordinary_commands_pass_through(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    res = run_git(["status", "--porcelain"], cwd=str(tmp_path))
    assert res.returncode == 0


def test_words_containing_push_are_not_refused(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    res = run_git(["branch", "--list", "pushover"], cwd=str(tmp_path))
    assert res.returncode == 0


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("xcrun"), reason="macOS shim")
def test_the_xcrun_git_shim_is_skipped(monkeypatch):
    from polyphony import guard
    monkeypatch.setattr(guard.shutil, "which", lambda name: "/usr/bin/git")
    guard.git_binary.cache_clear()
    try:
        real = guard.git_binary()
        assert real != "/usr/bin/git" and os.access(real, os.X_OK)
    finally:
        guard.git_binary.cache_clear()
