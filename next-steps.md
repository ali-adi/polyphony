# Polyphony — What to Do Next + Token Optimization Roadmap

> **Status:** Post-v0.1.0 planning document  
> **Scope:** Reliability, benchmarking, orchestration, token efficiency, memory, research workflows, developer UX, security, and long-term intelligence  
> **Principle:** Build Polyphony into a reliable local-first orchestration system before making it increasingly autonomous.

---

## 1. Current State

Polyphony already has a substantial v0.1.0 core:

- Local-first CLI orchestration
- Claude Code as lead reasoner with AGY fallback
- Antigravity, Cursor Agent, and deterministic Python/Shell executors
- Hierarchical reasoning/execution
- Safety policy engine
- Protected paths and blocked commands
- Git checkpoints and rollback
- Nested repo/worktree discovery
- Zero-change guardrails
- Configurable models and thinking levels
- Dynamic subagents/workflow policies
- Bidirectional fallback
- Circuit breakers and failure classification
- Human-in-the-loop `ASK_HUMAN`
- Prompt caching and session IDs
- Universal migration of `.claude/`, `.cursor/`, `.agents/`
- Durable project/task memory
- Structured JSONL event logs
- Persistent task state and Markdown reports
- Global → project → task configuration cascade
- CLI task lifecycle management
- 87 passing tests

The next phase should **not** primarily be about adding more agent integrations.

The next phase should make Polyphony:

1. **Reliable**
2. **Measurable**
3. **Token-efficient**
4. **Evidence-driven**
5. **Safe around existing user work**
6. **Capable of increasingly sophisticated orchestration**

---

# 2. Immediate Priority: Freeze the Current Core

Before major architectural expansion:

## 2.1 Tag the current implementation

Create:

```text
v0.1.0-core
```

This becomes the known-good baseline.

Record:

- test count
- supported executors
- CLI behavior
- config schema
- task state schema
- event schema
- migration behavior
- safety behavior
- known limitations

## 2.2 Establish a compatibility contract

Define what Polyphony guarantees at v0.1:

- A task can be started and resumed
- State survives interruption
- Executors produce normalized results
- Dangerous operations are blocked
- Human approval is respected
- Existing user work is not accidentally destroyed
- Task history can be reconstructed
- A completed task has verifiable evidence

Anything beyond this can evolve without silently changing those guarantees.

---

# 3. First Major Next Step: Build a Real Benchmark Suite

Do this before sophisticated routing or learned optimization.

Create:

```text
benchmarks/
├── tasks/
├── expected/
├── runners/
├── results/
├── reports/
└── README.md
```

Start with at least these tasks:

1. Simple bugfix
2. Multi-file feature
3. Existing failing test
4. Refactor
5. Ambiguous requirement
6. Dependency problem
7. Executor failure
8. Zero-change / false completion
9. Research → implementation
10. Iterative bugfix requiring multiple attempts
11. Large-context task
12. Task with misleading repository instructions
13. Task with unrelated pre-existing changes
14. Task requiring human clarification
15. Task where deterministic tooling is sufficient and an LLM should ideally not be invoked

Measure:

- Correctness
- Completion rate
- Iterations
- LLM calls
- Executor calls
- Total tokens
- Input tokens
- Output tokens
- Wall-clock time
- Human interventions
- Failed attempts
- Recovery success
- Safety violations
- Rollback correctness
- Diagnosis quality
- Report accuracy
- Context size
- Cache hit rate
- Redundant-context ratio
- Tokens per successful task

This benchmark becomes the foundation for almost every later Polyphony feature.

---

# 4. Reliability First

Target:

## `v0.2.0 — Reliability`

### 4.1 Failure injection

Test:

- Executor crash
- Executor timeout
- Malformed executor output
- Agent claims success without changing anything
- Agent claims success despite failing tests
- Repeated identical failure
- Wrong executor selection
- Permission error
- CLI unavailable
- CLI authentication failure
- State write failure
- State corruption
- Process killed during execution
- Polyphony killed during execution
- Machine restart during task
- Git checkpoint failure
- Rollback failure
- Dirty working tree
- Untracked files
- Nested repositories
- Worktrees
- Concurrent Polyphony processes

