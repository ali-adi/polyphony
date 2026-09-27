"""Real CLIs. Reads usage only; spends no model quota."""

import pytest

from polyphony.usage import agy_usage, cursor_usage


@pytest.mark.smoke
def test_agy_usage_real():
    result = agy_usage()
    if result.get("error") == "agy is not installed.":
        pytest.skip("agy not installed")
    assert result["ok"] is True, result
    assert result["limits"]


@pytest.mark.smoke
def test_cursor_usage_real():
    result = cursor_usage()
    if result.get("error") == "cursor-agent is not installed.":
        pytest.skip("cursor-agent not installed")
    assert result["ok"] is True, result
    assert result["categories"]
