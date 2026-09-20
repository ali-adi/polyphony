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


from executors.claude_executor import ClaudeExecutor


def test_claude_review_mode_is_plan_and_never_bypasses():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(Mode.REVIEW)
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "--permission-prompts" in argv
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "--dangerously-skip-permissions" not in argv


def test_claude_code_mode_accepts_edits_and_never_bypasses():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(Mode.CODE)
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--dangerously-skip-permissions" not in argv


def test_claude_argv_includes_print_flag_and_model():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(Mode.CODE, model="claude-sonnet-5")
    assert "-p" in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"


from executors.agy_executor import AgyExecutor


def test_agy_review_mode_is_plan_and_sandboxed():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(Mode.REVIEW, cwd="/tmp")
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_agy_code_mode_accepts_edits_and_sandboxed():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(Mode.CODE, cwd="/tmp")
    assert argv[argv.index("--mode") + 1] == "accept-edits"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_agy_passes_workspace_and_effort():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(
        Mode.CODE, cwd="/tmp/work", effort="high"
    )
    assert argv[argv.index("--add-dir") + 1] == "/tmp/work"
    assert argv[argv.index("--effort") + 1] == "high"


from executors.cursor_executor import CursorExecutor


def test_cursor_agent_binary_invokes_without_subcommand():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(Mode.CODE)
    assert argv[0] == "/usr/local/bin/cursor-agent"
    assert argv[1] == "-p"
    assert "agent" not in argv


def test_legacy_cursor_binary_keeps_agent_subcommand():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor").build_argv(Mode.CODE)
    assert argv[1] == "agent"
    assert argv[2] == "-p"


def test_cursor_review_mode_is_plan_and_never_forces():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(Mode.REVIEW)
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "-f" not in argv
    assert "--yolo" not in argv


def test_cursor_code_mode_forces_inside_sandbox():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(Mode.CODE)
    assert "-f" in argv
    assert argv[argv.index("--sandbox") + 1] == "enabled"
    assert "--yolo" not in argv