### 4.2 Crash recovery

Polyphony should be able to determine:

```text
TASK_RUNNING
↓
process disappeared
↓
inspect persisted state
↓
inspect working tree
↓
determine whether execution completed
↓
resume / recover / ask human
```

Avoid simply assuming that an interrupted task failed.

### 4.3 Idempotency

Repeated commands should not accidentally:

- duplicate work
- duplicate task records
- duplicate events
- corrupt state
- re-run destructive operations

Introduce:

- task IDs
- execution IDs
- iteration IDs
- event IDs
- idempotency keys

### 4.4 Stale-task detection

Detect tasks that have been running without a heartbeat.

Support:

```text
RUNNING
STALE
RECOVERING
PAUSED
ABORTED
```

---

# 5. Fix Rollback Before Expanding Autonomy

The current automatic rollback concept is powerful but dangerous if the user already has unrelated work in the repository.

Polyphony must distinguish:

```text
User's pre-existing changes
```

from:

```text
Polyphony-produced changes
```

Before execution, record a baseline:

- HEAD commit
- tracked-file diff
- untracked-file inventory
- relevant file hashes
- repository status
- branch/worktree identity

After execution, calculate the delta.

Rollback should remove **only Polyphony-owned changes**.

Never assume:

```text
git reset --hard
```

is equivalent to safely undoing a task.

---

# 6. Formalize the Executor Protocol

All executors should conform to one interface.

Conceptually:

```python
capabilities()
health()
start()
send()
poll()
cancel()
collect()
```

Normalize results into a common schema:

```yaml
status:
  SUCCESS | PARTIAL | FAILED | BLOCKED | TIMEOUT | CANCELLED

summary:
files_changed:
tests:
metrics:
errors:
warnings:
artifacts:
next_action:
confidence:
```

The orchestrator should not need provider-specific reasoning about how Cursor, AGY, or Claude report results.

---

# 7. Separate Roles From Providers

Do not permanently define:

```text
Claude = lead
AGY = fallback
Cursor = executor
```

Instead define roles:

```text
LEAD_REASONER
IMPLEMENTER
RESEARCHER
REVIEWER
VERIFIER
DETERMINISTIC_EXECUTOR
```

Then providers implement those roles.

This enables future routing such as:

```text
LEAD_REASONER → Claude
LEAD_REASONER → AGY
IMPLEMENTER → Cursor
IMPLEMENTER → AGY
RESEARCHER → AGY
VERIFIER → Python
```

The role remains stable even as providers change.

---

# 8. Capability-Based Routing

Replace simple primary/secondary routing with capability requirements.

Examples:

```yaml
requires:
  - high_reasoning
  - code_editing
  - deterministic_verification
```

Potential executor capabilities:

- High reasoning
- Fast reasoning
- Code editing
- Repository navigation
- Web research
- Browser interaction
- Shell execution
- Deterministic computation
- Test execution
- Large-context processing
- Long-running execution
- Image understanding
- Structured output
- Cheap execution
- Offline execution

The router selects the cheapest/safest executor capable of satisfying the task.

---

# 9. Explicit Task Types

Introduce:

```text
FEATURE
BUGFIX
REFACTOR
RESEARCH
EXPERIMENT
AUDIT
VERIFICATION
MAINTENANCE
```

Each task type can have a default workflow.

For example:

```text
BUGFIX
→ reproduce
→ implement
→ test
→ verify
```

```text
RESEARCH
→ gather evidence
→ synthesize
→ identify uncertainty
→ optionally implement
→ verify
```

```text
AUDIT
→ inspect
→ collect evidence
→ report
→ no mutation by default
```

---

# 10. Formal Event Model

Create a durable event stream.

Examples:

