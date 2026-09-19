# Local Multi-Agent Engineering & Research Orchestrator
## Exhaustive Implementation Handoff

# THIS WAS ONLY THE INITIAL PLAN. THINGS HAVE CHANGED A LOT SINCE THEN DUE TO UNDERSTANDING MORE ABOUT MY SUBSCRIPTIONS AND WHATNOT. BUT YOU CAN USE CONCEPTS FROM THIS INITIAL IDEATION TO IMPROVE THE CURRENT PROJECT/IMPLEMENTATION.

---

# 0. Core Objective

Build a **permanent, reusable, local-first AI engineering and research orchestration system** on the user's Mac.

The system is **not** a one-feature automation script.

It should be reusable for:

- optimization
- debugging
- new feature development
- refactoring
- architecture design
- research
- experimentation
- benchmarking
- data analysis
- test generation
- test fixing
- documentation
- code review
- performance investigation
- model evaluation
- LLM experimentation
- repetitive engineering work
- future projects and repositories

The orchestrator is installed and configured **once**, then reused indefinitely.

The fundamental abstraction is:

```text
PERMANENT ORCHESTRATOR
        │
        ├── PROJECT A
        │     ├── Task 1
        │     ├── Task 2
        │     └── Task 3
        │
        ├── PROJECT B
        │     ├── Task 1
        │     └── Task 2
        │
        └── FUTURE PROJECTS
              └── ...
```

For the current situation:

```text
Permanent AI Orchestrator
        │
        └── Medicoder
              ├── Existing accumulated agent knowledge
              ├── Optimization task
              ├── New feature task
              ├── Bug investigation
              ├── Model experiment
              └── Future work
```

---

# 1. Critical New Requirement: Migrate Existing Agent Knowledge

The user has already spent several weeks developing an AI-assisted engineering workflow **inside the Medicoder repository**.

That existing work must **not be discarded** when introducing the new orchestration system.

The existing repository may already contain things such as:

- `CLAUDE.md`
- `AGENTS.md`
- Cursor rules
- `.cursor/rules/`
- `SKILL.md` files
- project-specific skills
- hooks
- scripts
- MCP configuration
- prompts
- coding conventions
- testing conventions
- workflow instructions
- architecture guidance
- debugging procedures
- research procedures
- agent-specific instructions
- tool-specific configuration

These should be treated as **existing accumulated knowledge and engineering infrastructure**.

The migration process must:

1. inventory what already exists
2. understand what each item does
3. classify its scope
4. preserve the original
5. translate the useful parts into the new architecture
6. avoid unnecessary duplication
7. distinguish global knowledge from Medicoder-specific knowledge
8. distinguish agent-specific instructions from general engineering rules
9. preserve useful hooks/workflows where appropriate
10. only remove/replace old configuration after the new system has been validated

The new orchestrator should therefore be viewed as **absorbing and organizing the user's existing AI workflow**, not replacing it blindly.

---

# 2. Phase 0 — Existing Agent Configuration Migration

This phase occurs **before implementing the main autonomous orchestration loop**.

The goal is:

```text
Existing Medicoder AI workflow
            ↓
      inventory
            ↓
       understand
            ↓
        classify
            ↓
        translate
            ↓
 New reusable orchestration system
```

Do **not** simply copy the entire `.cursor/` or configuration directory into `~/ai-orchestrator/`.

Different pieces have different scopes and meanings.

---

# 3. Migration Principle

Every existing rule, skill, hook, prompt, or configuration item should be classified into one of these categories:

```text
GLOBAL
PROJECT
TASK
AGENT-SPECIFIC
EXECUTOR-SPECIFIC
HOOK / AUTOMATION
TOOL CONFIGURATION
OBSOLETE / DUPLICATE
```

This classification determines where it belongs in the new system.

---

# 4. Global Knowledge

A rule is **global** if it is useful across essentially all software projects.

Examples:

```text
Always inspect existing code before modifying it.

Run relevant tests after changes.

Prefer minimal changes over unnecessary rewrites.

Never claim tests passed without actually running them.

Do not expose secrets in logs.

Explain assumptions when they materially affect implementation.
```

These should become reusable global instructions or skills.

Possible location:

```text
~/ai-orchestrator/
├── prompts/
└── skills/
```

For example:

```text
skills/
├── coding/
├── debugging/
├── testing/
├── optimization/
└── research/
```

---

# 5. Medicoder-Specific Knowledge

Some rules are only valid because of Medicoder's architecture, business requirements, deployment model, or codebase.

