"""Subprocess adapters for agent CLIs."""

from polyphony.executors.agy import AgyExecutor
from polyphony.executors.base import BaseExecutor, ExecutorResult, Mode
from polyphony.executors.claude import ClaudeExecutor
from polyphony.executors.cursor import CursorExecutor

EXECUTORS: dict[str, type[BaseExecutor]] = {
    "claude": ClaudeExecutor,
    "agy": AgyExecutor,
    "cursor": CursorExecutor,
}

__all__ = [
    "AgyExecutor", "BaseExecutor", "ClaudeExecutor", "CursorExecutor",
    "EXECUTORS", "ExecutorResult", "Mode",
]