```text
TASK_CREATED
TASK_STARTED
TASK_PAUSED
TASK_RESUMED

LEAD_STARTED
LEAD_DECISION

EXECUTOR_SELECTED
EXECUTOR_STARTED
EXECUTOR_OUTPUT
EXECUTOR_FINISHED

VERIFICATION_STARTED
VERIFICATION_FINISHED

REVIEW_STARTED
REVIEW_FINISHED

ITERATION_STARTED
ITERATION_FINISHED

HUMAN_REQUESTED
HUMAN_RESPONDED

CHECKPOINT_CREATED
ROLLBACK_STARTED
ROLLBACK_FINISHED

TASK_COMPLETED
TASK_FAILED
TASK_ABORTED
```

This enables:

- replay
- debugging
- analytics
- auditability
- benchmark analysis
- future UI

Add:

```bash
polyphony replay <task-id>
```

to reconstruct what happened.

---

# 11. Add `polyphony doctor`

A diagnostic command should inspect:

```text
Polyphony installation
Python environment
Git
Claude CLI
AGY CLI
Cursor CLI
Authentication
Model configuration
Project registration
State directory
Permissions
Disk space
Hooks
Safety configuration
Migration state
Executor health
```

Example:

```bash
polyphony doctor
```

Output should clearly distinguish:

```text
OK
WARNING
ERROR
BLOCKED
```

---

# 12. Add `polyphony task explain`

For every task, Polyphony should be able to answer:

- Why was this executor selected?
- Why did the lead choose this action?
- Why was another iteration performed?
- Why did Polyphony stop?
- Why was a task blocked?
- Why was a human asked?
- What evidence established completion?
- How many tokens were spent?
- Where did failures occur?

This is critical once the system becomes autonomous.

---

# 13. Token Optimization — Core Objective

Token optimization should be treated as a first-class Polyphony subsystem.

The objective is **not**:

> Minimize tokens at any cost.

The objective is:

> **Minimize unnecessary reasoning while preserving correctness, safety, and completeness.**

A useful conceptual metric is:

```text
useful outcome
────────────────────────────────
reasoning expenditure
```

---

# 14. Context Optimization

The largest source of waste in a multi-agent system is repeatedly sending unnecessary context.

A decision context should look like:

```text
GLOBAL RULES
PROJECT CONTEXT
CURRENT TASK
RELEVANT MEMORY
RELEVANT FILES
LATEST EXECUTOR RESULT
VERIFICATION EVIDENCE
```

Not:

```text
entire conversation
+ entire repository instructions
+ every previous executor transcript
+ every previous iteration
```

Implement:

### Context budgets

For example:

```yaml
context_budget:
  lead: 30000
  implementation: 20000
  research: 16000
  verification: 8000
```

These should be configurable rather than hard-coded.

### Relevance filtering

Only retrieve:

- relevant rules
- relevant files
- relevant memories
- relevant previous decisions
- relevant evidence

### Progressive disclosure

Start with compact information.

Allow agents to request deeper evidence when necessary.

### Deduplication

Do not repeatedly include identical:

- instructions
- file contents
- decisions
- test output
- repository metadata

### Diff-first context

After the first iteration, prioritize:

```text
what changed
what failed
what remains
```

over re-sending the entire repository context.

---

# 15. Context Hierarchy

Use progressive compression:

```text
RAW TRANSCRIPT
      ↓
STRUCTURED EXECUTOR RESULT
      ↓
ITERATION SUMMARY
      ↓
TASK STATE
      ↓
PROJECT MEMORY
```

Claude should normally consume:

```text
TASK STATE
+
RELEVANT EVIDENCE
+
RELEVANT MEMORY
```

rather than raw historical transcripts.

Keep raw transcripts locally for debugging and explicit retrieval.

---

# 16. Agent-Specific Context Builders

Different agents require different context.

### Lead reasoner

Prioritize:

- objective
- constraints
- architecture
- decisions
- evidence
- uncertainty
- failure history

### Implementer

Prioritize:

- exact task
- acceptance criteria
- relevant code
- conventions
- tests
- implementation constraints

### Researcher

Prioritize:

- research question
- known evidence
- source requirements
- desired output format
- unresolved questions

### Verifier

Prioritize:

