# Polyphony Baseline v0.1.0-core

> Baseline specification for Polyphony v0.1.0-core known-good foundation.

## 1. Test Count & Environment
- **Passing tests:** 87 tests passing under Python 3.14 / pytest 9.1.1.
- **Coverage:** CLI, Context, Executors (Claude, AGY, Cursor, Python), Fallback & Circuit Breakers, Migration, Models Configuration, Orchestrator Loop, Safety policies & Advanced safety.

## 2. Supported Executors
- **Claude Code (`ClaudeExecutor`):** Primary lead reasoner. Subprocess CLI execution with stdin instruction piping, session continuation (`--resume`), quota detection, and cost parsing.
- **Antigravity (`AGYExecutor`):** Secondary / fallback reasoner. Headless execution, prompt caching, session persistence.
- **Cursor Agent (`CursorExecutor`):** Fast code-editing executor. Class-level TTL caching, session tracking, diff analysis.
- **Python / Shell (`PythonExecutor`):** Deterministic tool and script executor. Pre-execution safety validation, bash command execution, git diff / change detection.

## 3. CLI Behavior & Surface
- `polyphony start`: Initiates orchestration session with goal, task-id, executor choices, thinking level, and iteration limits.
- `polyphony resume`: Resumes paused or interrupted task from durable state.
- `polyphony retry`: Resets status from terminal/failed state and resumes.
- `polyphony abort`: Transitions active task to ABORTED with status record.
- `polyphony status`: Summarizes active and completed task states.
- `polyphony list`: Lists known tasks and their execution states.
- `polyphony register`: Registers project workspace with Polyphony configuration.
- `polyphony inspect`: Displays resolved configuration cascade (global → project → task).
- `polyphony migrate`: Scans and translates legacy configurations from `.claude/`, `.cursor/`, and `.agents/`.

## 4. Configuration Schema
- **Cascade order:** Global (`config/global.yaml`) → Project (`projects/<name>/project.yaml`) → Task-level parameters.
- **Sections:**
  - `executors`: Lead and subagent providers, model mappings, fallback order.
  - `models`: Per-provider models, context limits, thinking budget/levels.
  - `safety`: Blocked command patterns, protected file paths, max file modifications, require approval flags.
  - `projects`: Registered workspace roots, hooks, rules, skills directories.

## 5. Task State Schema
- Stored as JSON (`tasks/<project>/<task_id>/state.json`):
  - `task_id`: Unique string identifier.
  - `goal`: User objective string.
  - `status`: Lifecycle status (`PENDING`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`, `ABORTED`, `BLOCKED`).
  - `current_iteration`: Integer index.
  - `max_iterations`: Configured iteration limit.
  - `history`: List of execution records (iteration, executor, prompt, result, files changed, duration, errors).
  - `session_ids`: Per-executor session identifiers for durable continuation.
  - `cost_estimate`: Aggregated token count and monetary cost tracking.

## 6. Event Schema
- Stored as structured JSON Lines (`tasks/<project>/<task_id>/events.jsonl`):
  - `timestamp`: ISO-8601 UTC timestamp.
  - `event_type`: Event category (e.g. `TASK_STARTED`, `EXECUTOR_INVOKED`, `CIRCUIT_BREAKER_TRIGGERED`, `SAFETY_VIOLATION`, `TASK_COMPLETED`).
  - `task_id`: Task identifier.
  - `payload`: Structured dictionary with event-specific telemetry and context.

## 7. Migration Behavior
- Discovers `.claude/config.json`, `.cursorrules`, `agents/` directories.
- Classifies items into rules, skills, hooks, and configurations.
- Translates them idempotently into Polyphony-native project configuration and conventions.

## 8. Safety Behavior
- AST and token-based command validation.
- Path traversal and protected path guards (`.git`, config files, system roots).
- Zero-change guardrails preventing false completion without verifiable edits.
- Git checkpoint creation before execution with rollback capabilities.

## 9. Known Limitations
- Rollback in v0.1.0-core reverts via git reset/stash which does not isolate user-authored uncommitted changes from Polyphony changes.
- Executor protocol varies across classes without a unified abstract interface.
- Routing is based on fixed primary/fallback lists rather than fine-grained task capabilities.
- Lack of formal benchmark evaluation suite.
- Lack of deterministic short-circuiting for purely rule-based steps.
