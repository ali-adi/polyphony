"""Adapters must not disguise Polyphony's own bugs as executor failures."""

import subprocess

import pytest

from polyphony.executors.agy import AgyExecutor
from polyphony.executors.base import Mode
from polyphony.executors.claude import ClaudeExecutor
from polyphony.executors.cursor import CursorExecutor

ADAPTERS = [
    (ClaudeExecutor, "claude"),
    (AgyExecutor, "agy"),
    (CursorExecutor, "cursor"),
]


@pytest.fixture(autouse=True)
def _reset_cursor_availability_cache():
    """CursorExecutor caches availability on the CLASS, shared by every instance.

    A test that makes a probe fail would otherwise mark cursor unavailable
    for every later test in the same process (300s TTL).
    """
    CursorExecutor._class_is_agent_ready = None
    CursorExecutor._class_last_checked = 0.0
    yield
    CursorExecutor._class_is_agent_ready = None
    CursorExecutor._class_last_checked = 0.0


@pytest.mark.parametrize("cls,name", ADAPTERS, ids=[n for _, n in ADAPTERS])
def test_programming_errors_propagate(cls, name, tmp_path, monkeypatch):
    """A NameError in our own code must not become 'the CLI failed'."""
    def boom(*a, **k):
        raise NameError("name 'session_id' is not defined")

    monkeypatch.setattr(subprocess, "run", boom)
    ex = cls(binary_path="/bin/echo")

    with pytest.raises(NameError):
        ex.execute(instruction="hi", cwd=str(tmp_path), mode=Mode.CODE)


@pytest.mark.parametrize("cls,name", ADAPTERS, ids=[n for _, n in ADAPTERS])
def test_environment_errors_become_failed_results(cls, name, tmp_path, monkeypatch):
    """A missing binary is a real executor failure, not a crash."""
    def missing(*a, **k):
        raise FileNotFoundError("No such file or directory: 'binary'")

    monkeypatch.setattr(subprocess, "run", missing)
    ex = cls(binary_path="/bin/echo")

    res = ex.execute(instruction="hi", cwd=str(tmp_path), mode=Mode.CODE)
    assert res.success is False
    assert res.error, "a failed result must explain itself"
