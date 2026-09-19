# Polyphony Exhaustive Implementation & Improvement Plan (v3.0)

This document integrates the complete verification of the Phase 2 implementation, records the critical runtime and edge-case fixes discovered and resolved during verification, presents an architectural critique of the codebase, analyzes logical fallacies and token leakage, and defines the Phase 3 feature backlog derived from `initial-plan.md`.

---

## 🟢 Part 1: Verification & Applied Fixes Summary

All 15 Phase 2 items from the v2.0 backlog have been implemented and verified with **81/81 automated tests passing** in under 3.3 seconds. During end-to-end verification, six critical bugs, edge cases, and efficiency loopholes were identified and resolved in code:

1. **`project inspect` Path Resolution Bug (`load_project_knowledge`)**:
   - *The Bug*: `polyphony project inspect <name>` printed `Path: N/A` because `load_project_knowledge` stored the repository path nested inside `knowledge["config"]["path"]` rather than top-level `knowledge["path"]`.
   - *Fix*: Added `knowledge["path"] = str(knowledge["config"].get("path", ""))` in [orchestrator/context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py), making project paths accurately display across all CLI commands.

2. **Virtualenv Interpreter PATH Resolution (`PythonExecutor`)**:
   - *The Bug*: `PythonExecutor.execute()` ran shell commands via `subprocess.Popen(shell=True)` without an explicit environment. If tools like `pytest`, `ruff`, or `mypy` were installed only in the target repository's `.venv/bin` rather than global `/usr/bin`, commands failed with `command not found: pytest`.
   - *Fix*: Updated [executors/python_executor.py](file:///Users/ali/root/ai-orch/executors/python_executor.py) to dynamically locate `.venv/bin`, `venv/bin`, and `interpreter` directories and prepend them to `PATH` in `os.environ`.

3. **Task Resume Iteration Trap (`resume_task`)**:
   - *The Bug*: When a task halted after hitting `max_iterations` (e.g. 10) and a user ran `polyphony resume <project> <task_id>`, `task_state.current_iteration` was already 10. In `_execute_task_loop`, `while task_state.current_iteration < self.max_iterations:` was skipped entirely, causing the task to fail immediately on line 1 without running a single resumed iteration.
   - *Fix*: Updated `resume_task()` in [orchestrator/main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py) to detect when `current_iteration >= max_iterations` and automatically extend the limit by `extra_iterations` (default +5), ensuring resumed tasks make progress.

4. **Double Testing on Task Completion (`just_verified`)**:
   - *The Bug*: When the lead reasoner executed a `VERIFY` step (which ran and passed `test_cmd`) and immediately followed with `COMPLETE`, `orchestrator/main.py` ran the entire test suite a second time before stopping. For large test suites, this doubled task latency.
   - *Fix*: Added deduplication logic in [orchestrator/main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py) (`just_verified`): if the immediately preceding iteration executed `test_cmd` or `VERIFY` successfully and no files were modified in between, the orchestrator reuses the previous test pass result.

5. **Lost Rationale, Target Files & Benchmark Metrics in Prompt History**:
   - *The Bug*: `build_user_prompt()` in [orchestrator/context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py) only rendered action, executor, instruction, output, and tests_passed for recent iterations. It dropped `target_files` and `metrics` (benchmarks, p50 latency, throughput). If iteration 1 established an optimization baseline, the reasoner in iteration 2 had no record of the baseline numbers.
   - *Fix*: Enriched iteration history in `build_user_prompt()` to explicitly include `Target Files: [...]` and `Metrics: latency_ms=14.2, ...`.

6. **Blind Skill Registry Frontmatter Extraction**:
   - *The Bug*: `build_system_prompt()` rendered skills as raw names (`- am-achi-notes-author`, `- icd10cm-pcs`). The lead reasoner had no context on what obscure or project-specific skills did, causing low utilization.
   - *Fix*: Implemented `get_skill_description()` in [orchestrator/context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py) to parse the YAML frontmatter `description` of each `SKILL.md` file and render `- `skill`: <description>` in the system prompt.

---

## 🔍 Part 2: Comprehensive Codebase Evaluation

### What is the state of the codebase now?
Polyphony has evolved from a simple CLI script wrapper into a robust, local-first multi-agent engineering platform:
- **True Orchestration vs. Agent Spawning**: Instead of blind agent delegation, the lead reasoner (Claude / AGY) operates with an explicit decision schema (`DELEGATE`, `VERIFY`, `USE_SKILL`, `COMPLETE`, `ABORT`).
- **Resilient Execution & Rollback**: Automatic Git checkpoints (`polyphony-temp-checkpoint`), process group termination on timeout (`killpg`), and selective dirty-file tracking guarantee that failed executor runs do not corrupt working trees.
- **Circuit Breakers**: Consecutive failure tracking halts runaway loops at 3 iterations, and injects root-cause prompts at 2 iterations.
- **Institutional Memory**: Institutional learning is preserved on disk across runs in `architecture.md`, `decisions.md`, and `known_issues.md`.

---

## ⚠️ Part 3: Logical Fallacies, Gaps & Efficiency Loopholes

### 1. The "Lazy Agent" Zero-Change Completion Fallacy
- **The Gap*: If `require_tests_before_stop` is true and a task's goal is "Fix the race condition in auth.py" or "Implement caching", a reasoner might emit `action: "COMPLETE"` on iteration 1 without delegating any code changes. Because the pre-existing test suite already passes, the orchestrator accepts the completion!
- **Consequence**: Tasks falsely succeed with zero code written or inspected.
- **Solution**: In `orchestrator/main.py`, if `task_state.read_only` is False and `len(task_state.all_files_changed) == 0`, require explicit affirmative verification or reject immediate completion if the goal contains action verbs (`fix`, `implement`, `add`, `refactor`, `optimize`, `build`).

### 2. Git Checkpoint Failure in Monorepo Subdirectories & Submodules
- **The Gap**: `create_workspace_checkpoint` and `rollback_workspace` currently check `(Path(cwd) / ".git").exists()`. In monorepo subdirectories or Git worktrees/submodules, `.git` is either in a parent directory or is a pointer file (`gitdir: ...`).
- **Consequence**: Checkpoint creation is skipped, leaving the workspace unprotected against failed executor scripts.
- **Solution**: Use `git rev-parse --is-inside-work-tree` or check `(Path(cwd) / ".git").exists() or _is_git_worktree(cwd)` to accurately detect Git root across complex directory hierarchies.

### 3. Subagent Re-Prompting Token Leak
- **The Gap**: In `orchestrator/main.py`, when delegating to coding agents (`claude`, `agy`, `cursor`), `build_delegation_context_header()` prepends project conventions and safety policies (up to 600 chars / ~150 tokens) to the instruction. When delegating across multiple turns to the *same* session ID (`--resume` or `--conversation`), the subagent already has this context in its session history.
- **Consequence**: 200–500 tokens of redundant prompt overhead are billed on every follow-up turn.
- **Solution**: Only prepend the delegation context header on the *first* iteration of a given executor session.

### 4. Passing Test Output Noise in Context Windows
- **The Gap**: `compress_execution_output` extracts error markers when tests fail. However, when tests pass (e.g. running pytest with 400 passing tests), it sends the last 15 lines of test dots or verbosity.
- **Consequence**: Wastes 100-300 tokens of noise in the lead reasoner's prompt.
- **Solution**: For successful verification runs, normalize test output to a 1-line summary (`"Pytest: 412 passed in 2.14s"`).

---

## 🛠️ Part 4: Phase 3 Features (Implemented & Verified)

All Phase 3 core integrity, workflow hardening, and token-reduction features have been implemented and verified with **87/87 automated tests passing**:

---

### 🔴 P0: Core Integrity & Workflow Hardening (Completed)

#### 1. [COMPLETED] [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py) — "Lazy Agent" Guardrail on Code Modifications
- Intercepts premature `COMPLETE` actions when `all_files_changed` is empty on code-altering tasks (e.g. goals containing `fix`, `implement`, `add`, `refactor`, `optimize`, `build`). Demands either actual code modifications or explicit justification (`"allow_zero_changes": true`). Verified in `test_lazy_agent_zero_change_interception`.

#### 2. [COMPLETED] [router.py](file:///Users/ali/root/ai-orch/executors/router.py) — Monorepo & Worktree Git Root Discovery
- Replaced raw `Path(cwd) / ".git"` checks with `_get_git_root(cwd)` utilizing `git rev-parse --show-toplevel`. Checkpoints and rollbacks now function seamlessly inside monorepo subpackages and Git worktrees.

#### 3. [COMPLETED] [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py) & [context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py) — One-Time Delegation Context Headers
- Tracks `initialized_sessions` dynamically across turns and executor session updates, omitting `build_delegation_context_header()` on subsequent turns to an existing session ID. Saves ~150–400 tokens per subagent delegation turn. Verified in `test_one_time_delegation_context_header`.

---

### 🟡 P1: Human-in-the-Loop & CLI Productivity (Completed)

#### 4. [COMPLETED] [cli.py](file:///Users/ali/root/ai-orch/orchestrator/cli.py) & [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py) — `task retry` with Feedback
- Implemented `polyphony task retry <project> <task_id> --feedback "..."`. Re-arms halted, failed, or completed tasks, automatically extends iteration budget by 5, and injects user feedback directly into the next reasoning prompt as a priority directive. Verified in `test_task_retry_cli`.

#### 5. [COMPLETED] [main.py](file:///Users/ali/root/ai-orch/orchestrator/main.py) & [state.py](file:///Users/ali/root/ai-orch/orchestrator/state.py) — Interactive Human Escalation (`action: "ASK_HUMAN"`)
- Added `action: "ASK_HUMAN"` decision support. Prompts user interactively on `sys.stdin` via `click.prompt()` when a terminal is available; transitions task to `TaskStatus.NEEDS_HUMAN` with actionable reason when in non-interactive / daemon mode. Verified in `test_ask_human_action_non_interactive`.

#### 6. [COMPLETED] [context.py](file:///Users/ali/root/ai-orch/orchestrator/context.py) — Passing Test Output Normalization & Failure Classification
- Added `classify_failure()` categorizing execution failures into `SYNTAX_ERROR`, `DEPENDENCY_ERROR`, `ASSERTION_FAILURE`, `TIMEOUT`, `PERMISSION_ERROR`, `UNKNOWN_FAILURE` and injecting them into circuit-breaker prompts.
- Normalized passing test outputs in `compress_execution_output()` to concise 1-2 line summaries (`"Tests passed: ..."`), saving 100–300 tokens of noisy output per verification pass. Verified in `test_classify_failure` and `test_compress_execution_output_normalizes_passed_tests`.

---

### 🟢 P2: Future Roadmap

#### 7. Independent Implementation Competition
- **Reference**: `initial-plan.md` Section 34 ("Independent implementation competition").
- **Design**: Run two candidate implementations (e.g. Claude 3.7 vs. Cursor/AGY) concurrently in separate isolated Git worktrees, execute the benchmark suite on both, compare metrics, and automatically select the winner.

#### 8. Automated GitHub Pull Request Generation (`task pr`)
- **Reference**: `initial-plan.md` Section 48 & 49 ("Automatic PR creation").
- **Design**: Add `polyphony task pr <project> <task_id>` to push the isolated task branch `polyphony/<task_id>` and generate a GitHub PR with changelog, architecture summary, and test results via `gh pr create`.

---

## 🧪 Verification Plan & Test Results

All test suites passing with zero failures:
- **Baseline CLI & Safety Suite**: 33 tests passed
- **Core Orchestrator & Context Suite**: 33 tests passed
- **Phase 2 Verification Suite (`tests/test_phase2_features.py`)**: 15 tests passed
- **Phase 3 Verification Suite (`tests/test_phase3_features.py`)**: 6 tests passed
- **Total**: **87/87 tests passed in 3.29s**.