Examples:

```text
This service communicates with component X.

Hospital deployments require Y.

This module must preserve interface Z.

The repository uses a particular inference architecture.

A particular data format must remain compatible.
```

These should **not** become global rules.

They belong under:

```text
~/ai-orchestrator/projects/medicoder/
```

For example:

```text
projects/medicoder/
├── project.yaml
├── context.md
├── architecture.md
├── conventions.md
├── decisions.md
├── known_issues.md
└── skills/
```

---

# 6. Agent-Specific Instructions

Some existing instructions are useful specifically because a particular agent needs them.

For example, an instruction may explain how Cursor should:

- edit files
- inspect code
- use its tools
- format responses
- handle terminal commands
- report changes

That does **not** necessarily belong in Claude's prompt.

Instead, separate:

```text
UNDERLYING INTENT
```

from:

```text
TOOL-SPECIFIC IMPLEMENTATION
```

For example:

```text
Old Cursor rule:
"Before editing, use Cursor's search mechanism to locate all references."

```

could translate conceptually into:

```text
General rule:
"Before modifying an interface, identify relevant references and callers."

```

while the Cursor adapter retains whatever implementation-specific instructions are necessary.

---

# 7. Executor-Specific Instructions

The new architecture should support instructions at multiple levels:

```text
Global
   ↓
Project
   ↓
Task
   ↓
Executor
```

Example:

```text
Global:
Always test changes.

Medicoder:
Use pytest for the Python test suite.

Optimization task:
Latency must not increase.

Cursor:
Implement source changes and run the relevant tests.

Python:
Run the deterministic benchmark.
```

The orchestrator combines these into the correct execution context.

---

# 8. `CLAUDE.md` Migration

If the repository contains:

```text
CLAUDE.md
```

do not simply delete it.

First determine what it contains.

Classify each section.

For example:

```text
CLAUDE.md
│
├── General coding principles
│       → global rule
│
├── Medicoder architecture
│       → project context
│
├── Testing commands
│       → project configuration
│
├── Claude-specific instructions
│       → lead-agent prompt
│
└── Temporary task instructions
        → task-specific information
```

A single `CLAUDE.md` may therefore be split across several locations in the new architecture.

---

# 9. `AGENTS.md` Migration

If the repository contains:

```text
AGENTS.md
```

perform the same classification.

Potential translations:

```text
General engineering guidance
    → global rules

Repository architecture
    → project context

Directory-specific behavior
    → project-specific rules

Agent execution behavior
    → executor instructions

Temporary instructions
    → task instructions
```

Do not assume every line belongs in one new file.

---

# 10. Cursor Rules Migration

If the repository contains:

```text
.cursor/rules/
```

inventory every rule individually.

For example:

```text
.cursor/rules/
├── backend.mdc
├── python.mdc
├── testing.mdc
├── architecture.mdc
└── ...
```

For every rule, determine:

```text
Scope
Purpose
Trigger
Dependencies
Whether it is still valid
Whether it is project-specific
Whether it is agent-specific
Whether it should become a reusable skill
```

A Cursor rule that represents a reusable engineering procedure may become:

```text
skills/<skill-name>/SKILL.md
```

A Cursor rule that only exists to configure Cursor's behavior should remain associated with the Cursor executor.

---

# 11. `SKILL.md` Migration

Existing skills are particularly important because they represent **reusable accumulated expertise**.

Do not discard them.

For each existing `SKILL.md`:

```text
1. Read it.
2. Identify its purpose.
3. Determine scope.
4. Determine dependencies.
5. Determine whether it is generic or Medicoder-specific.
6. Normalize its format if necessary.
7. Preserve useful instructions.
8. Remove obsolete/duplicated content only after validation.
```

Potential destinations:

```text
Global skill:
~/ai-orchestrator/skills/<skill-name>/SKILL.md
```

or:

```text
Medicoder-specific skill:
~/ai-orchestrator/projects/medicoder/skills/<skill-name>/SKILL.md
```

---

# 12. Skills Should Be Reusable

The orchestrator's skill system should make it possible for Claude to use the same skill across different tasks.

For example:

```text
optimization/
```

can support:

```text
Optimize retrieval.
Optimize inference.
Optimize memory.
Optimize latency.
Optimize database queries.
```

The skill contains the methodology.

The task contains the specific objective.

---

# 13. Hooks Migration

Hooks require special treatment.

Do not blindly copy hooks into the orchestrator.

