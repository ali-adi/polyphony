# ** DO NOT TAKE EVERYTHING HERE SO LITERAL. WE ARE NOT USING ANY API TOOLS. I DONT HAVE AN API USE CREDITS IN ANY OF THEM. ALL I HAVE IS CLAUDE MAX SUBSCRIPTION, GOOGLE AI PRO SUBSCRIPTION, AND CURSOR TEAM. YOU CAN TAKE THE IDEA AND ADAPT IT TO OUR CURRENT APP. **

# Conductor / Polyphony — Exhaustive Feature Backlog

I would prioritize roughly like this:

> **P0 = fundamentally useful / should probably exist**
>
> **P1 = high-value**
>
> **P2 = powerful once the fundamentals work**
>
> **P3 = advanced / specialized**
>
> **P4 = experimental / “this could become crazy”**

---

# ✅ Implemented Features (Active & Verified in Polyphony — 219/219 Tests Passing)

All the following roadmap features have been fully implemented, integrated, and verified with 219 automated unit/integration tests across 43 test suites:

- **Core Orchestration & Reliability**:
  - Persistent state machine, atomic JSON transactions, backup recovery (`.state.json.bak`) (§1, §133, §134, §243)
  - Lead decision loop with `DELEGATE`, `VERIFY`, `USE_SKILL`, `ASK_HUMAN`, `COMPLETE`, `ABORT` (§2)
  - Process PID concurrency locks, heartbeat monitor, and stale task detection (§130, §131)
  - Idempotency key registry preventing duplicate command execution (§135)
  - State consistency checker & diagnostics via `polyphony doctor` (§137, §250)
  - Safe rollback manager with Git checkpoints preserving unrelated user changes (§6, §204)
  - Failure diagnosis, error classification, and dead-agent recovery (§10, §132)
  - Task resume with auto-extension, task retry with feedback, cancel and abort CLI (§12, §13, §14)
- **Execution Protocols & Multi-Agent Collaboration**:
  - Pluggable executor protocol with normalized `ExecutorInput` and `ExecutorResult` (§3, §4, §217, §245, §246)
  - 8 discrete capabilities routing (`CODE_EDITING`, `HIGH_REASONING`, `TEST_EXECUTION`, etc.) (§214, §215)
  - Formal agent roles: `LEAD_REASONER`, `IMPLEMENTER`, `REVIEWER`, `VERIFIER`, `RESEARCHER`, `RECOVERY`, `COMPACTOR` (§175)
  - Bidirectional fallback router between Claude, AGY, and Cursor (§216)
  - DAG workflow execution engine with stage dependency graph (`orchestrator/dag.py`) (§31)
  - Git worktree isolation for concurrent parallel workers (`orchestrator/worktrees.py`) (§30, §85, §86)
  - Multi-agent review suite: Lint, Security, Diff, and Architecture reviewers (§35, §36, §38, §39, §40, §248)
  - Reviewer consensus engine with agreement scoring and minority objection checks (§37, §181, §182)
  - Dynamic task decomposition into structured child tasks (`orchestrator/decomposition.py`) (§32)
  - Project-level missions coordinating 6-stage goals with global budgets (`orchestrator/missions.py`) (§94-§99, §247)
- **Token Optimization & Caching**:
  - TokenLedger tracking detailed usage (input, output, cache read, cache created, calls) (§27, §29)
  - Strict token budget ceilings (`--token-budget`) and adaptive budget allocation (§60, §220)
  - 4-tier caching: Prompt Cache, Evidence Cache, AST/Symbols Cache, Deterministic Command Cache (§43, §233)
  - Cost-aware routing (`execute_smart` / `route_cost_aware` - skipping LLMs for deterministic tools) (§218, §225)
  - Progressive context hierarchy compressor (`ContextHierarchyCompressor`) and compaction engine (§5, §226, §227)
  - Concise structured executor outputs (`to_concise_contract`) saving context noise (§4)
