# 🎼 Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Architecture: Local--First](https://img.shields.io/badge/architecture-local--first-emerald.svg)]()
[![Cost: Zero Extra API](https://img.shields.io/badge/billing-zero--api--cost-violet.svg)]()

> **Polyphony** is a local-first, CLI-driven multi-agent engineering orchestrator. It conducts **Claude Code**, **Antigravity (AGY)**, and **Cursor Agent** in concert—turning your existing CLI subscriptions into an autonomous, safe, and disciplined engineering team with **zero incremental API token costs**.

---

## 💡 Why Polyphony?

Modern developers frequently pay for multiple AI subscriptions (**Claude Pro/Max**, **Cursor Pro**, **Google Antigravity**), yet:

1. **API Costs Multiply**: Running multi-agent loops via standard cloud APIs incurs heavy per-token charges. Polyphony executes directly against your local CLI binaries (`claude -p`, `agy -p`, `cursor agent -p`), running comprehensive reasoning loops with zero added token billing.
2. **Specialized Division of Labor**: High-level architectural reasoning and granular file edits require different strengths. Polyphony separates concerns: **Claude Code** acts as the lead reasoning maestro, delegating implementation to fast, IDE-native executors like **AGY** and **Cursor**, or deterministic local Python.
3. **Safety & Guardrails**: Left unsupervised, autonomous agents can accidentally force-push git branches, wipe databases, or trigger expensive remote pipelines. Polyphony enforces strict pre-execution safety gates on every action.
4. **Knowledge Fragmentation**: AI context (skills, rules, conventions, hooks) is typically scattered across `.claude/`, `.cursor/`, and `.agents/`. Polyphony's universal migration engine unifies them into a single, persistent knowledge layer.

---

## 🏛️ System Architecture

```
                      ┌────────────────────────┐
                      │    User Engineering    │
                      │          Goal          │
                      └───────────┬────────────┘
                                  │
                                  ▼
             ┌──────────────────────────────────────────┐
             │       Polyphony Orchestrator Loop        │
             │   (State Management, Context Builder)    │
             └───────────┬──────────────────┬───────────┘
                         │                  │
        1. Context & Prompts                │ 4. Evaluation & Review
                         ▼                  ▼
             ┌──────────────────────────────────────────┐
             │            Lead Reasoner Agent           │
             │   Claude Code CLI  ──fallback──►   AGY   │
             └────────────────────┬─────────────────────┘
                                  │
                          2. Decides Action
                                  ▼
             ┌──────────────────────────────────────────┐
             │           Safety Policy Engine           │
             │   • Blocks dangerous git operations      │
             │   • Protects immutable databases         │
             │   • Enforces test verification           │
             │   • Prevents unapproved cloud runs       │
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
  - **Git Discipline**: Blocks destructive operations (`git push`, `git merge`, wildcard staging `git add -A`).
  - **Attribution Blocking**: Eliminates unsolicited `Co-authored-by` AI commit trailers.
  - **Cost Controls**: Flags and blocks expensive pipeline runs unless explicitly approved.
- **🔄 Bidirectional Fallbacks & Quota Resilience**: If Claude reaches weekly/hourly usage quotas, Polyphony automatically promotes AGY as lead reasoner with zero workflow interruption. If an executor fails, Polyphony falls back to the secondary executor.
- **🧬 Universal Migration (`polyphony migrate`)**: Ingests existing `.claude/`, `.cursor/`, and `.agents/` configurations, automatically classifying items into global skills, project domain knowledge, executable hooks, and rules.
- **📚 Persistent Project Knowledge**: Injects domain conventions, schema references, and specific prompt notations (e.g. clinical coding grammar) directly into the agent's context window on every iteration.
- **📝 Structured Reporting & Auditing**: Every iteration generates granular JSON state histories and a final markdown task summary documenting decisions, diffs, test results, and command traces.

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

## 💻 CLI Usage

### Ingest Existing Repositories
Extract and translate all AI configurations from an existing codebase:
```bash
polyphony migrate /path/to/my-project --name my-project
```

### Inspect Registered Projects
```bash
polyphony project list
```

### Run an Autonomous Task
Launch an autonomous, iterative multi-agent run:
```bash
# Standard task run
polyphony start my-project --goal "Implement rate limiting middleware and verify with tests"

# Read-only audit mode (prohibits any write or modification)
polyphony start my-project --goal "Analyze codebase architecture and document security bottlenecks" --read-only

# Specify iteration ceiling or forced lead reasoner
polyphony start my-project --goal "Fix flaky integration tests" --max-iterations 5 --lead agy
```

### Track Task Status & History
```bash
# List all past runs for a project
polyphony task list my-project

# Inspect iteration details for a specific run
polyphony task status my-project task-20260919-183622-a9aa75
```

---

## 📁 Repository Layout

```text
polyphony/
├── config/
│   └── global.yaml             # Global orchestrator defaults, limits & command blocks
├── orchestrator/
│   ├── cli.py                  # Click CLI interface (polyphony / ai-orch)
│   ├── context.py              # Knowledge compiler & reasoning prompt builder
│   ├── main.py                 # Core orchestration decision loop
│   ├── safety.py               # Safety engine & pre-execution validator
│   ├── state.py                # Task state, iteration tracking, and persistence
│   ├── logging.py              # Structured console & file logging
│   └── report.py               # Markdown task report generation
├── executors/
│   ├── base.py                 # Base executor interface & execution models
│   ├── claude_executor.py      # Claude Code CLI adapter
│   ├── agy_executor.py         # Google Antigravity CLI adapter
│   ├── cursor_executor.py      # Cursor Agent CLI adapter
│   ├── python_executor.py      # Deterministic local Python/Shell runner
│   └── router.py               # Router with bidirectional fallback logic
├── migrate/
│   ├── scanner.py              # Recursive scanner for .claude, .cursor, .agents
│   ├── classifier.py           # Scope & safety classification engine
│   └── translator.py           # Knowledge, hook, and rule translator
├── projects/                   # Registered project knowledge bases
│   └── <project_name>/
│       ├── project.yaml        # Project metadata, executor preferences & safety rules
│       ├── context.md          # Architecture overview & repo structure
│       ├── conventions.md      # Coding style, commit syntax & prompt grammar
│       ├── safety.md           # Guardrail policies & protected paths
│       ├── hooks/              # Executable validation hooks
│       ├── rules/              # Behavioral policy documents
│       └── skills/             # Domain-specific skills
├── skills/                     # Global reusable engineering skills (TDD, review, PR, etc.)
└── tests/                      # Full test suite (executors, router, safety, state, migrate)
```

---

## 🧪 Testing & Verification

Polyphony includes a comprehensive automated test suite verifying executor routing, bidirectional fallback chains, safety gate enforcement, and state management:

```bash
# Run test suite
pytest -v
```

---

## 📄 License

Polyphony is licensed under the [MIT License](LICENSE).