- expected behavior
- changed files
- acceptance criteria
- test/benchmark commands
- objective evidence

The same task should not produce identical prompts for every agent.

---

# 17. Structured Outputs

Do not pass verbose agent prose into the next agent whenever structured data is sufficient.

Prefer:

```yaml
status: SUCCESS

summary: "Fixed ICD-10 cache normalization."

files_changed:
  - coder/cache.py
  - tests/test_cache.py

tests:
  passed: 19
  failed: 0

verification:
  - "pytest tests/test_cache.py"

remaining_risks:
  - "No performance benchmark performed"

recommended_next_action: VERIFY
```

Store the full transcript locally.

Pass the compact representation downstream.

---

# 18. Deterministic Work Should Not Consume LLM Tokens

Polyphony should aggressively avoid LLM calls for tasks that can be answered deterministically.

Examples:

```text
git status
git diff
pytest
ruff
mypy
file hashing
JSON parsing
metric calculation
benchmark aggregation
dependency inspection
test counting
repository structure
process status
```

Instead:

```text
AGENT
  ↓
deterministic tool
  ↓
evidence
  ↓
AGENT only if interpretation is needed
```

For example:

```text
pytest
→ 19/19 passed
→ deterministic rule
→ DONE
```

No LLM confirmation required.

---

# 19. Evidence Cache

Cache objective evidence:

```text
test results
benchmark results
git status
git diff
file hashes
dependency graph
repository metadata
static analysis
```

If nothing relevant changed, do not re-run expensive reasoning just to rediscover the same fact.

Every cached result should have:

```yaml
source:
timestamp:
inputs:
hash:
result:
valid_until:
```

Invalidate it when its dependencies change.

---

# 20. Token Usage Tracking

Track usage per:

- task
- iteration
- agent
- executor
- model
- decision
- prompt
- result

Example:

```yaml
usage:
  lead:
    input_tokens: 18200
    output_tokens: 3100

  executors:
    cursor:
      input_tokens: 12000
      output_tokens: 2100

  total:
    input: 30200
    output: 5200
```

Also track:

```text
LLM calls
executor calls
reasoning calls
tokens per iteration
tokens per successful task
average context size
cache hit rate
context reuse
redundant context ratio
```

---

# 21. Token Budgets

Allow:

```bash
polyphony start \
  --goal "implement X" \
  --token-budget 50000
```

Or project/task configuration:

```yaml
budget:
  total_tokens: 50000
  lead: 15000
  execution: 25000
  verification: 5000
  reserve: 5000
```

The orchestrator dynamically allocates the remaining budget.

Example:

```text
50k total

Planning          8k
Implementation   14k
Verification      3k
--------------------
Remaining        25k
```

versus:

```text
50k total

Planning         18k
Implementation   21k
Verification      5k
--------------------
Remaining         6k
```

In the second case, Polyphony may:

- compact context
- switch executor
- perform deterministic verification
- request human input
- stop
- use a lower-cost strategy

---

# 22. Adaptive Token Allocation

Do not divide the budget equally.

Allocate based on task complexity.

For example:

```text
Simple bugfix
→ small lead budget
→ larger implementation budget
→ deterministic verification

Architecture redesign
→ larger lead budget
→ implementation
→ independent review
→ verification
```

Reserve some budget for unexpected failures.

Never spend the entire budget before verification.

---

# 23. Output Optimization

Enforce concise executor contracts.

Agents should report:

- status
- summary
- files changed
- tests
- errors
- warnings
- artifacts
- remaining risks
- next action

Do not force downstream agents to interpret thousands of tokens of conversational narration.

---

# 24. Context Compaction

For long-running tasks:

```text
Iteration 1
Iteration 2
Iteration 3
Iteration 4
...
```

should eventually become:

```yaml
task_summary:
current_state:
successful_changes:
failed_attempts:
remaining_problem:
important_decisions:
known_risks:
verification_status:
```

Keep raw history locally.

Compaction should be:

- deterministic where possible
- schema-driven
- versioned
- recoverable

Never destroy the original evidence.

