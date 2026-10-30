import os
import subprocess
import time

import pytest

from polyphony.jobs import JobStore


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


# A global core.hooksPath would run the user's hooks in every test repo, and planted hooks would write into it.
@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory, monkeypatch):
    config = tmp_path_factory.mktemp("gitconfig") / "config"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


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


# Fake agy: runs the prompt's first paragraph as shell and keeps the prompt and argv beside the copy.
SHELL_AGY = """for a; do case "$a" in -p=*) p="${a#-p=}";; esac; done
printf '%s' "$p" > ../prompt.txt
printf '%s\\n' "$@" > ../argv.txt
eval "$(printf '%s\\n' "$p" | awk 'BEGIN { RS = "" } NR == 1 { print; exit }')"
"""


@pytest.fixture(autouse=True)
def agy_bin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "agy-bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("POLYPHONY_NO_NOTIFY", "1")
    _script(bin_dir / "agy", "echo 'real agy called from tests' >&2; exit 97")
    return bin_dir


def _script(path, body):
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


@pytest.fixture
def fake_agy(agy_bin):
    return lambda body: _script(agy_bin / "agy", body)


@pytest.fixture
def shell_agy(fake_agy):
    fake_agy(SHELL_AGY)


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
