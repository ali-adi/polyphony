"""Shared fixtures for the job and server test suites."""

import os
import subprocess
import time

import pytest

from polyphony.jobs import JobStore


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r)
    _git("config", "user.email", "t@example.com", cwd=r)
    _git("config", "user.name", "T", cwd=r)
    (r / ".gitignore").write_text("env/\ndata/\n")
    (r / "app.py").write_text("x = 1\n")
    (r / "env").mkdir()
    (r / "env" / "marker").write_text("venv\n")
    (r / "data").mkdir()
    (r / "data" / "big.bin").write_text("data\n")
    _git("add", ".gitignore", "app.py", cwd=r)
    _git("commit", "-q", "-m", "init", cwd=r)
    return r


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "home")


@pytest.fixture
def fake_agy(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def make(body):
        script = bin_dir / "agy"
        script.write_text(f"#!/bin/sh\n{body}\n")
        script.chmod(0o755)

    return make


@pytest.fixture
def wait_for():
    def _wait_for(store, job_id, states, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = store.refresh(store.load(job_id))
            if job.state in states:
                return job
            time.sleep(0.1)
        raise AssertionError(f"job {job_id} stayed {job.state}")

    return _wait_for
