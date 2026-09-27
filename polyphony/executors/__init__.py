"""Subprocess adapters for agent CLIs."""

from polyphony.executors.agy import AgyExecutor
from polyphony.executors.base import BaseExecutor, ExecutorResult, Mode
from polyphony.executors.claude import ClaudeExecutor
from polyphony.executors.codex import CodexExecutor
from polyphony.executors.cursor import CursorExecutor
from polyphony.executors.gemini import GeminiExecutor
from polyphony.executors.opencode import OpencodeExecutor

# codex, gemini and opencode are opt-in: never in DEFAULT_POOL, only used
# when a project's pool names them or a caller asks for one.
EXECUTORS: dict[str, type[BaseExecutor]] = {
    "claude": ClaudeExecutor,
    "agy": AgyExecutor,
    "cursor": CursorExecutor,
    "codex": CodexExecutor,
    "gemini": GeminiExecutor,
    "opencode": OpencodeExecutor,
}

__all__ = [
    "AgyExecutor", "BaseExecutor", "ClaudeExecutor", "CodexExecutor", "CursorExecutor",
    "EXECUTORS", "ExecutorResult", "GeminiExecutor", "Mode", "OpencodeExecutor",
]