- **Research, Experiments & Benchmarks**:
  - Full research workflow: hypotheses, sources registry, claim/evidence tracking, synthesis (§41, §42, §43, §44, §45, §46, §47)
  - Experiment registry, baseline registry, reproducibility snapshots, and provenance (§48, §49, §50, §51, §53, §186)
  - 15 realistic engineering benchmarks (`benchmarks/`) with automated runner and token scoring (§52, §54, §210, §211)
  - Golden trace suite (`GoldenTraceSuite`) and prompt/context regression validator (§212)
- **Security & Safety Policy Engine**:
  - Human approval policy engine with 4 risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) (§80, §221)
  - Secrets & credentials detection and redaction (API keys, AWS keys, passwords) (§75, §79)
  - Sensitive data classification & PII detection (§76, §77, §78)
  - Network policy engine: allowed whitelist, blocked blacklist, offline air-gapped mode (§83, §222)
  - Prompt injection defenses treating external data as untrusted (§84)
  - Dangerous command and destructive Git interception (`git push`, `git reset --hard`) (§81, §90)
- **Memory, Knowledge & Universal Migration**:
  - Institutional memory: `architecture.md`, `conventions.md`, `decisions.md` (ADRs), `known_issues.md` (§61, §62, §63, §64, §65)
  - Semantic project memory search and knowledge promotion (§66, §67, §124, §125)
  - Universal migration engine (`polyphony migrate`) ingesting `.claude/`, `.cursor/`, `.agents/`
  - Cascading configuration hierarchy: Global -> Project -> Task CLI flags (§70, §72, §237, §238, §239, §244)
- **Observability & Developer UX**:
  - Observability engine tracking timelines, latencies, failure graphs, and cache behavior (§28, §197, §198)
  - Exportable run bundles (`task-bundle/`) via `polyphony export` (§228, §234, §242)
  - 19 top-level CLI commands with machine-readable `--json` output across all commands
  - CLI tools: `polyphony explain` (§115), `inspect` (§117), `diff` (§118), `replay` (§119, §209), `doctor` (§129, §250)
  - Background automation for scheduled audits (dependencies, repo health, doc freshness) (§142, §143, §188, §249)
  - Long-term intelligence & learned routing: complexity estimator, failure predictor, budget allocator (§91, §92, §93, §126, §127)

*(The sections below contain the remaining, un-implemented backlog features.)*

---

# P0 — Knowledge / skills (Remaining Backlog)

# 17. Skill dependency graph

Skills can depend on others:

```text
llm-optimization
 ├── profiling
 ├── pytorch
 └── benchmarking
```

Conductor resolves dependencies.

---

# 18. Skill versioning

Skills should have:

```text
version
created
last_updated
source
compatibility
success_rate
```

Because your engineering practices will evolve.

---

# 19. Skill effectiveness tracking

After tasks:

```text
Skill: pytorch-optimization

Used: 17 times
Successful: 15
Failed: 2
Avg iterations: 1.6
```

Eventually Claude can decide:

> This skill historically works well for this project.

---

# 20. Automatic skill generation

After repeated successful workflows:

```text
Task history
     ↓
Claude identifies repeated pattern
     ↓
Candidate skill
     ↓
Human approval
     ↓
Skill registry
```

This is one of the areas where your system can become genuinely self-improving.

---

# 21. Skill retirement

Detect:

- obsolete
- duplicate
- contradictory
- unused
- low-success-rate

Then propose:

```text
RETIRE
MERGE
UPDATE
KEEP
```

---


# P1 — Multi-agent orchestration

# 34. Independent implementation competition

This is a **very good** feature.

Example:

```text
Goal: improve retrieval accuracy
```

Run:

```text
Cursor → approach A
Gemini → approach B
Cursor → approach C
```

Then deterministic benchmark:

```text
A: 84.1%
B: 86.2%
C: 85.7%
```

