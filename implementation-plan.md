# Local Multi-Agent Engineering & Research Orchestrator
## Exhaustive Implementation Handoff

> **Status:** Master implementation plan  
> **Primary project:** Medicoder  
> **Installation:** `~/ai-orchestrator/`  
> **Primary repository:** existing Medicoder company repository  
> **Design principle:** Claude > Cursor > Gemini in reasoning responsibility  
> **GitHub principle:** GitHub remains completely normal; orchestration state stays local  
> **Migration principle:** Existing Medicoder AI knowledge is preserved, understood, classified, and migrated—not discarded.

---

# 0. Executive Summary

Build a **permanent, reusable, local-first AI engineering and research orchestration system** on the user's Mac.

This is not a one-off automation script for a single Medicoder feature.

It is intended to become a reusable personal engineering environment capable of working across:

- Medicoder
- future repositories
- software engineering
- ML engineering
- LLM engineering
- research
- experimentation
- debugging
- optimization
- benchmarking
- data analysis
- model evaluation
- architecture work
- documentation
- testing
- refactoring
- repetitive engineering

The core system is:

```text
                    USER
                     │
                     ▼
                  CLAUDE
             highest reasoning
                     │
          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼
       CURSOR     GEMINI     PYTHON/
    implementation experimentation deterministic
          │          │          │
          └──────────┼──────────┘
                     ▼
              LOCAL PROJECT
                     │
                     ▼
              structured results
                     │
                     ▼
                  CLAUDE
             review / decide
                     │
                 iterate
                     │
                    ...
                     │
                     ▼
                  USER
                     │
               manual review
                     │
                     ▼
                  GITHUB
```

The important property is that **Claude is not merely another coding agent**.

Claude is the system's highest-level reasoning layer.

Cursor is the primary implementation layer.

Gemini/Antigravity is a lower-priority execution and experimentation layer.

Deterministic Python/local tooling handles work that should not consume LLM reasoning at all.

---

# 1. Core Agent Hierarchy

The system intentionally follows this hierarchy:

```text
CLAUDE
  ↓
CURSOR
  ↓
GEMINI
```

This does **not** mean "Claude is always better at every individual operation."

It means the architecture assigns progressively less difficult reasoning to progressively lower layers.

## 1.1 Claude — highest-level reasoning

Claude owns:

- understanding the user's actual objective
- understanding project context
- understanding accumulated engineering knowledge
- architecture decisions
- problem decomposition
- strategy selection
- deciding what needs to be investigated
- deciding what should be implemented
- deciding which executor should do it
- interpreting results
- diagnosing failures
- changing strategy
- evaluating competing approaches
- deciding whether an experiment is meaningful
- deciding whether a result is sufficient
- reviewing implementation
- deciding whether another iteration is needed
- deciding when the task is complete
- updating durable project knowledge when appropriate

Claude should be treated as the **lead engineer / researcher / reviewer / decision-maker**.

---

# 1.2 Cursor — primary implementation agent

Cursor owns most concrete engineering execution:

- inspecting source code
- creating files
- modifying files
- implementing features
- refactoring
- fixing bugs
- writing tests
- running tests
- debugging compiler/runtime errors
- making controlled implementation changes
- performing repetitive source transformations
- iterating on concrete implementation instructions

Claude tells Cursor **what should be accomplished and why**.

Cursor determines the concrete edits required to accomplish that instruction.

---

# 1.3 Gemini / Antigravity — secondary execution and experimentation

Gemini/Antigravity is primarily used for work where:

- deep architectural reasoning is unnecessary
- an independent implementation is useful
- exploratory experimentation is useful
- browser/tool workflows are useful
- parallel investigation is useful
- alternative approaches should be generated
- a cheaper/faster execution layer is preferable

Gemini should not normally become the system's primary architectural decision-maker.

Claude remains responsible for interpreting its output.

---

# 1.4 Python / deterministic workers

Do not use an LLM for deterministic work.

Examples:

```text
benchmark aggregation
metric calculation
JSON parsing
CSV processing
statistical calculations
test result aggregation
Git status inspection
diff statistics
file inventory
experiment comparison
dataset analysis
log processing
artifact generation
```

Use ordinary local programs whenever possible.

---

# 1.5 Responsibility matrix

| Responsibility | Claude | Cursor | Gemini | Python |
|---|---:|---:|---:|---:|
| Understand objective | **Primary** | — | — | — |
| Architecture | **Primary** | Support | Support | — |
| Strategy | **Primary** | — | — | — |
| Project knowledge migration | **Primary** | Implementation support | — | Support |
| Source-code implementation | Review | **Primary** | Secondary | — |
| Refactoring | Strategy/review | **Primary** | Secondary | — |
| Debugging | Diagnosis | **Primary execution** | Secondary | Support |
| Experiment design | **Primary** | Support | Support | Support |
| Experiment execution | Review | Support | **Primary secondary** | **Primary deterministic** |
| Benchmark calculation | Interpret | — | — | **Primary** |
| Result interpretation | **Primary** | — | — | Support |
| Final verification | **Primary** | Execute | Execute | Execute |
| Task completion decision | **Primary** | — | — | — |
| GitHub push | **Never automatic** | — | — | — |

---

# 2. Fundamental Architecture

The system has three persistent conceptual layers:

```text
GLOBAL ORCHESTRATOR
        │
        ▼
PROJECT
        │
        ▼
TASK
```

And four types of reusable knowledge:

```text
GLOBAL KNOWLEDGE
PROJECT KNOWLEDGE
TASK KNOWLEDGE
EXECUTOR KNOWLEDGE
```

---

# 3. Permanent vs Persistent vs Temporary

## Permanent

Installed once:

```text
~/ai-orchestrator/
```

Contains:

- orchestration engine
- agent adapters
- executor adapters
- global skills
- global rules
- safety policies
- project registry
- CLI
- shared infrastructure

---

## Persistent project state

Example:

```text
~/ai-orchestrator/projects/medicoder/
```

Contains knowledge that remains relevant across many tasks:

- architecture
- conventions
- important decisions
- known issues
- project-specific skills
- environment information
- testing information
- deployment constraints
- accumulated project knowledge

---

## Temporary task state

Example:

```text
~/ai-orchestrator/tasks/medicoder/<task-id>/
```

Contains:

- objective
- plan
- iteration history
- executor requests
- executor results
- experiments
- benchmarks
- artifacts
- task logs
- final report

