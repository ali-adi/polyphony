# Polyphony

A local-first, CLI-driven multi-agent orchestrator that coordinates Claude Code CLI (as the lead reasoning agent) with `agy` (Antigravity CLI) and Cursor Agent (as implementation executors).

## Architecture

```
User Goal
    │
    ▼
Orchestrator Loop (Python)
    │
    ├─► Claude Code CLI (`claude -p`) ── Reasons, plans, and selects executor
    │
    ├─► Executor Router
    │     ├── Antigravity CLI (`agy`)
    │     ├── Cursor Agent CLI (`cursor agent -p`)
    │     └── Local Python / Shell Execution
    │
    └─► Review & Verification Loop ── Tests, safety policies, iterations
```

## Key Capabilities

- **Zero-API-cost reasoning**: Leverages existing CLI subscriptions (`claude`, `agy`, `cursor`) without paying for separate token billing.
- **Project Knowledge Layer**: Manages persistent domain context, conventions, and safety policies per project.
- **Safety Gate Enforcement**: Blocks dangerous operations (`git push`, destructive DB writes, unapproved cost runs) before execution.
- **Universal Migration (`polyphony migrate`)**: Scans existing repositories (Claude Code `.claude/`, Cursor `.cursor/`, Antigravity `.agents/`), classifies configurations, and generates unified orchestrator project definitions.

## Installation

```bash
# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick Start

```bash
# Migrate an existing repository's AI config
polyphony migrate /path/to/repo

# List registered projects
polyphony project list

# Run an autonomous task
polyphony start medicoder --goal "Analyze the repository structure" --read-only
```
