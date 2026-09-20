# 🎼 Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Architecture: Local--First](https://img.shields.io/badge/architecture-local--first-emerald.svg)]()
[![Cost: Zero Extra API](https://img.shields.io/badge/billing-zero--api--cost-violet.svg)]()
[![Tests: 219 Passed](https://img.shields.io/badge/tests-219%20passed-brightgreen.svg)]()

> **Polyphony** is a local-first, CLI-driven multi-agent engineering orchestrator. It conducts **Claude Code**, **Antigravity (AGY)**, and **Cursor Agent** in concert—turning your existing CLI subscriptions into an autonomous, safe, and disciplined engineering team with **zero incremental API token costs**.

---

## 💡 Why Polyphony?

Modern developers frequently pay for multiple AI subscriptions (**Claude Pro/Max**, **Cursor Pro**, **Google Antigravity**), yet:

1. **API Costs Multiply**: Running autonomous multi-agent loops via standard cloud APIs incurs heavy per-token charges. Polyphony executes directly against your local CLI binaries (`claude -p`, `agy -p`, `cursor agent -p`), running comprehensive reasoning loops with zero added token billing.
2. **Specialized Division of Labor**: High-level architectural reasoning and granular file edits require different strengths. Polyphony separates concerns: **Claude Code** acts as the lead reasoning maestro, delegating implementation to fast, IDE-native executors like **AGY** and **Cursor**, and ground truth to deterministic local Python/Shell.
3. **Control Over Cognition**: Polyphony is a control system that decides when reasoning is necessary, who should reason, who should execute, what evidence is needed, how much context is sufficient, when another iteration is justified, and when the task is actually proven complete.
4. **4-Tier Caching & Deterministic Execution**: Bypasses costly LLM calls for objective facts, git inspections, and deterministic command reruns using multi-tier caches (prompt, evidence, AST/symbols, command output).
5. **Safety & Policy Guardrails**: Enforces strict 4-level human approval policy engines (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), prompt injection defense, secrets detection/redaction, and network access policies.
6. **Isolated Worktrees & Resilient Rollback**: Executes parallel tasks in dedicated Git worktrees; automatically rolls back failed steps without dirtying unrelated user modifications.
7. **Institutional Memory & Provenance**: Persists project architecture, coding conventions, failure history, and verified architectural decisions (ADRs) across runs.

---

## 🏛️ System Architecture

```text
                                  ┌────────────────────────┐
                                  │   User / Mission Goal  │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                         ┌──────────────────────────────────────────┐
                         │       Polyphony Orchestrator Core        │
                         │  (Missions, DAG Engine, State Machine)   │
                         └──────────────┬────────────┬──────────────┘
                                        │            │
            1. Role Context & Budgets   │            │ 5. Review & Consensus
                                        ▼            ▼
                         ┌──────────────────────────────────────────┐
                         │           Agent Roles Cascade            │
                         │   • LEAD_REASONER (Claude / AGY)         │
                         │   • IMPLEMENTER (Cursor / AGY)           │
                         │   • REVIEWER & VERIFIER Agents           │
                         │   • RESEARCHER, RECOVERY, COMPACTOR      │
                         └────────────────────┬─────────────────────┘
                                              │
                                      2. Decides Action
                                              ▼
                         ┌──────────────────────────────────────────┐
                         │     Human Approval & Security Policy     │
                         │   • 4 Risk Levels (LOW/MED/HIGH/CRIT)    │
                         │   • Secrets Redaction & PII Defense      │
                         │   • Network Policy & Offline Mode        │
                         │   • Git Guardrails & Push Interception   │
                         └────────────────────┬─────────────────────┘
                                              │
                                     3. Approved Routing
                                              ▼
                         ┌──────────────────────────────────────────┐
                         │        Smart Cost-Aware Router           │
                         │   • Capability Match (8 Capabilities)    │
                         │   • Deterministic Shortcut (Skip LLM)    │
                         │   • 4-Tier Multi-Level Cache Hit Check   │
                         └────────────────────┬─────────────────────┘
                                              │
                                     4. Parallel / Isolated Execution
                                              ▼
                         ┌──────────────────────────────────────────┐
                         │            Execution Engines             │
                         │  ┌───────────────┬───────────────────┐   │
                         │  │  Antigravity  │   Cursor Agent    │   │
                         │  │     (AGY)     │       (CLI)       │   │
                         │  ├───────────────┼───────────────────┤   │
                         │  │  Claude Code  │ Git Worktrees     │   │
                         │  │     (CLI)     │ (Isolated Branches│   │
                         │  └───────┬───────┴───────────┬───────┘   │
                         │          └─────────┬─────────┘           │
                         │                    ▼                     │
                         │      Deterministic Python / Pytest       │
                         └──────────────────────────────────────────┘
```

---

## ✨ Comprehensive Capabilities

### 1. 💰 Zero Incremental API Costs & Local-First Execution
Operates exclusively through your installed local CLI binaries (`claude`, `agy`, `cursor agent`, python). Requires zero third-party API keys or metered tokens.

### 2. 🎭 Explicit Agent Roles & Capability Routing
Tasks are dispatched to explicit roles:
- `LEAD_REASONER`: High-level strategic planning, decomposition, and review.
- `IMPLEMENTER`: Concrete code modifications and refactoring.
- `REVIEWER`: Static analysis, AST inspection, security, and diff reviews.
- `VERIFIER`: Objective test execution and assertion validation.
- `RESEARCHER`: External documentation, issue tracking, and literature synthesis.
- `RECOVERY`: Failure diagnosis and rollback execution.
- `COMPACTOR`: Summarizing context and pruning redundant token history.

Routed across **8 discrete capabilities**: `CODE_EDITING`, `HIGH_REASONING`, `TEST_EXECUTION`, `DIFF_ANALYSIS`, `RESEARCH`, `SYSTEM_AUDIT`, `CONTEXT_COMPACTION`, and `RECOVERY_ACTION`.

### 3. 📋 Explicit Task Types & Standard Workflows
Polyphony recognizes 8 specialized task types with purpose-built stage blueprints:
- `BUGFIX`: Reproduce ➔ Implement ➔ Test ➔ Verify
- `FEATURE`: Plan ➔ Implement ➔ Test ➔ Verify
- `REFACTOR`: Analyze ➔ Refactor ➔ Test ➔ Verify
- `RESEARCH`: Survey ➔ Synthesize ➔ Prove ➔ Document
- `EXPERIMENT`: Hypothesize ➔ Run ➔ Benchmark ➔ Compare
- `AUDIT`: Scan ➔ Analyze ➔ Score ➔ Report
- `VERIFICATION`: Inspect ➔ Test ➔ Benchmark ➔ Validate
- `MAINTENANCE`: Audit ➔ Update ➔ Test ➔ Verify

### 4. 🔀 Orchestration DAGs & Worktree-Based Parallelism
- **DAG Workflows**: Express complex dependencies (`stage_a` ➔ `stage_b` & `stage_c` ➔ `stage_d`). Ready stages execute as soon as prerequisites pass.
- **Git Worktree Isolation**: Spawns isolated Git worktrees (`.polyphony_worktrees/`) for parallel workers, allowing multiple agents to edit code concurrently without branch conflicts or dirty tree collision.

### 5. 👥 Multi-Agent Review & Consensus
- **Specialized Reviewers**: Lint/type reviewer, security reviewer, diff reviewer, and architectural reviewer.
- **Consensus Engine**: Calculates agreement ratios, detects minority objections, and computes weighted confidence before accepting completion.
- **Review Loop**: Automatically creates `review ➔ fix ➔ review` sub-iterations when findings exceed severity thresholds.

### 6. 🎯 Dynamic Task Decomposition & Project Missions
- **Dynamic Decomposition**: Evaluates complex tasks and breaks them into structured child subtasks with explicit acceptance criteria.
- **Project-Level Missions (`MissionCoordinator`)**: Manages high-level goals ("Make ICD-10 coding pipeline production-ready") across 6 distinct stages:
  1. `architecture audit`
  2. `security audit`
  3. `performance benchmark`
  4. `implementation`
  5. `tests`
  6. `deployment-readiness audit`
  Tracks global token budgets, deadlines, stage dependencies, and shared mission memory.

### 7. ⚡ 4-Tier Caching & Deterministic Smart Routing
- **Prompt Cache**: Tracks provider prefix caching for static instructions.
- **Evidence Cache**: Stores deterministic command outputs (test passes, diffs, git status) keyed by repository commit hash and arguments.
- **AST / Symbols Cache**: Caches symbol definitions and module outlines.
- **Deterministic Command Cache**: Avoids calling LLMs when an objective tool (git, pytest, ruff, find) can determine the answer directly (`execute_smart` / `route_cost_aware`).

### 8. 🪙 Token Usage Tracking, Budgets & Context Compaction
- **TokenLedger & Counter**: Measures detailed input tokens, output tokens, cache read tokens, cache creation tokens, and API calls per turn.
- **Token Budget Ceilings**: Enforce `--token-budget` hard and soft ceilings.
- **Concise Structured Output Contracts**: Emits normalized, ultra-compact YAML execution contracts (`to_concise_contract`), preventing verbose conversational output from leaking into downstream prompts.
- **Context Hierarchy Compressor**: Progressively summarizes old iterations into compact bulleted histories (`RAW TRANSCRIPT` ➔ `STRUCTURED RESULT` ➔ `ITERATION SUMMARY` ➔ `TASK STATE` ➔ `PROJECT MEMORY`).

### 9. 🔬 Research Workflows & Experiment Registry
- **Research Engine**: Formulates hypotheses, tracks research sources, builds claim/evidence chains, and synthesizes findings.
- **Experiment Registry**: Tracks baseline metrics, hypothesis validations, wall-clock latencies, and regression alerts.
- **Reproducibility Snapshots**: Generates self-contained reproducibility bundles with code commits, environment manifests, and replay scripts.

### 10. 🛡️ Security Expansion & Human Approval Policy Engine
- **Human Approval Policy Engine**: Evaluates operations across 4 risk levels:
  - `LOW`: Read files, run tests ➔ `ALLOW`
  - `MEDIUM`: Edit source, install dependencies ➔ `ALLOW` / `ASK`
  - `HIGH`: Modify database, change infrastructure, alter security ➔ `ASK`
  - `CRITICAL`: Production deployments, credential changes, destructive commands ➔ `BLOCK` / `ASK`
- **Secrets Redaction**: Automatic regex scanner blocking OpenAI keys (`sk-...`), AWS keys (`AKIA...`), bearer tokens, and private keys.
- **Network Policy Engine**: Whitelisted domain access, blocked domain lists, and strict offline air-gapped mode.
- **Prompt Injection Defense**: Treats external and web content strictly as untrusted data rather than system policy.
- **Safe Rollback Manager**: Creates pre-task checkpoints; selectively restores modified files upon failure while strictly preserving unrelated user changes.

### 11. 📚 Institutional Memory & Universal Migration
- **Institutional Memory Layer**: Auto-maintains `architecture.md`, `conventions.md`, `decisions.md` (ADRs), and `known_issues.md`.
- **Universal Migration (`polyphony migrate`)**: Ingests existing `.claude/`, `.cursor/`, and `.agents/` configurations and translates them into Polyphony skills, knowledge, hooks, and rules.

### 12. 📊 Observability & Exportable Run Bundles
- **Observability Engine**: Tracks task timelines, executor execution latencies, token consumption trajectories, and failure graphs.
- **Exportable Run Bundles (`polyphony export`)**: Exports self-contained, portable bundles:
  ```text
  task-bundle/
  ├── metadata.yaml
  ├── state.json
  ├── events.jsonl
  ├── report.md
  ├── decisions.md
  ├── metrics.json
  ├── evidence/
  └── diffs/
  ```

### 13. 🧪 Golden Traces & Prompt Regression Testing
- **GoldenTraceSuite**: Records reference execution traces across scenarios (`simple_bugfix`, `executor_timeout`, `rollback`, `human_question`, `multi_iteration`, `token_budget`) and compares future runs for regressions in routing, safety, token efficiency, and state transitions.
- **PromptContextValidator**: Treats prompt and context construction like code, verifying section presence, token budgets, credential redaction, and fact preservation across compression.

### 14. 🧠 Long-Term Intelligence & Learned Routing
- **Task Characteristics Extractor**: Analyzes goal scope, critical paths, and ambiguity.
- **Complexity Estimator**: Evaluates task complexity (`SIMPLE`, `MEDIUM`, `COMPLEX`).
- **Failure Predictor**: Identifies risky tasks before execution starts.
- **Learned Router**: Evaluates candidate workflows against historical benchmark priors (success rate, safety, latency, token economy) to select the optimal workflow.

### 15. 🤖 Background Automation
- **BackgroundAutomationManager**: Runs scheduled dependency audits, repository health checks, test monitoring, and documentation freshness under strict read-only policy controls.

---

## 🚀 Quick Start

### 1. Prerequisites

Ensure you have Python 3.11+ and at least one of the supported CLI agents installed and authenticated:
- **Claude Code CLI**: `claude` (Anthropic Claude Pro/Max)
- **Antigravity CLI**: `agy` (Google Antigravity)
- **Cursor Agent**: `cursor agent` (Cursor Pro)

### 2. Installation

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

Polyphony provides 19 top-level commands, complete task management, and machine-readable `--json` output for automation and scripting.

### Project & Configuration Commands

```bash
# Ingest and translate AI configurations from an existing codebase
polyphony migrate /path/to/my-project --name my-project

# Register an existing repository
polyphony project add my-project --path /path/to/my-project

# List all registered projects
polyphony project list

# Inspect project configuration, knowledge files, and skills
polyphony project inspect my-project

# Display merged global and default configuration
polyphony config show my-project
```

### Starting Tasks

```bash
# Standard autonomous task execution
polyphony start my-project --goal "Implement JWT token rotation with redis"

# Read-only audit mode (strictly prohibits file modifications or destructive actions)
polyphony start my-project --goal "Audit codebase for security vulnerabilities" --read-only

# Dry-run simulation (verifies routing and prompt construction without invoking agents)
polyphony start my-project --goal "Refactor user authentication service" --dry-run

# Specify hard token budget and maximum iterations
polyphony start my-project --goal "Fix off-by-one error in pagination" --token-budget 25000 --max-iterations 5

# Force specific lead reasoner and executor
polyphony start my-project --goal "Optimize database queries" --lead claude --executor cursor

# Dial in exact models & thinking levels
polyphony start my-project \
  --goal "Architect event-driven telemetry service" \
  --lead-model "claude-3-7-sonnet" \
  --lead-thinking "high" \
  --executor-model "gemini-3.1-pro-high" \
  --executor-thinking "high"
```

### Task Lifecycle, Inspection & Ergonomics

```bash
# View active tasks or specific task status (supports --json)
polyphony status
polyphony status <task_id> --json

# Live watch task progress until completion
polyphony watch <task_id> --interval 2

# Pause and resume tasks
polyphony pause <task_id>
polyphony resume <task_id>

# Cancel or abort tasks (triggers automatic rollback to pre-task checkpoint)
polyphony cancel <task_id> --reason "Requirements updated by client"
polyphony abort <task_id> --reason "Critical regression detected"

# Retry a failed or halted task with human guidance
polyphony retry <task_id> --feedback "Do not use in-memory cache; use Redis connection pool"

# Show git diff of changes produced by a task
polyphony diff <task_id>
polyphony diff <task_id> --json

# Deep inspection of state, iterations, tokens, approvals, and metrics
polyphony inspect <task_id>
polyphony inspect <task_id> --json

# Human approval gates (approve or reject pending operations)
polyphony approve <task_id> --notes "Approved after manual review"
polyphony reject <task_id> --reason "Unsafe database migration"

# View event stream for a task
polyphony events <task_id> --limit 50 --json

# Display token expenditure, cache hit ratios, and costs
polyphony metrics <task_id> --json

# Export a portable run bundle (directory or zip)
polyphony export <task_id> --format zip --output ./exports
```

### System Diagnostics, Replay & Explanations

```bash
# Run full system diagnostics (checks CLI tools, environment, git, and permissions)
polyphony doctor

# Replay and reconstruct task execution history from durable event stream
polyphony replay <task_id>

# Explain why decisions, executor selections, failures, and stops occurred
polyphony explain <task_id>

# Run comprehensive benchmark suite
polyphony benchmark
polyphony benchmark --task task_01_simple_bugfix
```

---

## ⚙️ Configuration & Models Cascade

Polyphony uses a 3-tier cascading configuration hierarchy:

```text
Global Config (config/global.yaml)
       ↓
Project Config (projects/<project>/project.yaml)
       ↓
Task / CLI Flags (--lead-model, --token-budget, etc.)
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
token_budget: 50000
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
├── benchmarks/                 # 15 Standardized engineering benchmark tasks & runner
│   ├── tasks/                  # Task definitions and criteria
│   ├── expected/               # Ground truth expected outputs
│   └── runners/                # Automated benchmark runner & token efficiency scorer
├── config/
│   └── global.yaml             # Global orchestrator defaults, limits & command blocks
├── executors/                  # Normalized executor adapters & capability router
│   ├── base.py                 # Formal executor protocol & output contracts
│   ├── capabilities.py         # 8 Discrete executor capabilities
│   ├── roles.py                # Formal agent roles (Lead, Implementer, Reviewer, etc.)
│   ├── cost_aware.py           # Cost-aware smart router & shortcutting
│   ├── claude_executor.py      # Claude Code CLI adapter
│   ├── agy_executor.py         # Google Antigravity CLI adapter
│   ├── cursor_executor.py      # Cursor Agent CLI adapter
│   ├── python_executor.py      # Deterministic local Python/Shell runner with venv detection
│   └── router.py               # Bidirectional fallback router & worktree discovery
├── migrate/                    # Universal AI configuration migration engine
│   ├── scanner.py              # Recursive scanner for .claude, .cursor, .agents
│   ├── classifier.py           # Scope & safety classification engine
│   └── translator.py           # Knowledge, hook, and rule translator
├── orchestrator/               # Core orchestration engine
│   ├── cli.py                  # Click CLI interface (all 19 commands + --json)
│   ├── main.py                 # Core orchestration decision loop & state machine
│   ├── state.py                # Task state machine, atomic persistence & locks
│   ├── dag.py                  # Multi-stage DAG workflow engine
│   ├── worktrees.py            # Git worktree isolation for parallel workers
│   ├── consensus.py            # Multi-agent agreement & consensus engine
│   ├── reviewers.py            # Automated code review & verification agents
│   ├── decomposition.py        # Dynamic task decomposition
│   ├── missions.py             # Multi-stage project-level missions coordinator
│   ├── intelligence.py         # Long-term intelligence & learned routing
│   ├── policy.py               # Human approval policy engine (4 risk levels)
│   ├── tokens.py               # TokenLedger, token counter & usage tracking
│   ├── budgets.py              # Strict token budget ceilings & adaptive allocation
│   ├── caching_layers.py       # 4-Tier caching (Prompt, Evidence, AST, Command)
│   ├── evidence_cache.py       # Deterministic evidence & fact cache
│   ├── deterministic.py        # Objective non-LLM execution shortcuts
│   ├── context_builders.py     # Role-specific context builders & hierarchy compressor
│   ├── context_compaction.py   # Progressive context compaction
│   ├── research.py             # Research workflows & experiment registry
│   ├── golden_traces.py        # Reference execution traces & regression detection
│   ├── prompt_testing.py       # Prompt & context regression validator
│   ├── automation.py           # Scheduled background maintenance & health audits
│   ├── doctor.py               # System health diagnostics & environment checker
│   ├── events.py               # Durable JSONL event logger & task replayer
│   ├── explain.py              # Decision rationale & stop explainer
│   ├── rollback.py             # Safe rollback manager & Git checkpointing
│   ├── recovery.py             # Process crash & state corruption recovery
│   └── bundles.py              # Exportable run bundles generator (task-bundle/)
├── projects/                   # Registered project knowledge bases
├── skills/                     # Global reusable engineering skills
├── tasks/                      # Persisted task state (.json), event logs & reports
└── tests/                      # Full automated test suite (219 passed)
```

---

## 🧪 Testing & Verification

Polyphony includes an automated test suite verifying executor routing, bidirectional fallback chains, safety gates, prompt caching, DAGs, research, missions, and token budgets:

```bash
# Run test suite
pytest -v
```

```text
============================= test session starts ==============================
collected 219 items

tests/test_automation_and_missions.py ...                                [  1%]
tests/test_benchmarks.py .....                                           [  3%]
tests/test_budgets.py ....                                               [  5%]
tests/test_caching_layers.py ....                                        [  7%]
tests/test_capabilities.py ...                                           [  8%]
tests/test_cli.py ............                                           [ 14%]
tests/test_consensus.py ..                                               [ 15%]
tests/test_context.py ....                                               [ 16%]
tests/test_context_builders.py ...                                       [ 18%]
tests/test_context_compaction.py ..                                      [ 19%]
tests/test_cost_aware_routing.py ....                                    [ 21%]
tests/test_dag.py ......                                                 [ 23%]
tests/test_decomposition.py ..                                           [ 24%]
tests/test_deterministic.py .......                                      [ 27%]
tests/test_developer_ux.py .....                                         [ 30%]
tests/test_doctor.py ...                                                 [ 31%]
tests/test_events.py ....                                                [ 33%]
tests/test_evidence_cache.py .....                                       [ 35%]
tests/test_executor_protocol.py .....                                    [ 37%]
tests/test_executors.py .....                                            [ 40%]
tests/test_explain.py ..                                                 [ 41%]
tests/test_fallback.py ...                                               [ 42%]
tests/test_golden_traces_and_prompts.py ......                           [ 45%]
tests/test_intelligence.py ......                                        [ 47%]
tests/test_memory.py ......                                              [ 50%]
tests/test_migrate.py ...                                                [ 52%]
tests/test_models_config.py ..........                                   [ 56%]
tests/test_observability_and_bundles.py ..                               [ 57%]
tests/test_orchestrator.py ......                                        [ 60%]
tests/test_orchestrator_loop.py .........                                [ 64%]
tests/test_output_optimization.py .                                      [ 64%]
tests/test_phase2_features.py ................                           [ 72%]
tests/test_phase3_features.py ......                                     [ 74%]
tests/test_policy.py .....                                               [ 77%]
tests/test_reliability_failure_injection.py ..........                   [ 81%]
tests/test_research.py ..                                                [ 82%]
tests/test_reviewers.py ....                                             [ 84%]
tests/test_roles.py ....                                                 [ 86%]
tests/test_safe_rollback.py ..                                           [ 87%]
tests/test_safety.py ....                                                [ 89%]
tests/test_safety_advanced.py .........                                  [ 93%]
tests/test_task_types.py ....                                            [ 94%]
tests/test_token_and_context_opt.py .....                                [ 97%]
tests/test_token_benchmarks.py ..                                        [ 98%]
tests/test_token_usage_tracking.py ...                                   [ 99%]
tests/test_worktrees.py .                                                [100%]

============================= 219 passed in 6.87s ==============================
```

---

## 📄 License

Polyphony is licensed under the [MIT License](LICENSE).