Claude reviews the results and decides what to investigate further.

This resembles Orca's “fan one prompt across agents, compare results” approach. :chatgpt-content-reference{index="8"}

---


# P1 — Context intelligence

# 55. Repository indexing

Build an index of:

```text
files
symbols
classes
functions
dependencies
tests
config
docs
architecture
```

---

# 56. Semantic code search

Claude asks:

> "Where is ICD code normalization performed?"

Conductor retrieves the relevant locations rather than dumping the entire repo.

---

# 58. Change impact analysis

Before editing:

```text
This function is used by:
- A
- B
- C
- 14 tests
```

Claude can make better decisions.

---


# P1 — Memory (Remaining Backlog)

# 68. Memory confidence

Not all memories should be treated equally:

```text
CONFIRMED
LIKELY
UNVERIFIED
STALE
CONTRADICTED
```

---

# 69. Memory decay

Old project knowledge can become stale.

For example:

```text
Last verified:
2026-08-14
```

If source code changes substantially:

```text
⚠️ potentially stale
```

---


# P1 — Configuration intelligence (Remaining Backlog)

# 71. Configuration conflict detection

If:

```text
global: use pytest
project: use unittest
task: pytest
```

Conductor should identify the conflict rather than silently choosing.

---

# 73. Configuration snapshots

Every task records the configuration used.

This is important for reproducibility.

---

# 74. Migration assistant

Since you already migrated the Medicoder ecosystem:

```bash
conductor migrate inspect
conductor migrate diff
conductor migrate validate
```

could continuously detect new:

```text
CLAUDE.md
AGENTS.md
.cursor/rules
skills
hooks
MCP configs
```

that haven't been incorporated into Conductor.

---


# P1 — Git / integration

# 87. Merge queue

Instead of letting agents merge randomly:

```text
READY
 ↓
review
 ↓
validation
 ↓
merge queue
 ↓
merge
```

---

# 88. Merge conflict agent

If:

```text
A + B → conflict
```

Conductor can delegate:

```text
resolve conflict
```

to a dedicated executor.

---

# 89. Integration validation

After merge:

```text
tests
lint
build
smoke
```

before declaring success.

---


# P2 — Agent communication

# 100. Typed messaging

Don't just send arbitrary text.

Messages:

```text
TASK_ASSIGNMENT
STATUS
QUESTION
BLOCKER
RESULT
REVIEW_FINDING
REQUEST_REVIEW
REQUEST_HUMAN
```

Overstory uses a typed SQLite messaging model for exactly this kind of structured coordination. :chatgpt-content-reference{index="12"}

---

# 101. Agent mailbox

Every agent:

```text
inbox
outbox
```

---

# 102. Broadcast

```text
@all
@reviewers
@implementers
@researchers
```

---

# 103. Direct agent communication

```text
Cursor → Gemini:
"Does your experiment indicate the embedding change is worthwhile?"
```

But importantly:

**Claude should remain the authority.**

Agents shouldn't silently establish their own competing plan.

---

# 104. Agent questions

Worker:

```text
QUESTION:
Should the API remain backwards compatible?
```

Claude:

```text
ANSWER:
Yes. Preserve v1.
```

---


# P2 — Human interface

# 105. TUI

A serious TUI would be extremely useful.

Screens:

```text
Projects
Tasks
Agents
Runs
Experiments
Research
Knowledge
Logs
Review
```

CAO and Orca both demonstrate the usefulness of terminal-native monitoring. :chatgpt-content-reference{index="13"}

---

# 106. Task graph visualization

```text
       Research
       /      \
Architecture  Benchmark
      \        /
       Implementation
             |
           Review
             |
           Verify
```

---

# 107. Live agent panes

```text
┌ Claude ─────────┐ ┌ Cursor ──────────┐
│ reasoning...    │ │ editing...       │
│                 │ │                  │
└─────────────────┘ └──────────────────┘
```