---

# 4. Critical Requirement: Existing Medicoder AI Knowledge Must Be Migrated

The user has already spent significant time developing an AI-assisted workflow inside the Medicoder repository.

That accumulated knowledge is valuable.

It may include:

- `CLAUDE.md`
- `AGENTS.md`
- `.cursor/rules/`
- Cursor configuration
- `SKILL.md`
- project-specific skills
- hooks
- scripts
- prompts
- MCP configuration
- coding conventions
- testing conventions
- architecture instructions
- debugging procedures
- research procedures
- optimization workflows
- model-development workflows
- tool usage conventions
- temporary workarounds
- lessons learned
- agent-specific instructions

The new system must **absorb this knowledge**.

It must not simply start from an empty template.

The migration should be:

```text
EXISTING MEDICODER AI WORKFLOW
              │
              ▼
           INVENTORY
              │
              ▼
          UNDERSTAND
              │
              ▼
           CLASSIFY
              │
              ▼
           TRANSLATE
              │
              ▼
        VALIDATE
              │
              ▼
NEW ORCHESTRATOR KNOWLEDGE
```

---

# 5. Migration Philosophy

The first migration should optimize for:

> **lossless understanding, not immediate cleanliness.**

Initially prefer:

```text
duplicate-but-understood
```

over:

```text
clean-but-missing-important-behavior
```

The system can be simplified later.

Do not aggressively delete or consolidate existing rules before understanding their purpose.

---

# 6. Phase 0 — Existing Configuration Migration

This is the **first implementation phase**.

Before building the autonomous loop:

1. inspect the Medicoder repository
2. inventory AI configuration
3. inventory skills
4. inventory hooks
5. inventory MCP/tool configuration
6. inventory prompts
7. inventory conventions
8. inventory workflow instructions
9. snapshot originals
10. classify each item
11. translate semantics
12. build Medicoder project context
13. build global reusable skills
14. build executor-specific rules
15. validate the migration
16. only then consider deprecating legacy configuration

---

# 7. Migration Snapshot

Before changing anything:

```text
~/ai-orchestrator/migration/medicoder/
```

Create:

```text
migration/
└── medicoder/
    ├── original/
    ├── inventory.md
    ├── migration.yaml
    ├── translated/
    ├── validation/
    └── README.md
```

The original snapshot provides a rollback/reference point.

---

# 8. Migration Inventory

Search broadly for:

```text
CLAUDE.md
AGENTS.md
.cursor/
.cursor/rules/
SKILL.md
skills/
hooks/
.git/hooks/
scripts/
.ai/
.ai-rules/
mcp.json
.mcp/
*.md
*.mdc
*.yaml
*.yml
*.json
```

Also inspect relevant:

```text
test configuration
lint configuration
formatter configuration
build configuration
CI configuration
package configuration
environment configuration
developer scripts
```

Not every discovered file is AI configuration.

The purpose of the broad scan is to avoid missing important context.

---

# 9. Migration Classification

Every discovered item should be classified as one or more of:

```text
GLOBAL
PROJECT
TASK
AGENT-SPECIFIC
EXECUTOR-SPECIFIC
HOOK / AUTOMATION
TOOL CONFIGURATION
OBSOLETE
DUPLICATE
TEMPORARY
```

Each item should have:

```text
source
purpose
scope
dependencies
owner
destination
status
validation method
```

---

# 10. Migration Manifest

Example:

```yaml
migration:
  project: medicoder

items:

  - source: CLAUDE.md
    section: architecture
    classification: project
    destination: projects/medicoder/architecture.md
    status: migrated

  - source: CLAUDE.md
    section: general_coding
    classification: global
    destination: skills/coding/SKILL.md
    status: migrated

  - source: .cursor/rules/optimization.mdc
    classification: reusable_skill
    destination: skills/optimization/SKILL.md
    status: pending

  - source: .cursor/rules/backend.mdc
    classification: project
    destination: projects/medicoder/skills/backend/SKILL.md
    status: migrated

  - source: hooks/test_after_edit.sh
    classification: verification
    destination: project.yaml
    status: pending
```

---

# 11. Semantic Translation

Do not perform:

```text
old file → new file
```

mechanically.

Perform:

```text
old instruction
      ↓
understand intent
      ↓
determine scope
      ↓
determine ownership
      ↓
translate into new architecture
```

---

# 12. Example: Global Rule

Existing:

```text
Before modifying code, inspect existing implementation and tests.
```

Possible destination:

```text
global coding skill
```

because this is broadly useful.

---

# 13. Example: Medicoder Rule

Existing:

```text
This service uses the local inference pipeline and must preserve interface X.
```

Destination:

```text
projects/medicoder/architecture.md
```

because it is project-specific.

---

# 14. Example: Task Rule

Existing:

```text
For this week's experiment compare retrieval variants A/B/C.
```

Destination:

```text
tasks/medicoder/<task-id>/
```

because it should not become permanent project knowledge.

---

# 15. Example: Executor Rule

Existing:

```text
Cursor should inspect all references before changing an interface.
```

Translate into:

```text
General principle:
Before changing an interface, identify relevant callers and references.
```

Then retain any Cursor-specific mechanics in:

```text
executors/cursor/
```

---

# 16. `CLAUDE.md` Migration

A `CLAUDE.md` file may contain several different kinds of knowledge.

Example:

```text
CLAUDE.md
│
├── general coding rules
│       → global
│
├── Medicoder architecture
│       → project
│
├── testing commands
│       → project configuration
│
├── Claude-specific behavior
│       → lead-agent instructions
│
└── temporary task information
        → task
```

Therefore, do not simply move `CLAUDE.md` wholesale.

Parse and classify it.

---

# 17. `AGENTS.md` Migration

Apply the same semantic decomposition.

Possible destinations:

```text
general engineering
    → global

repository architecture
    → project

directory-specific rules
    → project

executor behavior
    → executor

temporary work
    → task
```

---

# 18. Cursor Rules Migration

Inspect every:

```text
.cursor/rules/*.mdc
```

For each rule record:

```text
purpose
scope
activation conditions
dependencies
project-specific assumptions
agent-specific assumptions
reusability
current validity
```

A reusable methodology can become a skill.

A purely Cursor-specific instruction stays with Cursor.

---

# 19. Skill Migration