First determine what each hook actually does.

Possible categories:

```text
Validation hook
Safety hook
Formatting hook
Test hook
Context hook
Automation hook
Notification hook
Agent-specific hook
Temporary workaround
```

Then translate accordingly.

---

# 14. Example Hook Translation

Suppose the existing repository has a hook:

```text
After code modification:
run pytest.
```

This could become an orchestrator-level verification policy:

```text
After significant source modifications:
run relevant tests before declaring success.
```

The actual command may remain project-specific:

```yaml
testing:
  command: pytest
```

Thus:

```text
GENERAL POLICY
+
PROJECT COMMAND
=
ORCHESTRATOR VERIFICATION
```

---

# 15. Hooks That Should Remain in the Repository

Some hooks may be fundamentally repository-level and should remain there.

For example:

- Git hooks
- formatting hooks required by the project
- CI-related scripts
- build-system hooks
- application lifecycle hooks

The orchestrator should not absorb them merely because they happen to be used during AI development.

The goal is **correct ownership**, not centralization for its own sake.

---

# 16. MCP Configuration Migration

If the Medicoder workflow already uses MCP servers/tools, inventory them separately.

For each MCP integration determine:

```text
What capability does it provide?
Which agent uses it?
Is it project-specific?
Does it require credentials?
Does it access external data?
Is it safe for company data?
Can the orchestrator invoke it?
Should it remain directly attached to the agent?
```

Possible destinations:

```text
Global tool
Project tool
Claude-only tool
Cursor-only tool
Antigravity-only tool
Explicitly disabled
```

Do not automatically expose every MCP capability to every agent.

---

# 17. Existing Prompts

Existing prompts should be treated like source code.

For each prompt:

```text
What problem does it solve?
What assumptions does it make?
Which agent uses it?
Is it reusable?
Is it project-specific?
Is it still necessary?
```

Good reusable prompts should move into:

```text
~/ai-orchestrator/prompts/
```

Project-specific prompts can move into:

```text
projects/medicoder/prompts/
```

Temporary prompts should remain task-local or be discarded after validation.

---

# 18. Existing Conventions

Existing coding conventions should be separated into:

```text
Engineering convention
Project convention
Agent behavior
Temporary preference
```

Example:

```text
"Use type hints"
```

might be global.

While:

```text
"Use this particular internal module rather than library X"
```

is likely Medicoder-specific.

---

# 19. Existing Workflow Knowledge

The user may already have developed informal procedures such as:

```text
inspect → plan → implement → test → review
```

or:

```text
baseline → modify → benchmark → compare
```

These should become reusable skills.

For example:

```text
skills/optimization/SKILL.md
```

could encode:

```text
1. Establish baseline.
2. Define measurable success criteria.
3. Identify bottleneck.
4. Make controlled change.
5. Run tests.
6. Benchmark.
7. Compare against baseline.
8. Reject regressions.
9. Iterate.
10. Record conclusion.
```

This turns accumulated personal workflow knowledge into reusable infrastructure.

---

# 20. Existing Agent Knowledge Should Be Preserved Before Migration

Before modifying the Medicoder repository's existing AI configuration:

```text
CREATE A LOCAL SNAPSHOT
```

For example:

```text
~/ai-orchestrator/migration/medicoder-original/
```

Store:

```text
original files
original paths
migration notes
classification
translation
validation status
```

Do not delete the originals immediately.

---

# 21. Migration Manifest

Create a migration manifest.

Conceptually:

```yaml
migration:
  source_project: medicoder

items:

  - source: CLAUDE.md
    section: testing
    destination: project_config
    status: migrated

  - source: .cursor/rules/optimization.mdc
    destination: global_skill
    status: pending

  - source: .cursor/rules/backend.mdc
    destination: project_skill
    status: migrated

  - source: hooks/test_after_edit.sh
    destination: orchestrator_verification
    status: pending
```

This provides traceability.

---

# 22. Migration Must Be Lossless Initially

The first migration objective is:

```text
PRESERVE
```

not:

```text
CLEAN EVERYTHING UP
```

The system can be cleaned later.

Initially, it is better to have:

```text
duplicate-but-understood
```

than:

```text
clean-but-missing-important behavior
```

---

# 23. Validation After Migration

After translating existing configuration:

Run the old and new workflow against equivalent tasks where practical.

Compare:

```text
Did the new system preserve important behavior?
Did any important rule disappear?
Did any skill lose information?
Did any hook stop functioning?
Did agent behavior regress?
```

