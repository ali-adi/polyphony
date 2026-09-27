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
