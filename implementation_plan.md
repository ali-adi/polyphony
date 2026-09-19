# Polyphony Exhaustive Improvement Plan

This plan encompasses all bug fixes, architectural enhancements, token efficiency optimizations, and missing features identified in the exhaustive codebase review. 

The proposed changes are ranked by priority (P0 to P4) to ensure critical safety and data integrity issues are addressed first before moving on to UX and token optimizations.


## Proposed Changes

### 🔴 P0: Critical Security & Safety Fixes

#### [MODIFY] [safety.py](file:///Users/ali/root/ai-orch/orchestrator/safety.py)
- **Fix `_validate_rm_tokens` false positives**: Change `if "r" in tok` to check for exact flag matches (e.g., `tok in ("-r", "-R", "-rf", "-fr")` or `tok.startswith("-") and "r" in tok`) instead of simple substring checks that trigger on filenames.
- **Context-aware validation**: Safety engine currently treats prose (DELEGATE instructions) as shell commands. Update `SafetyEngine.validate_command()` to accept an `is_shell` boolean. Only run shell-specific regex tokenization on actual `PythonExecutor` commands, not natural language AI prompts.

#### [MODIFY] [python_executor.py](file:///Users/ali/root/ai-orch/executors/python_executor.py)
- **Mitigate `shell=True` Injection Risk**: Introduce an `--interactive` mode that pauses and requests user approval for execution. If running autonomously, log a prominent warning for shell executions.

---

### 🔴 P1: Data Integrity & Critical Bugs

#### [MODIFY] [router.py](file:///Users/ali/root/ai-orch/executors/router.py)
- **Fix `rollback_workspace`**: Replace `git stash push` with a temporary commit approach to guarantee zero data loss and clean git history. Before execution: `git commit -a -m "polyphony-temp"`. If execution fails: `git reset --hard HEAD~1` (reverting both executor and pre-existing changes). If execution succeeds: `git reset --soft HEAD~1` (leaving all changes in the working directory and removing the commit from history).

#### [MODIFY] [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py)
- **Fix Latent NameError**: On line 293, `test_res` is referenced when `tests_passed=False`, but it is only defined in the non-dry-run `else` branch. Initialize `test_res = None` prior to the dry-run check.
- **Implement Cost Tracking**: Introduce a budget enforcer. Track estimated tokens per iteration, calculate USD cost based on `models_config`, and abort if `max_cost_usd` is exceeded.

#### [MODIFY] [logging.py](file:///Users/ali/root/ai-orch/orchestrator/logging.py)
- **Fix Missing Logs**: `_write_log("WARN")` does not match `"WARNING"`, causing all safety block logs to be silently dropped. Update string matching to use `logging.INFO`, `logging.WARNING`, etc.

#### [MODIFY] [python_executor.py](file:///Users/ali/root/ai-orch/executors/python_executor.py)
- **Fix File Change Detection**: `git status --porcelain` captures all dirty files, not just those changed during execution. Change `_get_changed_files_via_git` to use file checksums or `git diff --name-only HEAD` before and after execution to isolate only the delta.

---

### 🟡 P2: Architectural Resilience & Waste Reduction

#### [MODIFY] [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py)
- **Persist Reasoner Sessions**: When resuming a task, `lead_session_id` starts as `None`. Persist this in `TaskState` and restore it on resume to prevent breaking session continuity.
- **Build System Prompt Once**: `build_system_prompt()` is currently called inside the `while` loop on every iteration. Move it *outside* the loop to save compute and enable true prompt caching.
- **Graceful Interrupts**: Add a signal handler (SIGINT) to catch `Ctrl+C`, save a checkpoint, and transition `TaskState` to `ABORTED` rather than leaving it as a zombie `RUNNING` task.
- **Final Synthesis Fix**: The final synthesis pass doesn't record an `IterationRecord` and fails silently if quota is reached. Record its execution and allow the reasoner to request an iteration extension rather than forcing `COMPLETE`.