---

# 25. Caching Layers

Potential cache layers:

## Static context cache

- global rules
- project conventions
- architecture

## Task context cache

- task objective
- acceptance criteria
- relevant files

## Evidence cache

- tests
- benchmarks
- Git state
- static analysis

## Semantic cache

Later, cache answers to equivalent or near-equivalent questions.

All cache entries need invalidation rules.

---

# 26. Cost-Aware Routing

The router should eventually consider:

```text
capability
quality
latency
token expenditure
failure rate
availability
task complexity
```

Conceptually:

```text
required capability
        ↓
candidate executors
        ↓
expected quality / cost / latency
        ↓
select strategy
```

Do not optimize for cheapness alone.

A cheap executor that fails three times may cost more than a strong executor succeeding once.

---

# 27. "Don't Call an LLM" as a Routing Decision

The router should be able to return:

```text
DETERMINISTIC
```

instead of:

```text
CLAUDE
CURSOR
AGY
```

Examples:

```text
"Are all tests passing?"
→ pytest

"What files changed?"
→ git diff

"How many benchmark cases passed?"
→ Python

"Is this task complete according to a simple rule?"
→ policy engine
```

This can become one of Polyphony's biggest token-saving mechanisms.

---

# 28. Token Efficiency Benchmarking

Add token metrics to the benchmark suite.

For every strategy measure:

```yaml
correct:
safe:
complete:

tokens:
  input:
  output:
  total:

calls:
  llm:
  deterministic:
  executor:

latency:
iterations:
human_interventions:

cache:
  hit_rate:
  reuse:
  redundant_context_ratio:
```

Compare orchestration strategies based on:

```text
correctness
+
safety
+
completeness
+
latency
+
reasoning expenditure
```

not raw token count alone.

---

# 29. Reliability + Token Optimization Are Connected

A major design principle:

> **Good evidence reduces reasoning requirements.**

For example:

```text
Bad:
Claude → "Are tests passing?"
          ↓
Cursor → reads repo
          ↓
Claude → interprets response
```

Better:

```text
pytest
 ↓
19/19 passed
 ↓
policy engine
 ↓
DONE
```

And:

```text
Bad:
Claude receives five complete previous transcripts.

Better:
Claude receives:
- current state
- last failure
- relevant diff
- test result
- one relevant historical decision
```

Polyphony should optimize the entire information flow, not merely prompt length.

---

# 30. Knowledge and Memory

Formalize memory types:

```text
RULE
DECISION
CONVENTION
FAILURE
LESSON
ARCHITECTURE
KNOWN_ISSUE
SKILL
EXPERIMENT
```

Each memory should contain:

```yaml
type:
scope:
source:
created:
updated:
confidence:
status:
content:
```

Prioritize **failure memory** before fancy semantic/vector memory.

A system that remembers:

> "This approach failed because X"

is immediately useful.

A system that merely remembers thousands of semantic snippets is much less useful.

---

# 31. Memory Quality Controls

Later add:

- deduplication
- contradiction detection
- provenance
- confidence
- expiration/TTL
- supersession
- project/global scoping
- automatic promotion
- human approval for important architectural decisions

Do not allow low-confidence agent speculation to silently become permanent project truth.

---

# 32. Orchestration DAG

Once sequential workflows are reliable, introduce:

```text
                 Research
                    │
          ┌─────────┴─────────┐
          ↓                   ↓
    Implementation        Alternative
          │                   │
          └─────────┬─────────┘
                    ↓
                  Review
                    ↓
                Verification
```

Support:

- task dependencies
- parallel execution
- fan-out
- fan-in
- retries
- conditional branches
- reviewer stages
- failure propagation
- cancellation

---

# 33. Worktree-Based Parallelism

Only introduce this after reliability is strong.

Example:

```text
main working tree
      │
      ├── worktree A → implementation
      ├── worktree B → alternative implementation
      └── worktree C → investigation
                         ↓
                     reviewer
                         ↓
                    merge decision
```

Polyphony should remain careful about the user's existing working tree.

---