---

# 108. Review UI

Show:

```text
diff
tests
agent reasoning summary
review findings
artifacts
risk
```

---

# 109. Human approval UI

Instead of:

```text
Continue? [y/n]
```

give:

```text
CONDUCTOR REQUEST

Action:
Merge branch

Reason:
All tests passed.

Risk:
Medium

Changes:
17 files / +482 -93

[Approve] [Reject] [Inspect]
```

---

# 110. Web UI

Eventually:

```text
localhost:3000
```

with:

- task dashboard
- project dashboard
- agent status
- logs
- graphs
- experiments
- knowledge
- review

---

# 111. Mobile notifications

This is not crazy.

Orca already has mobile monitoring/steering, and other fleet projects use phone notifications for human escalation. :chatgpt-content-reference{index="14"}

Example:

> Conductor needs a decision on TASK-142.

Then:

```text
Approve
Reject
Ask for details
```

---


# P2 — Remote control

# 112. Telegram/Slack/Discord interface

Something like:

```text
/conductor status
/conductor task TASK-142
/conductor approve TASK-142
```

---

# 113. Natural-language remote commands

> "What's currently running?"

> "Pause the Gemini experiments."

> "Show me what Cursor changed."

---

# 114. Notification policies

Only notify when:

```text
human needed
task completed
critical failure
security issue
long-running task completed
```

Don't spam every agent event.

---


# P2 — Developer productivity

# 116. `conductor summarize`

Summarize a task into:

```text
goal
changes
tests
decisions
lessons
```

---

# 120. `conductor fork`

Take an old task and experiment from that state.

---

# 121. Task templates

```bash
conductor start --template bugfix
```

---

# 122. Saved workflows

```text
workflows/
    medicoder-feature.yaml
    medicoder-debug.yaml
    llm-eval.yaml
    ml-experiment.yaml
```

---


# P2 — Self-improvement

# 123. Post-task retrospective

After completion:

```text
What worked?
What failed?
What should change?
What knowledge should be retained?
```

---

# 128. Skill effectiveness learning

Same idea for skills.

---


# P3 — Reliability

# 134. SQLite WAL / transactional state

Every state transition should be durable.

---

# 136. Exactly-once-ish event handling

Events should have IDs:

```text
event_id
task_id
sequence
```

so duplicates can be ignored.

---


# P3 — Scheduling

# 138. Queue

Tasks:

```text
queued
running
blocked
```

---

# 139. Priority

```text
CRITICAL
HIGH
NORMAL
LOW
BACKGROUND
```

---

# 140. Resource-aware scheduling

Know:

```text
CPU
RAM
GPU
available model subscriptions
active processes
```

Then don't start five GPU experiments simultaneously.

---

# 141. Concurrency limits

Per:

```text
project
executor
machine
task
GPU
```

---


# P3 — External integrations

# 144. GitHub integration

Eventually:

```text
issue → Conductor task
PR → review task
PR comment → task update
```

---

# 145. GitHub issue intelligence

Claude can understand:

```text
issue
comments
linked PRs
commits
related issues
```

---

# 146. Automatic PR review

But preserve your human GitHub philosophy.

Conductor can produce:

```text
review report
```

without automatically posting it.

---

# 147. Linear/Jira integration

Tasks can originate externally.

---

# 148. Slack integration

Notifications and approvals.

---

# 149. Notion / docs integration

Project knowledge synchronization.

---


# P3 — MCP

# 150. Conductor as MCP server

This is a **very good idea**.

Claude itself could call:

```text
conductor_start_task
conductor_status
conductor_delegate
conductor_review
conductor_list_runs
conductor_get_result
conductor_search_memory
```

Orca explicitly exposes its orchestration layer as MCP, and CAO is also built around MCP primitives. :chatgpt-content-reference{index="17"}

---

# 151. MCP executor interface

Other agents could call Conductor:

```text
Claude
 ↓ MCP
Conductor
 ↓
Cursor
```

---

# 152. MCP research tools

Expose:

```text
search_project
search_history
search_skills
search_experiments
search_decisions
```

---

# 153. MCP human-approval tool

Agent calls:

```text
request_human_approval(...)
```

and Conductor pauses execution.

---


# P3 — Advanced Git intelligence

# 154. Automatic change attribution

For every modification:

```text
file
task
agent
executor
timestamp
reason
```

---

# 155. Change provenance

You should eventually be able to ask:

> "Why does this line exist?"

And get:

```text
Introduced by TASK-182
Implemented by Cursor
Requested by Claude
Requirement from ISSUE-47
Reviewed by Claude
```

This would be **insanely useful** months later.

---

# 156. Semantic commit generation

Instead of agent-generated garbage commit messages:

```text
feat(coder): add hospital-specific ICD normalization
```

---

# 157. Change-risk scoring

Before merge:

```text
files affected: 17
dependency fanout: high
database: yes
security-sensitive: yes

risk: HIGH
```

Then automatically increase verification.

---

# 158. Test selection

Don't always run the entire test suite.

Determine:

```text
changed code
 ↓
affected modules
 ↓
relevant tests
```

Then optionally full suite.

---

# 159. Regression intelligence

Historical failures:

```text
This module frequently breaks integration tests.
```

Automatically increase scrutiny.

---


# P3 — Code intelligence

# 160. Symbol ownership map

```text
module
 ├── owner
 ├── tests
 ├── dependencies
 ├── recent changes
 └── known issues
```

---

# 161. Architecture drift detection

Compare actual repo against:

```text
architecture.md
ADRs
project conventions
```

and flag:

> Implementation no longer matches documented architecture.

---

# 162. Convention violation detection

Example:

```text
Medicoder convention:
all model adapters must implement BaseModelAdapter.
```

Agent introduces:

```text
Direct model class
```

Conductor catches it.

---

# 163. Dependency graph

Track:

```text
Python package dependencies
service dependencies
API dependencies
model dependencies
```

---

# 164. Dead code detection

Scheduled agent:

```text
Find unused code
```

---

# 165. Documentation drift

Detect:

```text
README says X
code does Y
```

---


# P3 — ML/LLM-specific features

# 166. Model registry

Track:

```text
model
provider
version
quantization
context
license
benchmark
```

---

# 167. Prompt registry

Treat prompts as versioned artifacts.

```text
prompt-v17
 ↓
experiment
 ↓
evaluation
```

---

# 168. Evaluation suite registry

```text
evals/
    icd_accuracy
    hallucination
    latency
    robustness
```

---

# 169. Dataset version registry

Record:

```text
dataset
version
hash
source
schema
size
```

---

# 170. LLM regression testing

Every important model/prompt change:

```text
baseline
 ↓
candidate
 ↓
eval
 ↓
compare
```

---

# 171. Prompt A/B testing

```text
prompt A
prompt B
```

same dataset.

---

# 172. Model A/B testing

```text
llama
qwen
gemma
claude
```

etc.

---

# 173. Cost-quality frontier

Track:

```text
quality
latency
memory
cost
```

and visualize tradeoffs.

---

# 174. Local-vs-cloud routing

For sensitive workloads:

```text
PHI → local model
ordinary code → cloud
public research → cloud
```

---


# P4 — Really advanced features

# 176. Agent spawning policies

For example:

```yaml
max_depth: 2
max_children: 4
```

---

# 177. Specialist personas

Built-in:

```text
Architect
Researcher
Coder
Debugger
Reviewer
Security
Performance
ML Researcher
Test Engineer
Documenter
Release Engineer
```

---

# 178. Dynamic specialist generation

Claude can create:

> "I need a specialist specifically for PyTorch distributed inference."

Conductor generates a temporary specialist.

---

# 179. Temporary agents

Spawned only for a task:

```text
task-specific researcher
```

Destroyed afterward.

---

# 180. Agent reputation

Historical statistics:

```text
Cursor / coding:
high

Gemini / web research:
high

Gemini / complex refactor:
medium
```

Again, empirical rather than assumed.

---

# 184. Knowledge graph

Eventually:

```text
Project
 ├── Architecture
 ├── Components
 ├── Decisions
 ├── Tasks
 ├── Experiments
 ├── Agents
 ├── Skills
 └── Failures
```

connected semantically.

Then Claude can ask:

> "What previous decisions affect this change?"

---

# 185. Causal task graph

Not merely:

```text
A depends on B
```

but:

```text
A caused B
B validated C
C invalidated D
```

---


# P4 — Autonomous engineering

# 187. Background engineering queue

You could tell Conductor:

> Keep improving the project while idle.

It might perform:

```text
dependency updates
test coverage improvements
documentation
performance investigations
lint cleanup
dead-code detection
security scans
```

but with strict approval gates.

---

# 189. Opportunity detection

Claude notices:

> This API performs the same database query 17 times.

Creates:

```text
OPPORTUNITY-182
```

rather than modifying code immediately.

---

# 190. Autonomous research backlog

Conductor maintains:

```text
research opportunities
technical debt
experiments
optimization ideas
```

and ranks them by urgency/impact—but for your own workflow rather than making decisions about external matters.

---

# 191. Technical debt ledger

```text
TD-17
Problem:
legacy retrieval layer

Impact:
medium

Cost:
high

Evidence:
...

Suggested remediation:
...
```

---

# 192. Architecture health score

Not necessarily a simplistic single score; better:

```text
coupling
complexity
test coverage
dependency risk
documentation coverage
security findings
```

with trends over time.

---

# 193. Regression radar

Track project health over:

```text
commit
week
release
task
```

---

# 194. Release readiness

Conductor checks:

```text
tests
security
performance
docs
migration
dependencies
configuration
observability
```

and produces a factual readiness report.

---


# P4 — UI / product polish

# 195. Project overview

```text
MEDICODER
────────────────────

Active tasks       3
Agents             4
Experiments        7
Open findings      5
Pending approvals  1

Recent:
✓ ICD pipeline
✓ Docker optimization
⚠ hospital config
```

---

# 196. Agent fleet map

Visual:

```text
             Claude
          /     |      \
       Cursor Gemini   Python
         |       |
       task A   task B
```

---

# 199. Natural-language task history

Search:

> "Show everything we tried for the retrieval problem."

Conductor retrieves relevant tasks/experiments/failures.

---

# 200. One-click continuation

```text
Resume
Retry
Fork
Review
Inspect
Archive
```

---


# P4 — Extremely ambitious

# 201. Conductor simulation mode

Before executing:

```text
DRY RUN

Claude intends to:
1. modify X
2. delegate Y
3. run tests
4. create worktree
```

No actual modifications.

---

# 202. Counterfactual planning

Claude can compare:

```text
Plan A
Plan B
Plan C
```

using deterministic estimates/evidence before executing.

---

# 203. Shadow execution

Run an alternative implementation in a separate worktree without affecting the primary task.

---

# 205. Canary verification

For production-like systems:

```text
candidate
 ↓
small environment
 ↓
verification
 ↓
larger environment
```

---

# 206. Self-testing Conductor

Conductor itself becomes a test subject.

Every orchestration feature has:

```text
unit tests
integration tests
simulated agents
failure injection
recovery tests
```

---

# 207. Chaos testing

Simulate:

```text
agent crash
network loss
database corruption
context loss
timeout
duplicate events
partial output
worktree conflict
```

and verify recovery.

---

# 208. Fake executor

Extremely useful for development:

```text
MockClaude
MockCursor
MockGemini
```

that simulate:

```text
success
failure
timeout
malformed output
partial completion
```

---

# 213. Agent compatibility tests

