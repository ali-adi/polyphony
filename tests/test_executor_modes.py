"""Mode resolution and per-adapter argv construction."""

import pytest

from executors.base import Mode, resolve_mode


def test_explicit_mode_wins_over_read_only():
    assert resolve_mode(Mode.CODE, read_only=True) is Mode.CODE
    assert resolve_mode(Mode.REVIEW, read_only=False) is Mode.REVIEW


def test_string_modes_accepted():
    assert resolve_mode("review") is Mode.REVIEW
    assert resolve_mode("code") is Mode.CODE


def test_read_only_bridges_to_review_when_mode_absent():
    assert resolve_mode(None, read_only=True) is Mode.REVIEW


def test_defaults_to_code():
    assert resolve_mode(None, read_only=False) is Mode.CODE


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        resolve_mode("yolo")