#### [MODIFY] [context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py)
- **Lazy Context Loading**: Truncate `context.md` and `conventions.md` at load-time (or cache the truncated result) rather than reading 10KB+ into memory on every iteration.
- **Smart Delegation Header**: Only prepend the delegation context header if delegating to an AI executor. Skip it for `python` which only runs shell commands and ignores conventions.
- **Active Skill Injection**: The orchestrator lists skills but never exposes their contents. Implement a mechanism (or `USE_SKILL` action) that injects a skill's `SKILL.md` content into the prompt when requested by the lead reasoner.

#### [MODIFY] [claude_executor.py](file:///Users/ali/root/ai-orch/executors/claude_executor.py)
- **Fix Quota Check**: `claude --version` only checks binary health, not quota. Rename `check_quota_status` to `check_binary_health()`.
- **Robust Session Extraction**: The regex for extracting `session_id` is brittle and overwrites JSON parsing. Rely primarily on JSON output parsing, and tighten the regex as a strict fallback.

#### [MODIFY] [cursor_executor.py](file:///Users/ali/root/ai-orch/executors/cursor_executor.py)
- **TTL Cache for Availability**: `is_available()` caches `False` at the class level permanently. Add a TTL (e.g., 5 minutes) so the orchestrator notices if Cursor becomes available mid-task.

---

### 🟢 P3: Token Optimization & Cleanup

#### [MODIFY] [claude_executor.py](file:///Users/ali/root/ai-orch/executors/claude_executor.py)
- **JSON Output Mode**: Use `--output-format json` natively for the lead reasoner call to guarantee parseable output and avoid markdown wrappers.

#### [MODIFY] [context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py)
- **Compress System Prompt**: Remove redundant headers (`Active Rules: None`), condense the JSON schema, and trim empty lines to save static tokens.
- **Remove History Noise**: Omit `Tests Passed: None` and `Files Changed: []` from the iteration history strings when they are empty.
- **Aggressive Output Truncation**: Currently, 800 chars of output are kept per iteration, eating up to 8000 chars over 10 iterations. Compress repetitive test outputs or only retain the last `N` lines of execution output for historical iterations.

#### [MODIFY] [report.py](file:///Users/ali/root/ai-orch/orchestrator/report.py)
- **Accurate Token Math**: Replace `chars // 4` with an accurate calculation that includes the system prompt, accumulated conversation context, and thinking tokens.

#### [MODIFY] [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py)
- **Lazy Prompt Building for COMPLETE**: If the reasoner emits `COMPLETE` or `ABORT`, don't build the next user prompt unnecessarily.
- **Thinking Level Downgrades**: Ensure the orchestrator respects when a reasoner emits `"thinking_level": "low"` for mechanical `VERIFY` steps, rather than forcing the config's default `high` everywhere.

---

### 🔵 P4: Design Improvements & Missing Features

#### [MODIFY] [safety.py](file:///Users/ali/root/ai-orch/orchestrator/safety.py)
- **Remove Medicoder Defaults**: Strip `database/` and `configs/full.yml` from the base `SafetyConfig` class. These should only be defined in `project.yaml`.

#### [MODIFY] [global.yaml](file:///Users/ali/root/ai-orch/config/global.yaml)
- **Fix Model IDs**: Correct invalid Gemini model IDs (`gemini-3.1-pro-high` -> `gemini-2.0-flash` or similar) to prevent instant failures.

#### Setup & Build
- **Clean Egg Info**: Remove the stale `ai_orch.egg-info` directory.

## Verification Plan

### Automated Tests
- Run `pytest -v` to ensure all existing router, state, and safety tests pass.
- Add tests for `safety.py` to ensure `rm --recursive file.txt` is blocked but `rm --preserve-root file.txt` is allowed.
- Add tests for `context.py` to ensure empty fields are elided from the system and history prompts.

### Manual Verification
- Trigger a `dry_run=True` task that "fails" verification to ensure the `NameError` is resolved.
- Press `Ctrl+C` during an active task to verify the SIGINT handler correctly saves state and aborts.