Only after validation should old configuration be considered for removal.

---

# 24. Migration Compatibility Layer

Where practical, support a transition period where the new orchestrator can still reference existing repository instructions.

For example:

```text
New orchestrator
       │
       ├── Global rules
       ├── Medicoder project context
       ├── Migrated skills
       └── Legacy instructions
```

This allows incremental migration instead of requiring a single big-bang conversion.

Eventually:

```text
Legacy instructions
        ↓
fully migrated
        ↓
removed only if appropriate
```

---

# 25. Recommended Migration Directory

During Phase 0:

```text
~/ai-orchestrator/
└── migration/
    └── medicoder/
        ├── inventory.md
        ├── migration.yaml
        ├── original/
        ├── translated/
        ├── validation/
        └── README.md
```

This directory is temporary infrastructure and should remain outside the company repo.

---

# 26. Migration Inventory Checklist

Search the Medicoder repository for at least:

```text
CLAUDE.md
AGENTS.md
.cursor/
.cursor/rules/
skills/
SKILL.md
hooks/
.git/hooks/
.mcp/
mcp.json
*.md
*.mdc
*.json
*.yaml
*.yml
scripts/
```

Also inspect:

```text
package configuration
build configuration
test configuration
formatter configuration
lint configuration
CI configuration
```

Not everything discovered is necessarily AI infrastructure, but the inventory should be broad enough to avoid missing important context.

---

# 27. Do Not Assume File Names

The migration process must not assume that all agent configuration follows a particular convention.

The repository should be inspected first.

Possible examples include:

```text
CLAUDE.md
AGENTS.md
.cursor/
.cursor/rules/
skills/
.ai/
.ai-rules/
hooks/
scripts/
```

The implementation should discover what actually exists rather than assuming a particular structure.

---

# 28. Translation Is Semantic, Not Just File Copying

The goal is **not**:

```text
old_file → same_file_in_new_directory
```

The goal is:

```text
old behavior
     ↓
understand intent
     ↓
determine correct scope
     ↓
express intent in new architecture
```

This is particularly important for rules created specifically for one agent.

---

# 29. Example Semantic Translation

Suppose an existing instruction says:

```text
Before implementing anything, inspect the surrounding code and existing tests.
```

Possible new representation:

```text
Global engineering rule:
Before making a non-trivial change, inspect relevant implementation
and existing tests.
```

This can then be used by:

```text
Claude
Cursor
Antigravity
```

where appropriate.

---

# 30. Example Project Translation

Suppose an existing rule says:

```text
The coding pipeline uses BM25 + embedding retrieval with a local cache.
```

That should become project context:

```text
projects/medicoder/architecture.md
```

Claude can then understand the architecture regardless of which executor performs the implementation.

---

# 31. Example Task Translation

Suppose an existing instruction says:

```text
For this week's optimization experiment, compare three retrieval variants.
```

That should **not** become permanent project knowledge.

It belongs in:

```text
tasks/<task-id>/
```

---

# 32. Example Executor Translation

Suppose a rule says:

```text
Cursor should always run the formatter after editing Python files.
```

This may remain:

```text
Cursor executor policy
```

while the general principle:

```text
Modified code must satisfy project formatting requirements.
```

belongs at the project/global level.

---

# 33. New Architecture After Migration

After Phase 0, the architecture becomes:

```text
                         GLOBAL
                           │
                ┌──────────┴──────────┐
                │                     │
            Global Skills        Global Rules
                │                     │
                └──────────┬──────────┘
                           │
                           ▼
                     ORCHESTRATOR
                           │
              ┌────────────┴────────────┐
              │                         │
           PROJECT                  EXECUTORS
              │                         │
        ┌─────┴─────┐          ┌────────┼────────┐
        │           │          │        │        │
    Medicoder    Project B   Claude   Cursor  Antigravity
        │
   ┌────┴─────┐
   │          │
Context    Project Skills
   │
   └────┬─────┘
        │
      TASK
        │
        ▼
     execution
```

---

# 34. Permanent System Filesystem

After migration, the permanent architecture should look approximately like:

```text
~/ai-orchestrator/
│
├── orchestrator/
│   ├── __init__.py
│   ├── main.py
│   ├── loop.py
│   ├── state_machine.py
│   └── context.py
│
├── agents/
│   ├── claude.py
│   ├── cursor.py
│   └── antigravity.py
│
├── executors/
│   ├── base.py
│   ├── cursor_executor.py
│   ├── antigravity_executor.py
│   └── python_executor.py
│
├── prompts/
│   ├── lead_agent.md
│   ├── coding_agent.md
│   ├── experiment_agent.md
│   └── review_agent.md
│
├── skills/
│   ├── coding/
│   ├── debugging/
│   ├── optimization/
│   ├── experimentation/
│   ├── research/
│   └── testing/
│
├── projects/
│   ├── medicoder/
│   │   ├── project.yaml
│   │   ├── context.md
│   │   ├── architecture.md
│   │   ├── conventions.md
│   │   ├── decisions.md
│   │   ├── known_issues.md
│   │   ├── prompts/
│   │   └── skills/
│   │
│   └── future-project/
│
├── tasks/
│   ├── medicoder/
│   └── future-project/
│
├── state/
├── artifacts/
├── logs/
├── config/
├── migration/
└── .env
```

---

# 35. Core Agent Architecture

### Claude = Lead / Brain / Researcher / Reviewer

Claude is responsible for:

- understanding the user's objective
- understanding project context
- decomposing problems
- deciding what should happen next
- designing implementation approaches
- selecting the appropriate executor
- reviewing executor results
- analyzing experiment results
- identifying failures
- deciding whether another iteration is necessary
- changing strategy
- deciding when the task is complete
- producing the final explanation

Claude should not necessarily perform every low-level action itself.

---

### Cursor = Coding / Implementation Agent

Cursor primarily handles:

- modifying source code
- creating files
- refactoring
- implementing features
- fixing bugs
- writing tests
- running tests
- inspecting compiler/runtime errors
- iterative implementation

---

### Antigravity = Experimentation / Secondary Execution Agent

Antigravity can be used for:

- exploratory coding
- experimentation
- alternative implementations
- browser workflows where appropriate
- parallel investigation
- independent validation

Its exact capabilities should remain configurable because external tooling can evolve.

---

### Python / Deterministic Workers

Use ordinary local scripts for:

- parsing experiment results
- calculating metrics
- comparing benchmarks
- processing datasets
- repeatable evaluations
- generating reports
- aggregating logs
- checking Git state

Do not spend LLM context on deterministic operations.

---

# 36. Three-Layer Data Model

The system has three fundamental levels:

```text
GLOBAL ORCHESTRATOR
        │
        ▼
PROJECT
        │
        ▼
TASK
```

### Global

Reusable forever:

```text
agents
skills
general rules
safety policies
executor adapters
```

### Project

Persistent for a repository:

```text
architecture
conventions
decisions
known issues
project-specific skills
```

### Task

Temporary:

```text
objective
plan
iterations
experiments
results
artifacts
```

---

# 37. Project Registry

The orchestrator maintains a registry.

Example:

```yaml
projects:
  medicoder:
    path: ~/work/medicoder
    default_lead_agent: claude
    coding_agent: cursor
    experiment_agent: antigravity
```

Adding a new project:

```bash
ai-orch project add project-name ~/work/project-name
```

---

# 38. Project Context

Each project gets:

```text
context.md
architecture.md
conventions.md
decisions.md
known_issues.md
```

Project-specific skills can live in:

```text
projects/<project>/skills/
```

---

# 39. Task Model

A task is a temporary unit of work.

Example:

```bash
ai-orch start medicoder \
  --goal "Optimize ICD-10 retrieval latency"
```

The orchestrator creates:

```text
tasks/medicoder/<task-id>/
├── task.yaml
├── objective.md
├── state.json
├── plan.json
├── iterations/
├── results/
├── experiments/
├── artifacts/
└── logs/
```

---

# 40. Generic Task Lifecycle

```text
USER OBJECTIVE
      ↓
LOAD PROJECT CONTEXT
      ↓
LOAD RELEVANT SKILLS
      ↓
CLAUDE ANALYZES OBJECTIVE
      ↓
CLAUDE DECIDES NEXT ACTION
      ↓
SELECT EXECUTOR
      ↓
EXECUTOR PERFORMS ACTION
      ↓
STRUCTURED RESULT
      ↓
CLAUDE REVIEWS RESULT
      ↓
 ┌───────────────┬───────────────┐
 │               │               │
ITERATE         DONE            ABORT
 │               │               │
 ↓               ↓               ↓
executor      final summary    human review
```

---

# 41. Skill Selection

Claude should not automatically load every skill.

The orchestrator should select relevant skills based on:

```text
task type
task description
project
executor
```

Example:

```text
"Optimize inference latency"
```

might load:

```text
optimization
benchmarking
profiling
testing
```

while:

```text
"Implement new API endpoint"
```

might load:

```text
coding
backend
testing
```

This keeps Claude's context efficient.

---

# 42. Claude Decision Schema

Claude should return structured decisions.

Conceptually:

```json
{
  "action": "DELEGATE",
  "executor": "cursor",
  "objective": "Implement cached retrieval",
  "instructions": "...",
  "success_criteria": [
    "All tests pass",
    "Latency improves",
    "No accuracy regression"
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

# 43. Executor Result Schema

Executors return structured results.

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
    "failed": 0
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

---

# 44. Context Efficiency

Claude should receive:

```text
project context
+
relevant skills
+
task objective
+
current state
+
latest structured result
```

rather than:

```text
entire repository
+
all historical logs
+
all previous tasks
```

This preserves expensive reasoning context for decisions.

---

# 45. GitHub Principle

The company GitHub repository should remain normal.

Desired flow:

```text
User
 ↓
Claude
 ↓
Cursor / Antigravity / Python
 ↓
Local working tree
 ↓
User reviews
 ↓
User commits
 ↓
User pushes
 ↓
GitHub
```

No automatic:

```text
AI branch
AI PR
AI merge
AI push
```

in Version 1.

---

# 46. Company Security

Local orchestration does **not automatically mean no data leaves the Mac**.

Before using the system on company code:

1. Check Medicoder's AI/tooling policy.
2. Determine permitted external services.
3. Determine what source/data can be sent externally.
4. Do not expose secrets or credentials.
5. Do not expose restricted/patient/production data.
6. Prefer synthetic/local data where possible.
7. Configure providers appropriately.

This is more important than keeping the GitHub history visually normal.

---

# 47. Git Safety

Before every task:

```bash
git status --short
```

Record the initial state.

If the repository already has user changes:

```text
warn
record baseline
avoid blindly overwriting
```

---

# 48. No Automatic Git Commits

Initial system:

```text
AI modifies working tree
        ↓
AI tests
        ↓
Claude reviews
        ↓
Task completes
        ↓
User reviews diff
        ↓
User commits
        ↓
User pushes
```

---

# 49. Human Approval Gates

Require explicit human approval for:

```text
git push
git merge
deployment
production changes
credential access
secret modification
destructive operations
database migrations
external communications
```

---

# 50. Read-Only Mode

Support:

```bash
ai-orch start medicoder \
  --goal "Analyze the inference pipeline" \
  --read-only
```

Allowed:

```text
read
test
benchmark
inspect
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

# 51. Dry-Run Mode

Support:

```bash
ai-orch start medicoder \
  --goal "Optimize inference" \
  --dry-run
```

Claude should explain the intended plan without modifying files.

---

# 52. Controlled Write Mode

Normal local mode:

```text
modify working tree
run tests
run experiments
iterate
```

but:

```text
NO automatic push
NO automatic merge
NO automatic deployment
```

---

# 53. Persistent Task State

The orchestrator must survive:

- terminal closure
- Mac restart
- API failure
- executor failure
- partial completion

Support:

```bash
ai-orch task resume medicoder <task-id>
```

---

# 54. Iteration Limits

Example:

```yaml
max_iterations: 10
max_execution_time_minutes: 60
```

When exceeded:

```text
REQUEST_HUMAN
```

with a summary of what happened.

---

# 55. Experiment Tracking

Record:

```text
experiment ID
task ID
timestamp
code state
configuration
dataset
model
parameters
metrics
result
```

Store experiment artifacts outside the company repository unless explicitly required otherwise.

---

# 56. Baseline and Verification

Optimization/research tasks should establish a baseline where practical.

Claude should compare:

```text
baseline
vs
candidate
```

using the task's success criteria.

Passing tests alone does not constitute success if the task requires measurable improvement.

---

# 57. Failure Handling

Executor failure:

```text
Executor
 ↓
structured FAILURE
 ↓
Claude
 ↓
diagnose
 ↓
retry / change executor / change strategy / request human
```

Retry limits are required.

---

# 58. Parallelism

Do not start with complex parallel worktrees.

Version 1:

```text
one project
one working tree
one active executor
sequential iteration
```

Later:

```text
parallel experiments
isolated worktrees
```

can be introduced.

---

# 59. Reusable CLI

Eventually:

```bash
ai-orch project list
```

```bash
ai-orch project add medicoder ~/work/medicoder
```

```bash
ai-orch start medicoder --goal "..."
```