Existing `SKILL.md` files are high-value accumulated knowledge.

For every skill:

```text
read
understand
classify
normalize
preserve
validate
```

Potential destinations:

```text
~/ai-orchestrator/skills/<skill>/SKILL.md
```

or:

```text
~/ai-orchestrator/projects/medicoder/skills/<skill>/SKILL.md
```

---

# 20. Skill Design

A skill should contain **methodology**, not a particular task.

Good:

```text
optimization skill
```

Bad:

```text
optimize retrieval on 2026-09-19
```

The first is reusable.

The second belongs to a task.

---

# 21. Hooks

Every existing hook should be classified.

Potential categories:

```text
validation
safety
formatting
testing
context
automation
notification
agent-specific
temporary workaround
repository infrastructure
```

Do not centralize hooks merely for centralization's sake.

---

# 22. Repository Hooks

Some hooks should remain in the actual repository:

```text
Git hooks
CI scripts
build hooks
application lifecycle hooks
formatting infrastructure
```

The orchestrator should call or respect them where appropriate rather than duplicating their logic.

---

# 23. Verification Policies

An existing hook such as:

```text
run tests after modifications
```

may become:

```text
global policy:
significant changes require relevant verification
```

with project-specific commands stored separately.

---

# 24. MCP Migration

For every MCP/tool integration determine:

```text
capability
agent
scope
credentials
data access
security implications
project dependency
whether Claude needs it
whether Cursor needs it
whether Gemini needs it
```

Do not expose every capability to every agent.

---

# 25. Prompt Migration

Treat prompts as source code.

For every prompt:

```text
purpose
inputs
outputs
dependencies
agent
scope
reusability
current validity
```

Global prompts:

```text
~/ai-orchestrator/prompts/
```

Medicoder prompts:

```text
~/ai-orchestrator/projects/medicoder/prompts/
```

Task prompts:

```text
~/ai-orchestrator/tasks/medicoder/<task-id>/
```

---

# 26. Workflow Migration

Existing workflows should become reusable skills when appropriate.

Example:

```text
baseline
→ profile
→ identify bottleneck
→ formulate hypothesis
→ modify
→ test
→ benchmark
→ compare
→ accept/reject
→ record result
```

This becomes:

```text
optimization/SKILL.md
```

rather than remaining a one-off prompt.

---

# 27. Permanent Filesystem

Target structure:

```text
~/ai-orchestrator/
│
├── README.md
├── pyproject.toml
├── .gitignore
├── .env
│
├── orchestrator/
│   ├── __init__.py
│   ├── main.py
│   ├── cli.py
│   ├── loop.py
│   ├── state_machine.py
│   ├── context.py
│   ├── registry.py
│   ├── planner.py
│   ├── evaluator.py
│   ├── safety.py
│   └── logging.py
│
├── agents/
│   ├── base.py
│   ├── claude.py
│   ├── cursor.py
│   └── gemini.py
│
├── executors/
│   ├── base.py
│   ├── cursor_executor.py
│   ├── gemini_executor.py
│   ├── python_executor.py
│   └── shell_executor.py
│
├── prompts/
│   ├── lead/
│   ├── coding/
│   ├── review/
│   └── experiment/
│
├── skills/
│   ├── coding/
│   ├── debugging/
│   ├── testing/
│   ├── optimization/
│   ├── experimentation/
│   ├── research/
│   ├── benchmarking/
│   └── code-review/
│
├── projects/
│   ├── medicoder/
│   │   ├── project.yaml
│   │   ├── context.md
│   │   ├── architecture.md
│   │   ├── conventions.md
│   │   ├── environment.md
│   │   ├── decisions.md
│   │   ├── known_issues.md
│   │   ├── testing.md
│   │   ├── security.md
│   │   ├── prompts/
│   │   ├── skills/
│   │   └── executor_rules/
│   │
│   └── future-project/
│
├── tasks/
│   └── medicoder/
│
├── state/
├── artifacts/
├── logs/
├── config/
└── migration/
    └── medicoder/
```

---

# 28. Medicoder Project Context

The Medicoder project should eventually contain:

```text
project.yaml
context.md
architecture.md
conventions.md
environment.md
decisions.md
known_issues.md
testing.md
security.md
```

## `context.md`

High-level project understanding.

## `architecture.md`

Technical architecture.

## `conventions.md`

Coding/development conventions.

## `environment.md`

Development environment and commands.

## `decisions.md`

Important architectural decisions.

## `known_issues.md`

Known problems and limitations.

## `testing.md`

Test commands and verification strategy.

## `security.md`

Project-specific security constraints.

---

# 29. Project Registry

Example:

```yaml
projects:

  medicoder:
    path: ~/work/medicoder

    agents:
      lead: claude
      coding: cursor
      secondary: gemini

    defaults:
      max_iterations: 10
      max_runtime_minutes: 60

    git:
      automatic_commit: false
      automatic_push: false
      automatic_merge: false
```

The actual repository path should be configured during setup rather than hard-coded into the architecture.

---

# 30. Task Model

Example:

```bash
ai-orch start medicoder \
  --goal "Optimize ICD-10 retrieval latency"
```

Creates:

```text
tasks/medicoder/<task-id>/
├── task.yaml
├── objective.md
├── state.json
├── plan.json
├── context_snapshot.json
├── iterations/
├── results/
├── experiments/
├── artifacts/
├── logs/
└── final_report.md
```

---

# 31. Task Lifecycle

```text
USER OBJECTIVE
      │
      ▼
LOAD PROJECT
      │
      ▼
LOAD RELEVANT KNOWLEDGE
      │
      ▼
CLAUDE ANALYSIS
      │
      ▼
CLAUDE DECISION
      │
      ▼
SELECT EXECUTOR
      │
      ▼
EXECUTOR ACTION
      │
      ▼
STRUCTURED RESULT
      │
      ▼
CLAUDE REVIEW
      │
      ├───────────────┐
      │               │
      ▼               ▼
ITERATE            COMPLETE
      │               │
      └──────┐        ▼
             │      SUMMARY
             │
             ▼
          NEXT ACTION
```

---

# 32. Claude Decision Model

Claude should not return only free-form prose to the orchestrator.

Use structured decisions.

Example:

```json
{
  "action": "DELEGATE",
  "executor": "cursor",
  "objective": "Implement retrieval caching",
  "instructions": [
    "Inspect the current retrieval implementation.",
    "Preserve existing public interfaces.",
    "Add tests for cache hits and misses."
  ],
  "success_criteria": [
    "All relevant tests pass",
    "No API regression",
    "Measured latency improves"
  ],
  "verification": [
    "pytest",
    "benchmark"
  ]
}
```

Possible actions:

```text
DELEGATE
DONE
ABORT
REQUEST_HUMAN
```

---

# 33. Why Claude Must Own the Decision Loop

The system should not work like:

```text
Claude generates prompt
→ Cursor executes
→ done
```

It should work like:

```text
Claude
  ↓
decides
  ↓
executor
  ↓
result
  ↓
Claude interprets result
  ↓
decides again
  ↓
executor
  ↓
...
```

This feedback loop is the central feature.

---

# 34. Executor Result Schema

Executors should return structured results.

Example:

```json
{
  "status": "SUCCESS",

  "summary": "Implemented retrieval cache.",

  "files_changed": [
    "src/retrieval/cache.py",
    "tests/test_cache.py"
  ],

  "tests": {
    "passed": 42,
    "failed": 0,
    "skipped": 1
  },

  "metrics": {
    "baseline_latency_ms": 830,
    "new_latency_ms": 510
  },

  "errors": [],

  "artifacts": [
    "results/benchmark.json"
  ]
}
```

Possible statuses:

```text
SUCCESS
PARTIAL
FAILED
BLOCKED
TIMEOUT
CANCELLED
```

---

# 35. Context Management

Claude should **not** receive everything every iteration.

Avoid:

```text
entire repository
+
all logs
+
all previous prompts
+
all terminal output
```

Instead provide:

```text
user objective
+
project context
+
relevant skills
+
current task state
+
latest executor result
+
relevant evidence
```

Large logs should remain local and be summarized or selectively retrieved.

---

# 36. Context Hierarchy

The lead agent's context should be assembled approximately as:

```text
1. System-level orchestration rules
2. Safety policies
3. Global engineering rules
4. Project context
5. Relevant project skills
6. Task objective
7. Task constraints
8. Current state
9. Relevant historical decisions
10. Latest executor result
11. Relevant artifacts
```

Do not automatically load unrelated project knowledge.

---

# 37. Skill Selection

Skills should be selected dynamically.

Example:

```text
Task:
"Optimize inference latency."

Load:

optimization
profiling
benchmarking
testing
Medicoder inference context
```

For:

```text
"Implement a new API endpoint."

Load:

coding
backend
testing
Medicoder API context
```

This reduces unnecessary context consumption.

---

# 38. Persistent Knowledge Updates

The system should eventually allow Claude to propose updates to:

```text
architecture.md
decisions.md
known_issues.md
conventions.md
```

But these updates should not happen blindly.

Example:

```text
Claude:
"Discovered an important architecture constraint."

        ↓

proposed knowledge update

        ↓

validate

        ↓

persist
```

Task-specific observations should not automatically become permanent truths.

---

# 39. Knowledge Promotion

Use a promotion model:

```text
TASK OBSERVATION
       ↓
candidate knowledge
       ↓
validated?
       │
   ┌───┴───┐
   │       │
  no      yes
   │       │
discard   promote
           │
     project knowledge
```

For reusable methodology:

```text
project/task knowledge
        ↓
generalized
        ↓
global skill
```

---

# 40. GitHub Philosophy

The company GitHub repository should look exactly like normal developer work.

The desired flow is:

```text
User
 ↓
Claude
 ↓
Cursor/Gemini/Python
 ↓
existing local working tree
 ↓
User reviews
 ↓
User commits
 ↓
User pushes
 ↓
GitHub
```

Do not create:

```text
AI branches
AI pull requests
AI merge commits
AI orchestration branches
```

unless explicitly requested later.

---

# 41. No Automatic Git Push

Version 1 must not automatically execute:

```text
git push
```

The orchestrator can inspect:

```text
git status
git diff
git diff --stat
git log
```

but GitHub publication remains human-controlled.

---

# 42. No Automatic Commit

Version 1 should leave changes in the working tree.

At completion:

```text
Task complete.

Files modified:
...

Tests:
...

Metrics:
...

GitHub:
NO ACTION TAKEN.
```

Then the user decides what to commit.

---

# 43. Existing User Changes

Before every task:

```bash
git status --short
```

Record the baseline.

If pre-existing changes exist:

```text
warn user
record baseline
avoid assuming every diff belongs to the current task
```

The orchestrator must not accidentally overwrite unrelated work.

---

# 44. Git Diff Attribution

Eventually the system should track:

```text
baseline diff
+
task-generated diff
```

so the user can distinguish:

```text
existing work
```

from:

```text
AI-generated changes
```

without creating a separate Git branch.

---

# 45. Safety Gates

Require explicit human approval for:

```text
git push
git merge
deployment
production changes
credential changes
secret changes
database migrations
destructive commands
external communication
irreversible data operations
```

---

# 46. Read-Only Mode

Support:

```bash
ai-orch start medicoder \
  --goal "Analyze the inference architecture" \
  --read-only
```

Allowed:

```text
read
search
inspect
test
benchmark
analyze
```

Not allowed:

```text
modify
commit
push
deploy
```

---

# 47. Dry-Run Mode

Support:

```bash
ai-orch start medicoder \
  --goal "Optimize inference" \
  --dry-run
```

Claude should generate:

```text
objective interpretation
planned approach
expected changes
expected verification
executor selection
```

without modifying the repository.

---

# 48. Controlled Write Mode

Normal autonomous mode:

```text
read
modify
test
benchmark
iterate
```

but still:

```text
no push
no merge
no deployment
```

---

# 49. Security Model

"Local orchestrator" does **not** automatically mean all data stays on the Mac.

The architecture may still send information to:

```text
Claude API
Cursor services
Gemini services
MCP services
other external tooling
```

Therefore, before production use:

1. inspect Medicoder policy
2. determine approved AI providers
3. determine what source code may leave the machine
4. determine whether datasets may leave the machine
5. avoid secrets
6. avoid patient/production data
7. use synthetic data where possible
8. configure credentials safely
9. log external tool usage where useful

Security policy takes precedence over architectural convenience.

---

# 50. Secrets

Never store:

```text
API keys
tokens
passwords
private credentials
production secrets
```

inside:

