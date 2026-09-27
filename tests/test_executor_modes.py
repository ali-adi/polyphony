"""Per-adapter argv construction."""

from polyphony.executors.base import Mode


from polyphony.executors.claude import ClaudeExecutor


def test_claude_review_mode_is_plan_and_never_bypasses():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv("task", Mode.REVIEW, "/tmp")
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "--permission-prompts" in argv
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "--dangerously-skip-permissions" not in argv


def test_claude_code_mode_accepts_edits_and_never_bypasses():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv("task", Mode.CODE, "/tmp")
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--dangerously-skip-permissions" not in argv


def test_claude_argv_includes_print_flag_and_model():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(
        "task", Mode.CODE, "/tmp", model="claude-sonnet-5"
    )
    assert "-p" in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"


from polyphony.executors.agy import AgyExecutor


def test_agy_review_mode_is_plan_and_sandboxed():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv("task", Mode.REVIEW, cwd="/tmp")
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_agy_code_mode_accepts_edits_and_sandboxed():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv("task", Mode.CODE, cwd="/tmp")
    assert argv[argv.index("--mode") + 1] == "accept-edits"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_agy_passes_workspace():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(
        "task", Mode.CODE, cwd="/tmp/work"
    )
    assert argv[argv.index("--add-dir") + 1] == "/tmp/work"


from polyphony.executors.cursor import CursorExecutor


def test_cursor_agent_binary_invokes_without_subcommand():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(
        "task", Mode.CODE, "/tmp"
    )
    assert argv[0] == "/usr/local/bin/cursor-agent"
    assert argv[1] == "-p"
    assert "agent" not in argv


def test_legacy_cursor_binary_keeps_agent_subcommand():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor").build_argv(
        "task", Mode.CODE, "/tmp"
    )
    assert argv[1] == "agent"
    assert argv[2] == "-p"


def test_cursor_review_mode_is_plan_and_never_forces():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(
        "task", Mode.REVIEW, "/tmp"
    )
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "-f" not in argv
    assert "--yolo" not in argv


def test_cursor_code_mode_forces_inside_sandbox():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(
        "task", Mode.CODE, "/tmp"
    )
    assert "-f" in argv
    assert argv[argv.index("--sandbox") + 1] == "enabled"
    assert "--yolo" not in argv


def test_agy_attaches_prompt_to_p_flag():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(
        "do the thing", Mode.CODE, cwd="/tmp"
    )
    assert "-p=do the thing" in argv
    assert "-p" not in argv, "bare -p would swallow the next flag as the prompt"


def test_agy_drops_input_format_flag():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(
        "do the thing", Mode.CODE, cwd="/tmp"
    )
    assert "--input-format" not in argv


def test_agy_prompt_survives_special_characters():
    tricky = 'fix "auth.py" --now; echo $HOME'
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(tricky, Mode.CODE, cwd="/tmp")
    assert f"-p={tricky}" in argv


def test_cursor_review_mode_trusts_workspace():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(
        "analyze this", Mode.REVIEW, "/tmp"
    )
    assert "--trust" in argv
    assert "-f" not in argv, "--trust must not imply command execution"


def test_cursor_code_mode_uses_force_not_trust():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(
        "edit this", Mode.CODE, "/tmp"
    )
    assert "-f" in argv, "-f already clears the workspace trust gate"


def test_cursor_prompt_is_positional_and_last():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(
        "do the thing", Mode.REVIEW, "/tmp"
    )
    assert argv[-1] == "do the thing"


def test_cursor_detects_quota_failure_despite_zero_exit():
    ex = CursorExecutor(binary_path="/usr/local/bin/cursor-agent")
    out = (
        "ActionRequiredError: Increase limits for faster responses You're out "
        "of usage. Switch to Auto or Composer 2.5, or ask your admin to "
        "increase your limit to continue."
    )
    assert ex.detect_failure(out) is not None


def test_cursor_does_not_flag_normal_output():
    ex = CursorExecutor(binary_path="/usr/local/bin/cursor-agent")
    assert ex.detect_failure("POLYPHONY_OK") is None
    assert ex.detect_failure("") is None


