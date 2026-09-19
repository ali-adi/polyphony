# ai-orch Implementation Tasks

## Phase 1: Migration System
- [x] Create project structure (pyproject.toml, .gitignore, README)
- [x] Implement `migrate/scanner.py` — scans project dirs for AI config
- [x] Implement `migrate/classifier.py` — classifies items (global/project/task/executor)
- [x] Implement `migrate/translator.py` — translates items into orchestrator format
- [x] Wire up `ai-orch migrate` CLI command
- [x] Run migration against Medicoder copy and validate inventory

## Phase 2: Project Knowledge Layer
- [x] Create `projects/medicoder/project.yaml`
- [x] Create `projects/medicoder/context.md`
- [x] Create `projects/medicoder/safety.md`
- [x] Migrate global skills (catchup, pr, fix-until-green, verify-before-stop)
- [x] Create `config/global.yaml`

## Phase 3: Orchestrator Skeleton
- [x] Implement `orchestrator/main.py` — core decision loop
- [x] Implement `orchestrator/cli.py` — Click CLI entry point
- [x] Implement `orchestrator/context.py` — context builder
- [x] Implement `orchestrator/state.py` — task state management
- [x] Create Pydantic models for decisions, results, state

## Phase 4: Executor Adapters
- [x] Implement `executors/base.py` — Executor ABC + ExecutorResult model
- [x] Implement `executors/claude_executor.py` — `claude -p` wrapper
- [x] Implement `executors/agy_executor.py` — `agy` CLI wrapper
- [x] Implement `executors/cursor_executor.py` — `cursor agent -p` wrapper
- [x] Implement `executors/python_executor.py` — local Python/shell
- [x] Implement `executors/router.py` — executor routing + fallback

## Phase 5: Safety Layer
- [x] Implement `orchestrator/safety.py` — safety gate enforcement

## Phase 6: Logging & Reporting
- [x] Implement `orchestrator/logging.py` — structured logging
- [x] Implement `orchestrator/report.py` — final report generation

## Phase 7: First Task (Read-Only)
- [x] Test `ai-orch start medicoder --goal "Analyze the repository structure" --read-only`
- [x] Verify: Claude/AGY reasons, no files modified, report generated

## Phase 8: Iterative Task
- [x] Test `ai-orch start medicoder --goal "Run the test suite and summarize results"`
- [x] Verify: executor routing, test execution, review loop
- [x] Test fallback: disable one executor, verify other is used