# 34. Review and Verification Agents

Later workflows can use:

```text
Planner
   ↓
Implementer
   ↓
Reviewer
   ↓
Verifier
```

Potential reviewer modes:

- correctness reviewer
- security reviewer
- architecture reviewer
- test reviewer
- performance reviewer

Reviewers should receive evidence and diffs rather than the entire history.

---

# 35. Multi-Agent Consensus

For genuinely ambiguous tasks, support:

```text
Agent A → proposal
Agent B → independent proposal
Agent C → critique
Lead → synthesis
```

Potentially:

- independent solutions
- adversarial review
- quorum
- judge
- disagreement detection

Do not use multiple agents simply because they are available.

Parallel reasoning should have a measurable expected benefit.

---

# 36. Dynamic Task Decomposition

Eventually the lead should be able to produce:

```text
TASK
├── investigate
├── implement
├── test
├── benchmark
└── review
```

Each child gets:

- objective
- constraints
- inputs
- expected output
- dependency information
- budget
- deadline
- capabilities

The parent aggregates evidence rather than blindly concatenating transcripts.

---

# 37. Research Workflows

Create first-class research support:

```text
RESEARCH
→ query decomposition
→ source discovery
→ source extraction
→ evidence normalization
→ synthesis
→ uncertainty
→ recommendations for implementation
```

Potential integrations:

- web research
- GitHub
- papers
- documentation
- issues
- changelogs
- repositories

Capture provenance for every important claim.

---

# 38. Experiment Registry

For ML/research tasks, store:

```yaml
experiment:
  name:
  hypothesis:
  baseline:
  candidates:
  configuration:
  model:
  dataset:
  metrics:
  runtime:
  executor:
  result:
  artifacts:
  reproducibility:
```

This makes Polyphony useful beyond code editing.

---

# 39. Research Reproducibility

Record:

- code version
- config
- model
- dataset
- dependencies
- random seeds
- environment
- executor
- metrics
- artifacts
- source references

A successful experiment should be reproducible.

---

# 40. Security Expansion

The current safety engine should eventually become a broader policy layer.

Important areas:

### Prompt injection

Repository files, web pages, issue descriptions, and tool outputs may contain instructions intended to manipulate agents.

Treat external/untrusted content as **data**, not policy.

### Secrets

Detect:

- API keys
- tokens
- passwords
- credentials
- private keys

before passing data to external agent providers.

### Sensitive data

Classify and block or require approval for:

- patient data
- production data
- credentials
- confidential company material

### Network policy

Eventually support:

```text
allowed domains
blocked domains
offline mode
research mode
```

### Least privilege

Executors should receive only the permissions they need.

---

# 41. Human Approval Policy Engine

Instead of one generic approval gate, define risk levels.

Example:

```text
LOW
- read files
- run tests

MEDIUM
- edit source
- install dependency

HIGH
- modify database
- alter infrastructure
- change security policy
- external communication

CRITICAL
- production deployment
- credential changes
- destructive operations
```

Policy determines whether Polyphony:

```text
ALLOW
ASK
BLOCK
```

---

# 42. Observability

Eventually expose:

```text
task timeline
executor timeline
token usage
failure graph
iteration history
decision history
context size
cache behavior
latency
```

A future TUI could show:

```text
Task #42
────────────────────────────

Lead        Claude
Executor    Cursor
Iteration   3/8

Tokens      21.4k / 50k
Status      VERIFYING

✓ Planning
✓ Implementation
✓ Tests
✗ Integration test
→ Debugging

Last decision:
Fix API response normalization
```

---

# 43. Exportable Run Bundles

Support exporting a task:

```text
task-bundle/
├── metadata.yaml
├── state.json
├── events.jsonl
├── report.md
├── decisions.md
├── evidence/
├── diffs/
└── metrics.json
```

Useful for:

- debugging
- benchmarks
- sharing
- regression tests
- reproducibility
- incident analysis

---

# 44. Golden Traces and Regression Testing

Record successful orchestration traces.

Then test future Polyphony versions against them.

Examples:

