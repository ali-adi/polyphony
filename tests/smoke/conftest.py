"""Fixtures for smoke tests that spawn real executor CLI binaries."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    """A real git repo with one commit, safe for an agent to modify."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    (repo / "hello.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c", "user.name=polyphony-test",
            "-c", "user.email=test@localhost",
            "commit", "-q", "-m", "init",
        ],
        cwd=repo,
        check=True,
    )
    return repo
