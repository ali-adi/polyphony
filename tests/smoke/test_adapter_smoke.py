"""Real-subprocess smoke tests. These consume subscription quota.

Run explicitly:  pytest tests/smoke -m smoke -v
"""

from __future__ import annotations

import pytest

from polyphony.executors.agy import AgyExecutor
from polyphony.executors.base import Mode
from polyphony.executors.claude import ClaudeExecutor
from polyphony.executors.cursor import CursorExecutor

SENTINEL = "POLYPHONY_OK"
PROMPT = f"Reply with exactly this one word and nothing else: {SENTINEL}"

# This account is out of usage on cursor's default model, and --model auto
# returns the same quota error despite the error text recommending it.
# composer-2.5 is verified working.
CURSOR_MODEL = "composer-2.5"


def _assert_responded(res, executor_name: str):
    assert res.exit_code == 0, (
        f"{executor_name} exited {res.exit_code}\n"
        f"stdout: {res.output[:500]}\nstderr: {res.error}"
    )
    assert res.output.strip(), f"{executor_name} returned empty output"
    assert SENTINEL in res.output, (
        f"{executor_name} did not echo the sentinel.\nGot: {res.output[:500]}"
    )


@pytest.mark.smoke
def test_claude_adapter_responds(scratch_repo):
    ex = ClaudeExecutor()
    if not ex.is_available():
        pytest.skip("claude binary not installed")
    res = ex.execute(
        instruction=PROMPT,
        cwd=str(scratch_repo),
        mode=Mode.REVIEW,
        timeout_seconds=180,
    )
    _assert_responded(res, "claude")


@pytest.mark.smoke
def test_agy_adapter_responds(scratch_repo):
    ex = AgyExecutor()
    if not ex.is_available():
        pytest.skip("agy binary not installed")
    res = ex.execute(
        instruction=PROMPT,
        cwd=str(scratch_repo),
        mode=Mode.REVIEW,
        timeout_seconds=180,
    )
    _assert_responded(res, "agy")


@pytest.mark.smoke
def test_cursor_adapter_responds(scratch_repo):
    ex = CursorExecutor()
    if not ex.is_available():
        pytest.skip("cursor-agent binary not installed")
    res = ex.execute(
        instruction=PROMPT,
        cwd=str(scratch_repo),
        mode=Mode.REVIEW,
        model=CURSOR_MODEL,
        timeout_seconds=180,
    )
    _assert_responded(res, "cursor")