```text
golden/
├── simple_bugfix/
├── executor_timeout/
├── rollback/
├── human_question/
├── multi_iteration/
└── token_budget/
```

Detect regressions in:

- routing
- state transitions
- safety
- context construction
- token efficiency
- completion decisions

---

# 45. Prompt/Context Regression Testing

Prompts are part of the system.

Test:

- required information is present
- irrelevant information is excluded
- budgets are respected
- structured outputs remain valid
- sensitive information is redacted
- context compression preserves important facts

Treat context construction like code.

---

# 46. Long-Term Intelligence

Only after enough benchmark data exists should Polyphony learn from its history.

Potential learned components:

### Complexity estimator

Predict:

```text
simple / medium / complex
```

### Learned router

Predict which executor/workflow is most effective.

### Failure predictor

Identify tasks likely to fail before execution.

### Budget allocator

Predict how much reasoning each task requires.

### Workflow selector

Choose:

```text
direct execution
reason → execute
research → execute
multi-agent
DAG
human approval
```

Do not build these before collecting reliable data.

---

# 47. Future Token Optimization: Learned Routing

Once enough historical data exists:

```text
task characteristics
       ↓
complexity estimate
       ↓
candidate workflows
       ↓
expected:
  success
  safety
  latency
  token usage
       ↓
select workflow
```

Example historical result:

```text
Simple refactors:
Cursor → pytest
97% success
9k median tokens

Ambiguous architecture:
Claude → Cursor → Claude review
89% success
42k median tokens
```

Polyphony can eventually learn these patterns.

---

# 48. Developer UX

Useful commands:

```bash
polyphony start
polyphony status
polyphony watch
polyphony pause
polyphony resume
polyphony cancel
polyphony retry
polyphony abort
polyphony diff
polyphony explain
polyphony replay
polyphony doctor
polyphony inspect
```

Eventually:

```bash
polyphony approve
polyphony reject
polyphony events
polyphony metrics
polyphony benchmark
polyphony export
```

Support machine-readable output:

```bash
--json
```

for scripting.

---

# 49. Background Automation

Later:

```text
scheduled maintenance
dependency audits
test monitoring
repository health
benchmark regression detection
documentation freshness
known-issue checks
```

But autonomous background mutation should remain behind strong policy controls.

---

# 50. Project-Level Missions

Eventually support goals larger than a single task:

```text
MISSION
"Make ICD-10 coding pipeline production-ready"
```

Polyphony decomposes this into:

```text
architecture audit
↓
security audit
↓
performance benchmark
↓
implementation
↓
tests
↓
deployment-readiness audit
```

The mission has:

- global budget
- deadlines
- safety policy
- success criteria
- child tasks
- shared memory
- progress tracking

---

# 51. Suggested Version Roadmap

## v0.1.0 — Core

Current state.

Focus:

- basic orchestration
- safety
- executors
- migration
- state
- memory
- CLI

---

## v0.2.0 — Reliability

Priority:

1. Failure injection
2. Crash recovery
3. State corruption recovery
4. Safer rollback
5. Idempotency
6. Stale-task detection
7. Executor health
8. `polyphony doctor`
9. `polyphony replay`
10. Formal executor protocol

---

## v0.3.0 — Evidence + Efficiency

Priority:

1. Benchmark suite
2. Structured executor outputs
3. Context budgets
4. Context compaction
5. Evidence cache
6. Deterministic verification
7. Token usage tracking
8. Token budgets
9. Token-efficiency metrics
10. `polyphony task explain`
11. Golden traces
12. Context regression tests

This is arguably the most important near-term milestone.

---

## v0.4.0 — Orchestration

Priority:

1. Capability routing
2. Explicit task types
3. DAG workflows
4. Parallel execution
5. Worktrees
6. Dependencies
7. Review stages
8. Multi-agent workflows
9. Dynamic decomposition
10. Concurrency controls

---

## v0.5.0 — Intelligence

Priority:

1. Failure memory
2. Knowledge promotion
3. Semantic project search
4. Provenance
5. Architecture graph
6. Skill effectiveness
7. Learned routing
8. Complexity estimation
9. Adaptive budget allocation
10. Workflow selection