```bash
ai-orch task list medicoder
```

```bash
ai-orch task status medicoder
```

```bash
ai-orch task resume medicoder <task-id>
```

---

# 60. Example Long-Term Workflow

September:

```text
Optimize inference
```

October:

```text
Implement feature
```

November:

```text
Investigate regression
```

December:

```text
Evaluate new model
```

January:

```text
Refactor architecture
```

All use:

```text
SAME ORCHESTRATOR
SAME PROJECT
DIFFERENT TASK
```

---

# 61. Adding Another Project

```bash
ai-orch project add another-project ~/work/another-project
```

Then:

```bash
ai-orch start another-project \
  --goal "Investigate performance bottleneck"
```

The same orchestrator handles it.

---

# 62. Agent Abstraction

Do not hard-code the entire system around Claude.

Use conceptual interfaces:

```text
LeadAgent
Executor
Skill
Project
Task
```

Claude is the current preferred implementation of:

```text
LeadAgent
```

Cursor and Antigravity are implementations of:

```text
Executor
```

This makes future replacement possible.

---

# 63. Executor Abstraction

Conceptually:

```text
Lead Agent
    ↓
Executor interface
    ├── Cursor
    ├── Antigravity
    ├── Python
    ├── Shell
    └── Future executor
```

Claude should reason in terms of capabilities where possible.

---

# 64. Technology Stack

Initial:

```text
Python
Anthropic SDK
Pydantic
python-dotenv
PyYAML
JSON / JSONL
Git
Cursor CLI
Antigravity CLI
```

Later:

```text
SQLite
FastAPI
TUI/Web UI
Docker
parallel worktrees
job queue
```

---

# 65. Complete Implementation Order

## Phase 0 — Existing Agent Configuration Migration

**Do this first.**

```text
1. Inventory Medicoder AI configuration.
2. Snapshot originals.
3. Identify rules.
4. Identify skills.
5. Identify hooks.
6. Identify MCP/tool configuration.
7. Identify prompts.
8. Identify conventions.
9. Identify workflows.
10. Classify scope.
11. Translate semantics.
12. Create migration manifest.
13. Create global skills/rules.
14. Create Medicoder project context.
15. Create executor-specific instructions.
16. Preserve legacy configuration temporarily.
17. Validate migrated behavior.
18. Only then consider removing duplicates.
```

This phase ensures that the new system begins with the knowledge already accumulated.

---

## Phase 1 — Permanent Orchestrator Skeleton

Create:

```text
~/ai-orchestrator/
```

with:

```text
orchestrator/
agents/
executors/
projects/
tasks/
state/
logs/
config/
prompts/
skills/
```

---

## Phase 2 — Python Environment

Install:

```text
anthropic
pydantic
python-dotenv
pyyaml
```

---

## Phase 3 — Project Registry

Implement:

```text
project add
project list
project inspect
```

---

## Phase 4 — Project Context

Implement:

```text
context
architecture
conventions
decisions
known issues
project skills
```

---

## Phase 5 — Claude Lead Agent

Implement Claude API integration.

---

## Phase 6 — Decision Schema

Implement:

```text
DELEGATE
DONE
ABORT
REQUEST_HUMAN
```

---

## Phase 7 — Executor Interface

Implement:

```text
CursorExecutor
AntigravityExecutor
PythonExecutor
```

---

## Phase 8 — Cursor Integration

Allow:

```text
read
modify
test
```

but not:

```text
commit
push
merge
```

---

## Phase 9 — Structured Results

Normalize all executor output.

---

## Phase 10 — Persistent Task State

Implement task directories and state.

---

## Phase 11 — Main Feedback Loop

Implement:

```text
goal
 ↓
Claude
 ↓
executor
 ↓
result
 ↓
Claude
 ↓
executor
 ↓
...
 ↓
DONE
```

---

## Phase 12 — Safety

Implement:

```text
dry-run
read-only
Git baseline
iteration limits
timeouts
secret protection
```

---

## Phase 13 — Python Executor

Add deterministic analysis.

---

## Phase 14 — Antigravity Executor

Add exploratory/experimental execution.

---

## Phase 15 — Experiment Tracking

Add reproducible metrics and artifacts.

---

## Phase 16 — Reusable Skills

Migrate and normalize existing skills.

---

## Phase 17 — Durable Project Memory

Implement controlled updates to:

```text
decisions.md
known_issues.md
architecture.md
```

---

## Phase 18 — Background Execution