```text
project context
task logs
prompts
Git
artifacts
executor results
```

Use:

```text
.env
macOS Keychain
provider-native credential storage
```

where appropriate.

---

# 51. Local Storage

Orchestrator state should remain outside the company repository:

```text
~/ai-orchestrator/
```

The company repository remains:

```text
~/work/medicoder/
```

The orchestrator should reference it.

Do not pollute the company repo with:

```text
AI logs
task state
agent transcripts
experiment orchestration state
migration state
```

unless explicitly desired.

---

# 52. Agent Adapters

The architecture should separate:

```text
AGENT
```

from:

```text
EXECUTOR
```

Conceptually:

```text
LeadAgent
Executor
Skill
Project
Task
```

Claude is an implementation of:

```text
LeadAgent
```

Cursor/Gemini are implementations of:

```text
Executor
```

This prevents the whole system from becoming hard-coded to one provider.

---

# 53. Executor Interface

Conceptually:

```python
class Executor:
    def execute(self, instruction, context) -> ExecutorResult:
        ...
```

Potential implementations:

```text
CursorExecutor
GeminiExecutor
PythonExecutor
ShellExecutor
FutureExecutor
```

The exact interface should be determined during implementation.

---

# 54. Why Cursor Is the Primary Coding Executor

Cursor should be the default implementation executor because its role is:

```text
Claude decides what
        ↓
Cursor figures out how to edit the repository
        ↓
Cursor runs implementation/test loop
        ↓
structured result
        ↓
Claude decides what next
```

This keeps expensive reasoning at the highest layer while using a capable coding agent for high-volume implementation.

---

# 55. Why Gemini Is Secondary

Gemini/Antigravity can be valuable for:

```text
exploration
experiments
alternative implementations
independent investigation
browser-heavy workflows
parallel tasks
lower-cost execution
```

But it should not silently become the source of truth.

Claude interprets its output.

---

# 56. Example: Feature Development

User:

```text
Implement ICD-10 hierarchy retrieval.
```

System:

```text
Claude:
Understand existing architecture.
Identify constraints.
Design implementation.
Define success criteria.

↓

Cursor:
Inspect retrieval code.
Implement hierarchy retrieval.
Add tests.
Run tests.

↓

Result:
Tests pass.
Implementation complete.

↓

Claude:
Review changes.
Identify missing benchmark.

↓

Python:
Run retrieval benchmark.

↓

Result:
Latency +12%.

↓

Claude:
Reject implementation.
Determine bottleneck.
Give Cursor revised strategy.

↓

Cursor:
Optimize implementation.

↓

Python:
Benchmark again.

↓

Claude:
Compare results.
Accept if criteria satisfied.
```

---

# 57. Example: Debugging

User:

```text
Investigate why coding accuracy dropped.
```

Claude:

```text
form hypothesis
```

Then:

```text
Python:
analyze historical metrics

Cursor:
inspect recent code changes

Gemini:
independent investigation

Python:
compare datasets/results

Claude:
synthesize evidence
```

Claude then determines the next experiment.

---

# 58. Example: Research

User:

```text
Investigate whether retrieval strategy X improves coding accuracy.
```

Claude:

```text
define hypothesis
define experiment
define metrics
define controls
```

Python:

```text
prepare evaluation
```

Gemini:

```text
explore alternative implementation
```

Cursor:

```text
implement controlled candidate
```

Python:

```text
run benchmark
```

Claude:

```text
interpret result
```

---

# 59. Baselines

Optimization and research tasks should establish baselines whenever meaningful.

Record:

```text
baseline commit/state
configuration
dataset
model
parameters
metrics
environment
timestamp
```

Then compare:

```text
baseline
vs
candidate
```

---

# 60. Success Criteria

Claude should define measurable success criteria when possible.

Example:

```text
accuracy >= baseline
latency <= baseline
memory <= baseline
all tests pass
no API regression
```

Do not declare success simply because an executor reports:

```text
"implemented successfully"
```

---

# 61. Verification

Verification should be layered:

```text
syntax
 ↓
unit tests
 ↓
integration tests
 ↓
benchmark
 ↓
task-specific metric
 ↓
Claude review
```

Not every task requires every layer.

Claude chooses relevant verification.

---

# 62. Executor Failure

Example:

```text
Cursor
 ↓
FAILED
 ↓
structured error
 ↓
Claude diagnoses
 ↓
retry / different approach / different executor / human
```

Do not blindly retry the exact same action indefinitely.

---

# 63. Iteration Limits

Configure:

```yaml
max_iterations: 10
max_runtime_minutes: 60
max_executor_retries: 2
```

When limits are reached:

```text
REQUEST_HUMAN
```

with:

```text
what happened
what was attempted
what failed
what remains
recommended next investigation
```

---

# 64. Timeouts

Every external executor call should have a timeout.

Handle:

```text
timeout
API failure
process crash
network failure
invalid output
partial output
```

without corrupting task state.

---

# 65. Structured State

Use durable state rather than relying on terminal history.

Example:

```json
{
  "task_id": "...",
  "status": "RUNNING",
  "iteration": 4,
  "objective": "...",
  "last_executor": "cursor",
  "last_result": "...",
  "next_action": "benchmark",
  "started_at": "...",
  "updated_at": "..."
}
```

---

# 66. Resume

Support:

```bash
ai-orch task resume medicoder <task-id>
```

after:

```text
terminal closure
Mac restart
API failure
executor failure
manual interruption
```

---

# 67. Cancellation

Support:

```bash
ai-orch task cancel medicoder <task-id>
```

Cancellation should preserve:

```text
state
logs
diff
artifacts
results
```

so the work can be inspected later.

---

# 68. Experiment Tracking

For meaningful experiments record:

```text
experiment ID
task ID
timestamp
code state
configuration
dataset
model
parameters
baseline
candidate
metrics
result
artifacts
```

---

# 69. Artifact Handling

Artifacts may include:

```text
benchmark JSON
CSV
plots
model outputs
logs
reports
patches
test reports
```

Keep orchestration artifacts outside the company repository unless explicitly required.

---

# 70. Logging

Maintain separate logs for:

```text
orchestrator
Claude decisions
executor actions
executor outputs
verification
experiments
errors
security events
```

Do not blindly log sensitive payloads.

---

# 71. Auditability

For every task it should eventually be possible to answer:

```text
What did the user ask?

What did Claude decide?

Why was Cursor selected?

What did Cursor change?

What tests ran?

What were the results?

What did Claude conclude?

How many iterations occurred?

What files changed?

What metrics changed?

What remains unresolved?
```

This is especially important for autonomous iteration.

---

# 72. Context Compression

Long executor output should not be repeatedly injected into Claude.

Use:

```text
raw log
   ↓
structured extraction
   ↓
summary
   ↓
Claude context
```

Keep raw evidence locally available.

---

# 73. Agent Communication

Agents should communicate through structured artifacts rather than giant conversational transcripts.

Example:

```text
Claude decision
       ↓
task_request.json
       ↓
Cursor
       ↓
executor_result.json
       ↓
Claude
```

This makes the system:

- debuggable
- resumable
- provider-independent
- cheaper
- easier to validate

---

# 74. No Hidden State in GitHub

The orchestrator should not depend on:

```text
GitHub comments
PR descriptions
AI branches
issue comments
commit messages
```

for its internal state.

Its state is local.

GitHub is the normal code-hosting system.

---

# 75. Parallelism

Do not begin with parallel worktrees.

Version 1 should be:

```text
one task
one working tree
one active executor
sequential iteration
```

After this is reliable, introduce:

```text
parallel experiments
isolated worktrees
multiple executors
```

---

# 76. Future Parallel Architecture

Eventually:

```text
Claude
  │
  ├── Cursor → worktree A
  ├── Gemini → worktree B
  ├── Python → benchmark
  └── Research → worktree C
          │
          ▼
       Claude
       compare
          │
          ▼
     choose direction
```

But this is explicitly **not V1**.

---

# 77. Project Independence

The system must not be Medicoder-specific.

Adding a new project should look like:

```bash
ai-orch project add project-name ~/work/project-name
```

Then:

```bash
ai-orch start project-name \
  --goal "Investigate performance bottleneck"
```

No orchestrator rewrite should be necessary.

---

# 78. Global Skills

Potential global skills:

```text
coding
debugging
testing
optimization
benchmarking
research
experimentation
code-review
refactoring
performance-analysis
data-analysis
documentation
```

Only create skills when they represent reusable methodology.

---

# 79. Medicoder Skills

Potential examples:

```text
Medicoder retrieval
Medicoder LLM evaluation
Medicoder coding pipeline
Medicoder inference
Medicoder deployment
Medicoder privacy/on-prem
```

These should be derived from actual repository knowledge rather than invented ahead of inspection.

---

# 80. CLI

Eventually:

```bash
ai-orch project list
```

```bash
ai-orch project add medicoder ~/work/medicoder
```

```bash
ai-orch project inspect medicoder
```

```bash
ai-orch start medicoder --goal "..."
```

```bash
ai-orch task list medicoder
```

```bash
ai-orch task status medicoder <task-id>
```

```bash
ai-orch task resume medicoder <task-id>
```

```bash
ai-orch task cancel medicoder <task-id>
```

```bash
ai-orch inspect medicoder
```

```bash
ai-orch diff medicoder
```

---

# 81. Technology Stack

Initial implementation:

```text
Python
Anthropic SDK
Pydantic
PyYAML
python-dotenv
Git
JSON/JSONL
```

Executor integrations:

```text
Claude
Cursor
Gemini/Antigravity
Python
Shell
```

Later if necessary:

```text
SQLite
FastAPI
TUI
web UI
job queue
parallel worktrees
```

Do not introduce a database or web UI prematurely.

---

# 82. Recommended Build Strategy

The system should be built in stages.

Do not attempt:

```text
full autonomous multi-agent platform
```

on day one.

Instead:

```text
migration
 ↓
project context
 ↓
Claude lead
 ↓
Cursor executor
 ↓
structured result
 ↓
single feedback loop
 ↓
verification
 ↓
state persistence
 ↓
Gemini
 ↓
experiments
 ↓
advanced features
```

---

# 83. Phase 0 — Migration

### Objective

Understand and preserve existing Medicoder AI knowledge.

### Steps

```text
1. Locate Medicoder repository.
2. Inventory AI-related configuration.
3. Snapshot originals.
4. Read every relevant rule.
5. Read every relevant skill.
6. Inspect hooks.
7. Inspect MCP configuration.
8. Inspect prompts.
9. Inspect project conventions.
10. Inspect workflow documentation.
11. Classify everything.
12. Build migration manifest.
13. Create global knowledge.
14. Create Medicoder knowledge.
15. Create executor-specific knowledge.
16. Preserve legacy configuration.
17. Validate.
```

### Primary agent

**Claude**

### Supporting implementation agent

**Cursor**

### Deterministic support

**Python**

---

# 84. Phase 0A — Repository Discovery

Claude should first inspect:

```text
directory tree
README
CLAUDE.md
AGENTS.md
.cursor/
skills/
scripts/
hooks/
MCP config
test config
build config
CI
environment docs
```

No modification initially.

Output:

```text
migration/inventory.md
```

---

# 85. Phase 0B — Knowledge Classification

For each item:

```text
What does it mean?
Why does it exist?
Who needs it?
How often does it apply?
Is it still valid?
Can it be generalized?
```

Claude owns this reasoning.

---

# 86. Phase 0C — Migration Implementation

Cursor performs the mechanical creation/editing of:

```text
~/ai-orchestrator/projects/medicoder/
~/ai-orchestrator/skills/
~/ai-orchestrator/prompts/
~/ai-orchestrator/migration/
```

Claude reviews the resulting structure.

---

# 87. Phase 0D — Migration Validation

Validate:

```text
No important instruction disappeared.
No project-specific rule became global accidentally.
No temporary instruction became permanent accidentally.
No executor-specific rule became a universal requirement.
No skill lost important procedure.
No security restriction disappeared.
```

---

# 88. Phase 1 — Orchestrator Skeleton

Create:

```text
~/ai-orchestrator/
```

Implement:

```text
CLI
project registry
config loading
logging
basic state
```

No autonomy yet.

---

# 89. Phase 2 — Claude Lead

Implement:

```text
Claude client
lead prompt
context builder
structured decision parser
```

Test:

```text
objective
→ Claude
→ valid structured decision
```

---

# 90. Phase 3 — Cursor Executor

Implement:

```text
Cursor executor adapter
```

Capabilities:

```text
read
modify
test
```

Restrictions:

```text
no push
no merge
no deployment
```

---

# 91. Phase 4 — Structured Results

Implement:

```text
ExecutorResult
```

Normalize:

```text
status
summary
files
tests
metrics
errors
artifacts
```

---

# 92. Phase 5 — First Feedback Loop

Implement:

```text
Claude
 ↓
Cursor
 ↓
result
 ↓
Claude
```

Initially cap at:

```text
2–3 iterations
```

---

# 93. Phase 6 — Verification

Add:

```text
Git baseline
test execution
diff inspection
task success criteria
```

---

# 94. Phase 7 — Persistent State

Implement:

```text
task.yaml
state.json
iteration records
logs
artifacts
```

---

# 95. Phase 8 — Safety

Implement:

```text
read-only
dry-run
timeouts
iteration limits
human approval
secret protection
Git safety
```

---

# 96. Phase 9 — Deterministic Workers

Add:

```text
Python executor
benchmarking
metric comparison
artifact processing
```

---

# 97. Phase 10 — Gemini/Antigravity

Add secondary executor.

Use it initially for:

```text
exploration
alternative implementation
experiments
independent analysis
```

Do not make it part of every task.

Claude decides when it is useful.

---

# 98. Phase 11 — Skills

Migrate existing reusable skills.

Then add:

```text
coding
debugging
optimization
testing
research
benchmarking
```

only where useful.

---

# 99. Phase 12 — Experiment System

Add:

```text
experiment IDs
baselines
metrics
artifacts
comparisons
reproducibility
```

---

# 100. Phase 13 — Durable Knowledge

Allow validated discoveries to update:

```text
decisions.md
known_issues.md
architecture.md
conventions.md
```

with controlled promotion.

---

# 101. Phase 14 — Background Tasks

Eventually support:

```bash
ai-orch start medicoder --goal "..." --background
```

with:

```text
resume
status
cancel
logs
```

---

# 102. Phase 15 — Parallelism

Only after sequential execution is reliable.

Introduce:

```text
worktrees
parallel experiments
executor competition
```

---

# 103. Phase 16 — Optional UI

Only if CLI becomes insufficient.

Possible:

```text
TUI
web dashboard
task monitor
experiment dashboard
```

---

# 104. First Test

Use read-only:

```bash
ai-orch start medicoder \
  --goal "Analyze the repository architecture and identify the main inference pipeline" \
  --read-only
```

Expected:

```text
Claude loads project context
Claude understands repository
Claude produces structured plan
No files modified
```

---

# 105. Second Test

```text
Run the existing test suite and summarize failures.
```

Expected:

```text
Claude
→ Cursor/Python
→ tests
→ structured results
→ Claude summary
```

---

# 106. Third Test

Small safe change:

```text
Add a unit test for an existing function.
```

Expected:

```text
Claude
→ Cursor
→ test added
→ tests run
→ Claude reviews
→ working tree modified
→ no commit
```

---

# 107. Fourth Test

Real iterative task:

```text
Optimize X while preserving Y.
```

Expected:

```text
Claude defines baseline
↓
Cursor modifies implementation
↓
Python benchmarks
↓
Claude evaluates
↓
Cursor iterates
↓
Python benchmarks
↓
Claude decides
↓
DONE
```

---

# 108. Fifth Test — Gemini

Give Gemini an intentionally secondary task:

```text
Explore an alternative implementation strategy for X.
Do not modify the main working tree.
Return findings.
```

Claude evaluates the findings.

---

# 109. Sixth Test — Failure Recovery

Intentionally cause:

```text
test failure
```

Expected:

```text
Cursor failure
↓
structured result
↓
Claude diagnoses
↓
new strategy
↓
Cursor retry
```

---

# 110. Seventh Test — Resume

Interrupt a task.

Then:

```bash
ai-orch task resume medicoder <task-id>
```

Expected:

```text
state restored
iteration history restored
context reconstructed
task continues
```

---

# 111. Definition of Done — Migration

Migration is complete when:

- [ ] Existing AI configuration inventoried.
- [ ] Original files preserved.
- [ ] Every important rule classified.
- [ ] Existing skills inventoried.
- [ ] Existing skills migrated or intentionally retained.
- [ ] Hooks classified.
- [ ] MCP integrations classified.
- [ ] Prompts classified.
- [ ] Global knowledge separated from Medicoder knowledge.
- [ ] Task-specific knowledge not accidentally promoted.
- [ ] Executor-specific knowledge separated.
- [ ] Security requirements preserved.
- [ ] Migration manifest complete.
- [ ] New Medicoder project context exists.
- [ ] Migrated behavior validated.
- [ ] Legacy configuration still recoverable.
- [ ] Nothing important silently disappeared.

---

# 112. Definition of Done — Orchestrator V1

V1 is complete when:

```bash
ai-orch start medicoder \
  --goal "Perform a useful engineering task"
```

can:

```text
1. Load Medicoder project context.
2. Load relevant global knowledge.
3. Load relevant Medicoder skills.
4. Create a persistent task.
5. Ask Claude to reason about the task.
6. Generate a structured decision.
7. Delegate implementation to Cursor.
8. Receive structured results.
9. Feed results back to Claude.
10. Iterate.
11. Run appropriate tests.
12. Run appropriate benchmarks.
13. Evaluate success criteria.
14. Stop when complete.
15. Persist state.
16. Produce a final report.
17. Leave changes in the local working tree.
18. Take no automatic GitHub action.
```

---

# 113. Definition of Done — Generality

The orchestrator must then support:

```bash
ai-orch start medicoder \
  --goal "Implement a new feature"
```

```bash
ai-orch start medicoder \
  --goal "Investigate a bug"
```

```bash
ai-orch start medicoder \
  --goal "Optimize inference latency"
```

```bash
ai-orch start medicoder \
  --goal "Evaluate a new model"
```

without modifying the orchestrator itself.

A future project should work with:

```bash
ai-orch project add another-project ~/work/another-project
```

and:

```bash
ai-orch start another-project \
  --goal "Investigate performance"
```

---

# 114. Failure Modes to Explicitly Avoid

## Failure mode 1 — Building a one-off Medicoder script

Wrong:

```text
medicoder_optimizer.py
```

Right:

```text
general orchestrator
+
Medicoder project context
+
temporary task
```

---

## Failure mode 2 — Copying everything globally

Wrong:

```text
all Medicoder rules
→ global rules
```

This contaminates future projects.

Correct:

```text
general
→ global

Medicoder
→ project

task
→ task

Cursor
→ executor
```

---

## Failure mode 3 — Treating Claude/Cursor/Gemini equally

Wrong:

```text
three agents independently doing everything
```

Correct:

```text
Claude = reasoning/control
Cursor = implementation
Gemini = secondary execution
Python = deterministic
```

---

## Failure mode 4 — Letting executors make architectural decisions

Executors can propose ideas.

Claude owns the final strategy.

---

## Failure mode 5 — Dumping everything into Claude context

Use selective retrieval.

---

## Failure mode 6 — Autonomous GitHub activity

Do not allow automatic:

```text
push
merge
PR
```

in V1.

---

## Failure mode 7 — Overengineering parallelism

Start sequentially.

---

## Failure mode 8 — Deleting old configuration too early

Preserve it until migration is validated.

---

## Failure mode 9 — Treating every experiment as production code

Experiments should be isolated and measured.

---

## Failure mode 10 — Treating every task observation as permanent knowledge

Use controlled knowledge promotion.

---

# 115. Ideal Long-Term Workflow

A typical task should eventually look like:

```text
USER
 │
 │ "Improve ICD-10 coding accuracy without increasing latency."
 ▼
CLAUDE
 │
 │ Understand objective
 │ Load Medicoder context
 │ Load relevant skills
 │ Establish constraints
 │
 ▼
CLAUDE
 │
 │ Design experiment
 ▼
PYTHON
 │
 │ Establish baseline
 ▼
CLAUDE
 │
 │ Decide implementation
 ▼
CURSOR
 │
 │ Implement candidate
 ▼
PYTHON
 │
 │ Run evaluation
 ▼
CLAUDE
 │
 │ Analyze result
 │
 ├───────────────┐
 │               │
 │ insufficient  │ successful
 ▼               ▼
CURSOR          CLAUDE
 │               │
iterate          DONE
 │
 ▼
PYTHON
 │
benchmark
 │
 ▼
CLAUDE
```

The important point is that **Claude controls the loop**.

---

# 116. Final Architecture

```text
                         USER
                           │
                           ▼
                  ┌─────────────────┐
                  │     CLAUDE      │
                  │                 │
                  │  Lead Engineer  │
                  │  Researcher     │
                  │  Architect      │
                  │  Reviewer       │
                  │  Decision Maker │
                  └────────┬────────┘
                           │
                structured decision
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌───────────┐
        │  CURSOR  │ │  GEMINI  │ │  PYTHON   │
        │          │ │          │ │           │
        │ coding   │ │secondary │ │deterministic
        │ testing  │ │execution │ │analysis   │
        │ debugging│ │experiments│ │benchmarks │
        └────┬─────┘ └────┬─────┘ └─────┬─────┘
             │            │              │
             └────────────┼──────────────┘
                          ▼
                  LOCAL PROJECT
                          │
                    structured results
                          │
                          ▼
                       CLAUDE
                          │
                 review / next decision
                          │
                       iterate
                          │
                         ...
                          │
                          ▼
                        USER
                          │
                    manual Git review
                          │
                          ▼
                       GITHUB
```

---

# 117. Final Mental Model

The system should be understood as a **personal AI engineering operating environment**.

```text
ORCHESTRATOR
    │
    ├── GLOBAL KNOWLEDGE
    │
    ├── GLOBAL SKILLS
    │
    ├── AGENTS
    │
    ├── EXECUTORS
    │
    ├── PROJECTS
    │     │
    │     └── MEDICODER
    │           │
    │           ├── architecture
    │           ├── conventions
    │           ├── decisions
    │           ├── known issues
    │           ├── project skills
    │           └── migrated knowledge
    │
    └── TASKS
          │
          └── temporary objectives
```

The core hierarchy is:

```text
CLAUDE
  ↓
CURSOR
  ↓
GEMINI
```

with deterministic Python wherever possible.

The core persistence model is:

```text
ORCHESTRATOR = permanent
PROJECT      = persistent
TASK         = temporary
SKILL        = reusable
KNOWLEDGE    = persistent and scoped
AGENT        = replaceable
EXECUTOR     = replaceable
WORKTREE     = real
GITHUB       = normal
```

The core feedback loop is:

```text
CLAUDE
  ↓
DECIDE
  ↓
EXECUTE
  ↓
MEASURE
  ↓
REPORT
  ↓
CLAUDE
  ↓
REASON
  ↓
ITERATE
```

And the most important migration principle is:

```text
EXISTING MEDICODER AI WORK
            ↓
       DO NOT DISCARD
            ↓
         INVENTORY
            ↓
         UNDERSTAND
            ↓
          CLASSIFY
            ↓
         TRANSLATE
            ↓
          VALIDATE
            ↓
GLOBAL / PROJECT / TASK / EXECUTOR
            ↓
NEW ORCHESTRATOR
```

The end state is **not** "a new AI setup replacing the old one."

It is:

> **The accumulated Medicoder AI workflow becomes the first project's knowledge base inside a permanent multi-project orchestration system, with Claude providing the highest-level reasoning, Cursor performing most implementation, Gemini providing secondary execution/experimentation, and deterministic local tools handling everything that does not require an LLM.**

---

# 118. Immediate Next Action

Do **not** begin by writing the full orchestrator.

The correct first action is:

```text
PHASE 0
↓
Inspect the actual Medicoder repository.
↓
Inventory all existing AI configuration.
↓
Snapshot it.
↓
Have Claude classify and understand it.
↓
Build the Medicoder project knowledge layer.
↓
Validate the migration.
↓
Only then implement the orchestration engine.
```

The first concrete deliverable should therefore be:

```text
~/ai-orchestrator/migration/medicoder/inventory.md
```

followed by:

```text
~/ai-orchestrator/migration/medicoder/migration.yaml
```

and then:

```text
~/ai-orchestrator/projects/medicoder/
```

The system should **earn its autonomy gradually**:

```text
READ-ONLY
   ↓
ANALYSIS
   ↓
CONTROLLED WRITE
   ↓
TESTED ITERATION
   ↓
AUTONOMOUS LOCAL ITERATION
   ↓
EXPERIMENTATION
   ↓
PARALLELISM
```

This preserves control while allowing the system to eventually perform substantial engineering work autonomously.