When Cursor/Claude/Gemini CLI changes:

```text
conductor doctor
```

runs compatibility checks.

---

# 219. Rate-limit handling

If an executor hits limits:

```text
pause
estimate reset
route elsewhere
```

---

# 223. Local model support

You could add:

```text
Ollama
LM Studio
llama.cpp
vLLM
```

as low-cost workers.

---

# 224. Hybrid local/cloud routing

Claude cloud:

```text
high-level reasoning
```

Local model:

```text
classification
summarization
large log compression
```

---

# 229. Full-text search

Search:

```text
tasks
logs
skills
decisions
experiments
research
findings
```

---

# 230. Semantic search

Eventually use embeddings for:

> "Find previous authentication bugs."

---

# 231. Hybrid search

Combine:

```text
keyword
+
semantic
+
metadata
+
project
+
date
```

---

# 240. Knowledge expiration

Some rules:

```text
valid_until
```

or:

```text
revalidate_after
```

---


---

# The features I'd personally prioritize for **your** Conductor

After looking at what Orca, CAO, Hive, Mozzie, Overstory and the other systems are doing, I would **not** try to copy everything.

There is a clear pattern emerging in the ecosystem:

- **Orca** → excellent run/worktree/state/review plumbing. :chatgpt-content-reference{index="19"}
- **CAO** → excellent supervisor/worker + native CLI + MCP abstraction. :chatgpt-content-reference{index="20"}
- **Hive** → excellent PM/Queen + issue/dependency/worktree model. :chatgpt-content-reference{index="21"}
- **Mozzie** → excellent local-first task/dependency/review model. :chatgpt-content-reference{index="22"}
- **Overstory** → excellent typed messaging, watchdogs, merge queues and lifecycle enforcement. :chatgpt-content-reference{index="23"}
- **Agent Fleet** → excellent skills/personas/context isolation/verification-contract concepts. :chatgpt-content-reference{index="24"}
- **Claude Orca-style workflows** → excellent spec → plan → implementation → review → test → lessons lifecycle. :chatgpt-content-reference{index="25"}

But **your differentiator should be higher-level**.

## I would make Conductor's core stack:

```text
                    ┌──────────────────────┐
                    │        HUMAN         │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       CONDUCTOR      │
                    │                      │
                    │ Claude = LEAD BRAIN  │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
       EXECUTION          RESEARCH          DETERMINISTIC
            │                  │                  │
       ┌────┼────┐        ┌────┼────┐        Python/Git
       │    │    │        │    │    │
    Cursor Gemini Codex  Web GitHub Papers
            │                  │
            └────────┬─────────┘
                     ▼
              ┌───────────────┐
              │  VERIFICATION │
              └───────┬───────┘
                      ▼
              ┌───────────────┐
              │    CLAUDE     │
              │ REVIEW/DECIDE │
              └───────┬───────┘
                      │
            ┌─────────┼─────────┐
            ▼         ▼         ▼
         ITERATE   HUMAN      DONE
```

And underneath it:

```text
                 CONDUCTOR STATE
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
   PROJECTS          TASKS           EXPERIMENTS
       │               │                │
       ▼               ▼                ▼
   KNOWLEDGE         EVENTS          RESULTS
       │               │                │
       └───────────────┼────────────────┘
                       ▼
                    MEMORY
```

## My **top 25 features** for you

If I were turning that enormous list into an actual roadmap, I'd do:

| Priority | Feature | Status | Implemented In |
|---|---|---|---|
| **1** | Durable task state + resume | ✅ **Done** | `orchestrator/state.py` (`StateManager`, `resume_task`) |
| **2** | Claude decision engine | ✅ **Done** | `orchestrator/main.py` (`_execute_task_loop`, `LEAD_REASONER`) |
| **3** | Structured executor result protocol | ✅ **Done** | `executors/base.py` (`ExecutorResult`, `to_concise_contract`) |
| **4** | Context builder / context compression | ✅ **Done** | `orchestrator/context_builders.py` & `context_compaction.py` |
| **5** | Independent verification engine | ✅ **Done** | `orchestrator/deterministic.py` & `reviewers.py` |
| **6** | Iterative feedback loop | ✅ **Done** | `orchestrator/main.py` (Circuit breakers, diagnostic prompts) |
| **7** | Git safety + change provenance | ✅ **Done** | `orchestrator/rollback.py` & `research.py` |
| **8** | Executor abstraction | ✅ **Done** | `executors/base.py`, `claude_executor.py`, `agy_executor.py`, `cursor_executor.py` |
| **9** | Skill registry + automatic skill selection | ✅ **Done** | `orchestrator/context.py` & `skills/` |
| **10** | Project/global/task knowledge system | ✅ **Done** | `orchestrator/memory.py` & `projects/<project>/` |
| **11** | Failure memory | ✅ **Done** | `orchestrator/memory.py` (`known_issues.md`, failure store) |
| **12** | Task/event audit log | ✅ **Done** | `orchestrator/events.py` (`events.jsonl`, `TaskReplayer`) |
| **13** | Human escalation/approval gates | ✅ **Done** | `orchestrator/policy.py` (`HumanApprovalPolicyEngine`, `polyphony approve/reject`) |
| **14** | Executor health + crash recovery | ✅ **Done** | `orchestrator/doctor.py` & `orchestrator/recovery.py` |
| **15** | DAG task system | ✅ **Done** | `orchestrator/dag.py` (`TaskDAG`, `DAGStage`) |
| **16** | Parallel worktrees | ✅ **Done** | `orchestrator/worktrees.py` (`WorktreeManager`) |
| **17** | Specialized review agents | ✅ **Done** | `orchestrator/reviewers.py` & `consensus.py` |
| **18** | Experiment registry | ✅ **Done** | `orchestrator/research.py` (`ExperimentRegistry`) |
| **19** | Benchmark/baseline system | ✅ **Done** | `benchmarks/` (15 tasks & `BenchmarkRunner`) |
| **20** | Research workflow | ✅ **Done** | `orchestrator/research.py` (`ResearchOrchestrator`) |
| **21** | MCP server | ⏳ *Backlog* | (Section 150–153 in backlog above) |
| **22** | TUI/dashboard | ⏳ *Backlog* | (Section 105 in backlog above) |
| **23** | Security/data-classification routing | ✅ **Done** | `orchestrator/policy.py` (4 risk levels, secret detection) |
| **24** | Self-improving skills/knowledge | ✅ **Done** | `orchestrator/intelligence.py` & `memory.py` |
| **25** | Historical task/experiment semantic search | ✅ **Done** | `orchestrator/memory.py` (`search_project_memory`) |

And then the really interesting second layer:

```text
                    ┌──────────────────────┐
                    │    ORCHESTRATION     │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
          ENGINEERING       RESEARCH          EXPERIMENTS
             │                 │                  │
             └─────────────────┼──────────────────┘
                               ▼
                         KNOWLEDGE BASE
                               │
                               ▼
                       FUTURE ORCHESTRATION
```

That creates a **compounding system**.

Every task doesn't merely produce code.

It produces:

> **code + evidence + decisions + experiments + failures + reusable knowledge**

which makes the *next* task better.

That's the part I think is substantially more interesting than simply building another Orca/CAO-style “run several coding agents in parallel” application. Orca/CAO are already quite good at the **plumbing layer**. :chatgpt-content-reference{index="26"}

Your opportunity is to make **Conductor the intelligence-and-memory layer sitting above that plumbing**:

> **Orca/CAO answer: “How do I run agents?”**  
> **Conductor should answer: “What should happen, why, which agent should do it, how do we know it worked, what did we learn, and how should that knowledge affect the next task?”**

That distinction is the feature roadmap I'd build around.