---

## v0.6.0 — Research

Priority:

1. Research workflows
2. GitHub/documentation research
3. Paper research
4. Source provenance
5. Experiment registry
6. Reproducibility
7. Benchmark comparison
8. Research artifacts
9. Long-running experiments

---

## v1.0.0 — Reliable Autonomous Engineering

The target:

```text
USER GOAL
    ↓
UNDERSTAND
    ↓
PLAN
    ↓
SELECT WORKFLOW
    ↓
SELECT CAPABILITIES
    ↓
DELEGATE
    ↓
EXECUTE
    ↓
COLLECT EVIDENCE
    ↓
VERIFY
    ↓
REVIEW
    ↓
ITERATE IF NECESSARY
    ↓
PROVE COMPLETION
    ↓
REPORT
    ↓
HUMAN-OWNED GIT / DEPLOYMENT
```

while preserving:

- safety
- user work
- auditability
- reproducibility
- state
- reasonable token expenditure

---

# 52. Recommended Immediate Execution Order

Do **not** implement everything in this document sequentially.

The highest-value next sequence is:

### Step 1 — Freeze v0.1.0

Tag the current implementation.

### Step 2 — Fix rollback semantics

Make sure Polyphony can never destroy unrelated user changes.

### Step 3 — Formalize executor protocol

Normalize all executor interactions.

### Step 4 — Build failure-injection tests

Break Polyphony intentionally.

### Step 5 — Build the benchmark suite

Use realistic engineering tasks.

### Step 6 — Add structured executor results

Make downstream context compact.

### Step 7 — Build the context budgeter

Introduce strict per-agent context budgets.

### Step 8 — Add deterministic evidence paths

Avoid LLM calls for objective facts.

### Step 9 — Add token accounting

Measure input/output tokens, calls, iterations, cache hits, and redundant context.

### Step 10 — Add context compaction + evidence caching

Prevent long tasks from growing indefinitely.

### Step 11 — Add `doctor`, `replay`, and `explain`

Make the system observable and debuggable.

### Step 12 — Benchmark different workflows

Compare:

```text
Claude → Cursor
Claude → Cursor → Claude
AGY → Cursor
Cursor → Python
Claude → Python
multi-agent
```

based on correctness, safety, latency, and reasoning expenditure.

### Step 13 — Only then build DAG/parallel execution

Parallelism adds substantial state-management complexity.

### Step 14 — Only after sufficient data, build learned routing

Do not prematurely build an optimizer without measurements.

---

# 53. The Central Design Philosophy

Polyphony should not become:

> "A program that calls many AI agents."

It should become:

> **A control system that decides when reasoning is necessary, who should reason, who should execute, what evidence is needed, how much context is sufficient, when another iteration is justified, and when the task is actually proven complete.**

The most important optimization is therefore not merely:

```text
fewer tokens
```

It is:

```text
less unnecessary cognition
```

The ideal Polyphony execution is:

```text
deterministic operation
        ↓
small amount of relevant context
        ↓
appropriate agent
        ↓
structured result
        ↓
objective verification
        ↓
stop
```

rather than:

```text
large prompt
↓
large agent response
↓
another large prompt
↓
another agent
↓
another review
↓
another review
↓
eventual completion
```

---

# 54. Ultimate Success Metrics

Polyphony should eventually be evaluated on five dimensions:

## Correctness

Did it produce the intended result?

## Safety

Did it preserve user work and respect policy?

## Efficiency

How much reasoning/execution was required?

## Reliability

Can it recover from failures and interruptions?

## Explainability

Can it prove why it made its decisions and why it stopped?

A mature Polyphony task should be able to answer:

```text
What was requested?
What did Polyphony believe the task required?
Why was this workflow selected?
Why were these agents selected?
What changed?
What failed?
What was retried?
What evidence was collected?
How many tokens were spent?
What was cached?
Why is the task considered complete?
What remains uncertain?
```

That is the standard to build toward.
