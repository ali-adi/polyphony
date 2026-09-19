# 🎼 Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Architecture: Local--First](https://img.shields.io/badge/architecture-local--first-emerald.svg)]()
[![Cost: Zero Extra API](https://img.shields.io/badge/billing-zero--api--cost-violet.svg)]()
[![Tests: 87 Passed](https://img.shields.io/badge/tests-87%20passed-brightgreen.svg)]()

> **Polyphony** is a local-first, CLI-driven multi-agent engineering orchestrator. It conducts **Claude Code**, **Antigravity (AGY)**, and **Cursor Agent** in concert—turning your existing CLI subscriptions into an autonomous, safe, and disciplined engineering team with **zero incremental API token costs**.

---

## 💡 Why Polyphony?

Modern developers frequently pay for multiple AI subscriptions (**Claude Pro/Max**, **Cursor Pro**, **Google Antigravity**), yet:

1. **API Costs Multiply**: Running multi-agent loops via standard cloud APIs incurs heavy per-token charges. Polyphony executes directly against your local CLI binaries (`claude -p`, `agy -p`, `cursor agent -p`), running comprehensive reasoning loops with zero added token billing.
2. **Specialized Division of Labor**: High-level architectural reasoning and granular file edits require different strengths. Polyphony separates concerns: **Claude Code** acts as the lead reasoning maestro, delegating implementation to fast, IDE-native executors like **AGY** and **Cursor**, or deterministic local Python.
3. **Safety & Guardrails**: Left unsupervised, autonomous agents can accidentally force-push git branches, wipe databases, or trigger expensive remote pipelines. Polyphony enforces strict pre-execution safety gates on every action.
4. **Knowledge Fragmentation**: AI context (skills, rules, conventions, hooks) is typically scattered across `.claude/`, `.cursor/`, and `.agents/`. Polyphony's universal migration engine unifies them into a single, persistent knowledge layer.
5. **Institutional Memory & Resilience**: Tasks persist state on disk, survive terminal closures and process crashes, automatically roll back on failure via Git checkpoints, and accumulate project learnings across runs.

---

## 🏛️ System Architecture

```text
                      ┌────────────────────────┐
                      │    User Engineering    │
                      │          Goal          │
                      └───────────┬────────────┘
                                  │
                                  ▼
             ┌──────────────────────────────────────────┐
             │       Polyphony Orchestrator Loop        │
             │   (State Machine, Memory, Context)       │
             └───────────┬──────────────────┬───────────┘
                         │                  │
        1. Context & Prompts                │ 4. Evaluation & Review
                         ▼                  ▼
             ┌──────────────────────────────────────────┐
             │            Lead Reasoner Agent           │
             │   Claude Code CLI  ──fallback──►   AGY   │
             │     [DELEGATE, VERIFY, USE_SKILL,        │
             │      ASK_HUMAN, COMPLETE, ABORT]         │
             └────────────────────┬─────────────────────┘
                                  │
                          2. Decides Action
                                  ▼
             ┌──────────────────────────────────────────┐
             │           Safety Policy Engine           │
             │   • Blocks dangerous commands & git push │
             │   • Protects immutable databases/paths   │
             │   • Lazy-agent zero-change guardrails    │
             │   • Git temporary workspace checkpoints  │
             └────────────────────┬─────────────────────┘
                                  │
                         3. Approved Execution
                                  ▼
             ┌──────────────────────────────────────────┐
             │             Executor Router              │
             │   ┌───────────────┬──────────────────┐   │
             │   │  Antigravity  │   Cursor Agent   │   │
             │   │     (AGY)     │      (CLI)       │   │
             │   └───────┬───────┴──────────┬───────┘   │
             │           └─────────┬────────┘           │
             │                     ▼                    │
             │         Deterministic Python / Shell     │
             └──────────────────────────────────────────┘
```

---

## ✨ Key Features

- **💰 Zero Incremental API Costs**: Operates exclusively via installed CLI subscriptions with no third-party API keys required.
- **🧠 Hierarchical Reasoning & Execution**: High-level reasoning is handled by Claude Code (or AGY upon quota exhaustion); concrete implementations are routed to the best-suited executor.
- **🛡️ Defensive Safety Gates**:
  - **Database Immutability**: Forbids modifications to production data snapshots (e.g. SQLite databases, fixtures).
  - **Git Discipline**: Blocks destructive operations (`git push`, `git merge`, `git reset --hard`, wildcard staging `git add -A`).
  - **Attribution Blocking**: Eliminates unsolicited `Co-authored-by` AI commit trailers.
  - **Lazy Agent Guardrail**: Prevents agents from claiming completion on code-modifying goals when zero files were modified, unless explicitly justified.
  - **Automated Checkpoints & Rollback**: Creates a `polyphony-temp-checkpoint` Git stash/commit before runs; auto-rolls back on execution failure. Supports nested monorepo and worktree Git roots.
- **🎯 Granular Model & Thinking Levels**: Configure exact models and reasoning effort/thinking budgets per agent (Claude, AGY, Cursor) at global, project, or task CLI level.
- **🤖 Subagent & Dynamic Workflow Policies**: Specify models, thinking levels, and specialized role definitions (reviewer, tester, researcher) passed natively to spawned subagents via Claude `--agents` and AGY effort directives.
- **🔄 Bidirectional Fallbacks & Quota Resilience**: If Claude reaches weekly/hourly usage quotas, Polyphony automatically promotes AGY as lead reasoner with zero workflow interruption. If an executor fails, Polyphony falls back to the secondary executor.
- **🚨 Circuit Breakers & Failure Classification**: Automatically categorizes errors (`SYNTAX_ERROR`, `DEPENDENCY_ERROR`, `ASSERTION_FAILURE`, `TIMEOUT`, `PERMISSION_ERROR`). Injects root-cause diagnostic prompts after 2 consecutive errors, and halts runaway loops after 3 consecutive failures.
- **🙋 Human-in-the-Loop & Escalation**:
  - `action: "ASK_HUMAN"` prompts the developer via stdin in interactive mode, or cleanly sets status to `NEEDS_HUMAN` in non-interactive/daemon mode.
  - `polyphony task retry <project> <task_id> --feedback "..."` re-arms tasks, extends the iteration budget, and injects user feedback directly into the next prompt.
- **⚡ Token Optimization & Prompt Caching**:
  - Pre-computes static system prompts for provider prompt caching.
  - Tracks executor session IDs and injects project delegation headers on the first turn only, saving 150–400 tokens per subsequent turn.
  - Normalizes passing test results to 1-line metrics, eliminating hundreds of lines of pytest noise.
- **🧬 Universal Migration (`polyphony migrate`)**: Ingests existing `.claude/`, `.cursor/`, and `.agents/` configurations, automatically classifying items into global skills, project domain knowledge, executable hooks, and rules.
- **📚 Durable Institutional Memory**: Injects domain conventions, architecture notes, decisions, and known issues into the agent's context. Automatically appends task decision summaries to `decisions.md` on completion.
- **📝 Structured Reporting & Auditing**: Every iteration generates granular JSON event streams (`.log.jsonl`), state files (`.json`), and markdown task summaries (`_report.md`) documenting decisions, diffs, test results, and command traces.

---

## 🚀 Quick Start

### 1. Prerequisites

Ensure you have Python 3.11+ and at least one of the supported CLI agents installed and authenticated on your system:
- **Claude Code CLI**: `claude` (Anthropic Claude Pro/Max)
- **Antigravity CLI**: `agy` (Google Antigravity)
- **Cursor Agent**: `cursor agent` (Cursor Pro)

### 2. Installation

Clone the repository and install in editable mode:

```bash
git clone https://github.com/ali-adi/polyphony.git
cd polyphony

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify installation:
```bash
polyphony --version
```

---

## 💻 CLI Usage Guide

### Project Management

```bash
# Ingest and translate AI configurations from an existing codebase
polyphony migrate /path/to/my-project --name my-project

# Register an existing repository manually
polyphony project add my-project --path /path/to/my-project

# List all registered projects
polyphony project list

# Inspect project configuration, knowledge files, and skills
polyphony project inspect my-project

# Display merged global and default configuration
polyphony config show
```

### Running Tasks

```bash
# Standard autonomous task execution
polyphony start my-project --goal "Implement rate limiting middleware and verify with tests"

# Read-only audit mode (strictly prohibits file modifications or destructive actions)
polyphony start my-project --goal "Analyze codebase architecture and document bottlenecks" --read-only

# Dry-run mode (simulates orchestrator decision loop without invoking subagents)
polyphony start my-project --goal "Refactor database models" --dry-run

# Specify iteration budget and force lead reasoner
polyphony start my-project --goal "Fix flaky integration tests" --max-iterations 8 --lead agy

# Dial in exact models & thinking levels
polyphony start my-project \
  --goal "Architect event-driven telemetry service" \
  --lead-model "claude-3-7-sonnet" \
  --lead-thinking "high" \
  --executor-model "gemini-3.1-pro-high" \
  --executor-thinking "high"
```

### Task Lifecycle & Inspection

```bash
# List all tasks for a project
polyphony task list my-project

# Display live/completed task status, iteration history, and token estimates
polyphony task status my-project <task_id>

# View git diff of changes produced by a task
polyphony task diff my-project <task_id>

# Resume a halted or iteration-exhausted task (automatically adds +5 iterations)
polyphony resume my-project <task_id>

# Retry a failed or halted task with human guidance
polyphony task retry my-project <task_id> --feedback "Do not use in-memory cache; use Redis connection pool"

# Abort a running/blocked task and roll back repository to pre-task checkpoint
polyphony task abort my-project <task_id>
```

---

## ⚙️ Configuration & Models Cascade

Polyphony uses a 3-tier cascading configuration hierarchy:

```text
Global Config (config/global.yaml)
       ↓
Project Config (projects/<project>/project.yaml)
       ↓
Task / CLI Flags (--lead-model, --executor-thinking, etc.)
```

### Example `projects/<project>/project.yaml`

```yaml
name: my-service
path: /Users/developer/code/my-service
lead: claude
executors:
  primary: cursor
  secondary: agy
testing:
  command: pytest -v
models:
  lead:
    model: claude-3-7-sonnet
    thinking_level: high
  executors:
    cursor:
      model: claude-3-5-sonnet
    agy:
      model: gemini-3.1-pro-high
      thinking_level: medium
  subagents:
    policy: dynamic
    default_model: claude-3-5-haiku
    roles:
      reviewer:
        model: claude-3-7-sonnet
        thinking_level: high
      tester:
        model: claude-3-5-haiku
safety:
  protected_paths:
    - config/production.yaml
    - data/*.sqlite
  blocked_commands:
    - "rm -rf /"
    - "terraform destroy"
```

---

## 📁 Repository Layout

```text
polyphony/
├── config/
│   └── global.yaml             # Global orchestrator defaults, limits & command blocks
├── orchestrator/
│   ├── cli.py                  # Click CLI interface (polyphony / ai-orch)
│   ├── context.py              # Knowledge compiler, prompt caching & token compressor
│   ├── main.py                 # Core orchestration decision loop & state machine
│   ├── safety.py               # Pre-execution safety gates & lazy-agent guardrail
│   ├── state.py                # Task state machine, iteration tracking & persistence
│   ├── logging.py              # Structured console output & JSON event logging
│   └── report.py               # Markdown task report generation with diffs
├── executors/
│   ├── base.py                 # Base executor interface & execution models
│   ├── claude_executor.py      # Claude Code CLI adapter
│   ├── agy_executor.py         # Google Antigravity CLI adapter
│   ├── cursor_executor.py      # Cursor Agent CLI adapter
│   ├── python_executor.py      # Deterministic local Python/Shell runner with venv detection
│   └── router.py               # Bidirectional fallback router & worktree Git root discovery
├── migrate/
│   ├── scanner.py              # Recursive scanner for .claude, .cursor, .agents
│   ├── classifier.py           # Scope & safety classification engine
│   └── translator.py           # Knowledge, hook, and rule translator
├── projects/                   # Registered project knowledge bases
│   └── <project_name>/
│       ├── project.yaml        # Project metadata, executor preferences & safety rules
│       ├── context.md          # Architecture overview & repo structure
│       ├── conventions.md      # Coding style, commit syntax & prompt grammar
│       ├── decisions.md        # Architectural Decision Records (auto-appended on task complete)
│       ├── known_issues.md     # Failure memory & known gotchas
│       ├── hooks/              # Executable validation hooks
│       ├── rules/              # Behavioral policy documents
│       └── skills/             # Project-specific engineering skills
├── skills/                     # Global reusable skills (benchmarking, optimization, research)
├── tasks/                      # Persisted task state (.json), event logs (.jsonl) & reports (.md)
└── tests/                      # Full test suite (87 unit & integration tests)
```

---

## 🧪 Testing & Verification

Polyphony includes an automated test suite verifying executor routing, bidirectional fallback chains, safety gate enforcement, prompt caching, and task state machines:

```bash
# Run test suite
pytest -v
```

```text
============================== 87 passed in 3.29s ==============================
```

---

## 📄 License

Polyphony is licensed under the [MIT License](LICENSE).