# The adapters below are opt-in and unverified against real binaries; their
# flags come from each CLI's official docs
# (docs/evidence/new-adapters-unverified.md).

import pytest

from polyphony.config import DEFAULT_POOL
from polyphony.executors import EXECUTORS
from polyphony.executors.codex import CodexExecutor
from polyphony.executors.gemini import GeminiExecutor
from polyphony.executors.opencode import OpencodeExecutor

BYPASS_FLAGS = {
    "--dangerously-bypass-approvals-and-sandbox", "--yolo", "-y",
    "--full-auto", "--auto", "--dangerously-skip-permissions",
    "danger-full-access", "--approval-mode=yolo",
}


def test_new_adapters_are_registered_but_opt_in():
    for name in ("codex", "gemini", "opencode"):
        assert name in EXECUTORS
        assert name not in DEFAULT_POOL


def test_codex_review_mode_is_read_only_sandbox():
    argv = CodexExecutor(binary_path="/bin/codex").build_argv("task", Mode.REVIEW, "/tmp/w")
    assert argv[:2] == ["/bin/codex", "exec"]
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert not BYPASS_FLAGS & set(argv)


def test_codex_code_mode_is_workspace_write_sandbox():
    argv = CodexExecutor(binary_path="/bin/codex").build_argv("task", Mode.CODE, "/tmp/w")
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert not BYPASS_FLAGS & set(argv)


def test_codex_reads_the_prompt_from_stdin_and_sets_workspace_and_model():
    ex = CodexExecutor(binary_path="/bin/codex")
    argv = ex.build_argv("--looks like a flag", Mode.CODE, "/tmp/w", model="gpt-x")
    assert argv[-1] == "-"
    assert "--looks like a flag" not in argv
    assert ex.stdin("--looks like a flag") == "--looks like a flag"
    assert argv[argv.index("--cd") + 1] == "/tmp/w"
    assert argv[argv.index("--model") + 1] == "gpt-x"


def test_gemini_review_mode_is_plan():
    argv = GeminiExecutor(binary_path="/bin/gemini").build_argv("task", Mode.REVIEW, "/tmp")
    assert argv[argv.index("--approval-mode") + 1] == "plan"
    assert not BYPASS_FLAGS & set(argv)


def test_gemini_code_mode_auto_approves_edits_only():
    argv = GeminiExecutor(binary_path="/bin/gemini").build_argv("task", Mode.CODE, "/tmp")
    assert argv[argv.index("--approval-mode") + 1] == "auto_edit"
    assert not BYPASS_FLAGS & set(argv)


def test_gemini_attaches_prompt_so_a_leading_dash_is_not_a_flag():
    tricky = "-rf everything; echo $HOME"
    argv = GeminiExecutor(binary_path="/bin/gemini").build_argv(
        tricky, Mode.CODE, "/tmp", model="gemini-x"
    )
    assert f"--prompt={tricky}" in argv
    assert tricky not in argv
    assert argv[argv.index("--model") + 1] == "gemini-x"


def test_opencode_review_mode_uses_the_plan_agent():
    argv = OpencodeExecutor(binary_path="/bin/opencode").build_argv(
        "task", Mode.REVIEW, "/tmp/w", model="anthropic/x"
    )
    assert argv[:2] == ["/bin/opencode", "run"]
    assert argv[argv.index("--agent") + 1] == "plan"
    assert argv[argv.index("--dir") + 1] == "/tmp/w"
    assert argv[argv.index("--model") + 1] == "anthropic/x"
    assert argv[-1] == "task"
    assert not BYPASS_FLAGS & set(argv)


def test_opencode_has_no_code_mode():
    """Its only edit-capable setup allows every tool, shell included, unprompted."""
    ex = OpencodeExecutor(binary_path="/bin/opencode")
    assert ex.modes == (Mode.REVIEW,)
    with pytest.raises(ValueError, match="code"):
        ex.build_argv("task", Mode.CODE, "/tmp")


def test_existing_adapters_support_both_modes():
    for name in ("agy", "cursor", "claude", "codex", "gemini"):
        assert set(EXECUTORS[name].modes) == {Mode.REVIEW, Mode.CODE}