Add resumable background tasks.

---

## Phase 19 — Parallel Execution

Add:

```text
worktrees
parallel experiments
```

only after the sequential system is stable.

---

## Phase 20 — Optional UI

Add a TUI or web interface only if useful.

---

# 66. First Migration Test

Before implementing the autonomous loop, inspect the Medicoder repository and answer:

```text
What AI configuration already exists?

What rules exist?

What skills exist?

What hooks exist?

What MCP integrations exist?

What conventions have been encoded?

What is generic?

What is Medicoder-specific?

What is Cursor-specific?

What is Claude-specific?

What is temporary?
```

The output should be a migration manifest.

---

# 67. First End-to-End Test

After migration:

```bash
ai-orch start medicoder \
  --goal "Analyze the repository architecture and identify the main inference pipeline"
```

Use read-only mode.

Verify that Claude has access to:

```text
migrated project context
relevant migrated skills
relevant rules
repository
```

---

# 68. Second Test

```text
Run the existing test suite and summarize failures.
```

Read-only.

---

# 69. Third Test

```text
Add a small unit test for an existing function.
```

Controlled write mode.

Verify:

```bash
git diff
git status
```

No commit.

---

# 70. Fourth Test

Run a real iterative task:

```text
Optimize X while preserving Y.
```

Verify:

```text
Claude plans
→ executor acts
→ benchmark
→ Claude evaluates
→ another iteration
→ final result
```

---

# 71. Definition of Done — Migration

Migration is complete when:

- [ ] Existing AI configuration has been inventoried.
- [ ] Originals are preserved.
- [ ] Every important rule has a destination.
- [ ] Existing skills have been migrated or intentionally retained.
- [ ] Hooks have been classified.
- [ ] MCP integrations have been classified.
- [ ] Global knowledge is separated from Medicoder-specific knowledge.
- [ ] Executor-specific instructions are separated from general rules.
- [ ] Temporary instructions are not accidentally made permanent.
- [ ] Migrated behavior has been validated.
- [ ] Nothing important was silently lost.

---

# 72. Definition of Done — Version 1

Version 1 is complete when:

```bash
ai-orch start medicoder \
  --goal "Perform a useful engineering task"
```

can:

```text
1. Load Medicoder project context.
2. Load relevant migrated skills/rules.
3. Create a task.
4. Ask Claude to analyze it.
5. Delegate to Cursor.
6. Receive structured results.
7. Return results to Claude.
8. Iterate automatically.
9. Run tests/benchmarks.
10. Stop when success criteria are met.
11. Persist state.
12. Produce a final summary.
13. Leave changes in the local working tree.
14. Take NO GitHub action.
```

The same infrastructure must then handle:

```bash
ai-orch start medicoder \
  --goal "Implement a new feature"
```

and:

```bash
ai-orch start medicoder \
  --goal "Investigate a bug"
```

without rebuilding the orchestrator.

---

# 73. Final Mental Model

The final system should be understood as a **personal local AI engineering environment**, not as a collection of one-off scripts.

```text
                  PERSONAL AI
              ENGINEERING SYSTEM
                       │
          ┌────────────┴────────────┐
          │                         │
       PROJECTS                   SKILLS
          │                         │
    ┌─────┴─────┐                   │
    │           │                   │
 Medicoder   Project B              │
    │           │                   │
 Existing      Tasks                │
 AI knowledge                       │
    │                               │
    └──────────────┬────────────────┘
                   │
                TASK
                   │
                   ▼
                CLAUDE
                   │
             reasoning
             planning
             review
                   │
          ┌────────┼────────┐
          │        │        │
        Cursor  Antigravity Python
          │        │        │
          └────────┼────────┘
                   │
             LOCAL PROJECT
                   │
              user review
                   │
                GitHub
```

The key properties are:

```text
ORCHESTRATOR = permanent
PROJECT      = persistent
TASK         = temporary
SKILL        = reusable
AGENT        = replaceable
EXECUTOR     = replaceable
KNOWLEDGE    = migrated and organized
WORKTREE     = real
GITHUB       = normal
```

Most importantly:

```text
EXISTING MEDICODER AI WORK
          ↓
   IS NOT THROWN AWAY
          ↓
      INVENTORY
          ↓
     CLASSIFICATION
          ↓
      TRANSLATION
          ↓
GLOBAL / PROJECT / AGENT / TASK
          ↓
NEW ORCHESTRATOR
```

The new system should be an **evolution of the existing workflow**, not a reset.