# Polyphony Redesign — Design

**Date:** 2026-09-21
**Status:** Approved, pending implementation plan
**Supersedes:** `docs/BASELINE_v0.1.0.md`, `docs/COMPATIBILITY_CONTRACT.md` (both describe a system that has never run; delete on landing)

---

## Context

Polyphony is a local-first orchestrator that drives `claude`, `agy`, and `cursor-agent`
as subprocesses instead of calling metered APIs. The premise is sound: these CLI
subscriptions are already paid for, and a control loop around them costs no
incremental tokens.

**The codebase has never been run against a real task.** This is the single most
important fact about it. A review on 2026-09-21 established:

- 24 of 51 modules (5,652 lines) are unreachable from the CLI entrypoint. They are
  imported only by tests, which is why the suite is green and coverage is 83%.
- Nothing writes `events.jsonl`, so `events`, `replay`, `explain`, and `export` can
  never produce output.
- `TaskState.pending_approval` is never set, so `approve` and `reject` are inert.
- `policy.py` (secrets redaction, prompt-injection defense, risk gating) is called
  by nothing in the live path.
- `benchmarks/runners/benchmark_runner.py::_default_task_evaluator` fabricates its
  results: it reads the expected-outcome YAML and emits those values as
  measurements, with hardcoded constants for token counts and cache hit rates. No
  orchestrator is invoked.
- `CursorExecutor` searches for a binary named `cursor`; the installed binary is
  `cursor-agent`. The Cursor path has never been reachable.
- `estimate_token_cost_usd` applies a flat `$0.006/1k` to a `len(text)//4` token
  estimate. This fictional number gates `max_cost_usd`, which aborts real tasks.

The orphaned modules are not dead code in the usual sense. They are **unvalidated
speculation** — guesses about what orchestrating coding agents requires, none of
which has met a real task. The same is true of the guardrails that *are* wired in.

## Goal

A tool the author uses daily on their own repositories.

Success is measured in hours saved per week and the share of runs that need
intervention. Surface area is worth nothing. Anything that cannot be demonstrated
on a real task is a liability, because it cannot be debugged and it makes the
system look more capable than it is.

## Non-goals

- Broad adoption, plugin ecosystems, or a stable public API.
- Capability-based routing ("which agent is best at this?"). No evidence exists
  to support any such rule, and collecting it is a separate project.
- Overnight unattended operation. Longest intended leash is ~30 minutes.
- Benchmarking as a product feature.

## Operating model

Derived from how the tool will actually be used:

| | Share | Nature | Implication |
|---|---|---|---|
| Watched | ~70% | Write-heavy: bugfixes, features | Log quality is the safety mechanism |
| Away ~30 min | ~30% | Read-heavy: codebase review, notes | Mostly read-only by nature |

The risky work is supervised; the unsupervised work is low-risk. Heavy guardrail
machinery therefore earns very little, and observability earns a great deal.

Executor selection is **quota arbitrage**, not capability matching. Claude Max
weekly limits are the binding constraint; `agy` is cheap and `cursor-agent` is free
via a team plan. Claude does the reasoning (highest value per token); the cheap
subscriptions do mechanical edits; work fails over when any one hits a limit.

---

## Architecture

Three layers.

```
  polyphony run medicoder "fix the ICD-10 ranking bug"
              │
              ▼
  ┌─────────────────────────────────────┐
  │  Session          (worktree + log)  │   isolation & narration
  └──────────────┬──────────────────────┘
                 ▼
  ┌─────────────────────────────────────┐
  │  Loop      (decide → act → record)  │   ReAct cycle + gates
  └──────────────┬──────────────────────┘
                 ▼
  ┌─────────────────────────────────────┐
  │  Executors  (claude / agy / cursor  │   subprocess adapters
  │              / python) + quota      │   + which one to spend
  └─────────────────────────────────────┘
```

Target size: ~14,500 lines → ~4,700, of which 1,054 is the untouched `migrate/`
package. Orchestration code proper goes from ~13,450 to ~3,650.

---

## 1. Session — isolation

### Worktrees

Every task runs in a `git worktree` created off a fresh branch, located **outside
the target repository**:

```
~/.polyphony/worktrees/<project>/<task-id>/
```

The current `orchestrator/worktrees.py:72` places worktrees at
`self.repo_dir / ".polyphony" / "worktrees"` — inside the repo. This is wrong: it
leaves untracked directories in the working tree, and an agent running `git add -A`
could commit an entire second copy of the repository into itself.

With worktrees outside the repo, the target repository's `git status` is clean at
all times. Footprint is one local branch ref per task (`polyphony/<task-id>`).

This single boundary replaces `policy.py`, the approval flow, `rollback.py`, the
temporary-checkpoint commits, and most of `safety.py` — roughly 1,500 lines.

### Nothing reaches the remote

Worktrees, local branches, and `.git/worktrees/` metadata are local-only. The remote
is untouched unless something pushes. Therefore:

- `git push` is blocked **at the subprocess layer** — any spawn whose argv is a
  `git push` is refused. This does not rely on pattern-matching an agent's
  natural-language instruction, which is defeatable.
- Results are handed back as a **squash-merge command the user runs themselves**:

  ```bash
  git merge --squash polyphony/<task-id>
  git commit
  ```

  Squash is the default because a plain `git merge` writes the branch name into the
  merge commit (`Merge branch 'polyphony/task-a3f9'`), and any agent-authored commit
  messages or `Co-Authored-By` trailers inside the branch would become public
  history. Squashing collapses the work into one commit the user authors, with a
  message they write. Public history shows no trace of how the work was produced.

- Polyphony never merges, commits to the user's branches, or pushes.

### Provisioning (required — blocks `code` mode without it)

A fresh worktree contains only tracked files. Measured on the `medicoder` repo:

| Path | Size | Tracked | In worktree |
|---|---|---|---|
| `env/` (virtualenv) | 73M | gitignored | **absent** |
| `database/` | 98M | tracked | present, as an isolated copy |
| `datasets/smoke,tuning/` | 2.6M | gitignored | **absent** |
| `results/` | 3.9G | gitignored | absent (desired) |

The project's test command is `env/bin/python -m unittest discover -s tests -t .`,
and eight test files reference gitignored directories. A naive worktree therefore
breaks every `code`-mode task on this project immediately.

Projects declare what to materialize:

```yaml
worktree:
  provision:
    - { path: env/,             mode: clone }
    - { path: datasets/smoke/,  mode: clone }
    - { path: datasets/tuning/, mode: clone }
```

- `mode: clone` uses `cp -Rc` (APFS copy-on-write). A 73M virtualenv clones in
  milliseconds and consumes no additional disk until written. Isolation and speed
  are both free on macOS. This is the default.
- `mode: link` symlinks. **A symlink is a hole in the isolation wall** — writes
  through it reach the real path. Reserved for paths too large to clone, and
  documented as such.

Provisioning failure is **fatal**. A task that cannot materialize `env/` must not
start, rather than run and report a confusing test failure.

`database/` needs no entry: it is tracked, so each worktree gets its own copy and
the agent cannot corrupt the real one. The existing `protected_paths: database/`
rule becomes structurally true rather than regex-enforced.

### Lifecycle

- `git worktree prune` on startup, clearing interrupted runs.
- On discard: `git worktree remove` + `git branch -D` — zero trace.
- On keep: user squash-merges, then `polyphony clean <task-id>`.

---

## 2. Loop — decisions and gates

### Structure

`_execute_task_loop` is currently one 700-line method in which ten action branches
each rebuild an `IterationRecord`, call `record_iteration`, call
`_update_cost_and_budget`, and `continue`. That duplication is the structural cause
of the sprawl: the loop had no room to grow, so every new idea became a module
beside it.

Handlers return a value; the loop records once.

```python
@dataclass
class Step:
    record:   IterationRecord
    next:     Literal["continue", "stop"]
    status:   TaskStatus | None = None   # required when next == "stop"
    feedback: str | None = None          # prepended to the next prompt
```

```python
while session.has_budget():
    decision = reason(session)                 # parse-retry + failover live here
    step     = HANDLERS[decision.action](session, decision)
    session.record(step)
    if step.feedback:
        session.queue_feedback(step.feedback)
    if step.next == "stop":
        session.finish(step.status)
        break
```

Six handlers of 20–60 lines each: `complete`, `delegate`, `verify`, `skill`,
`ask_human`, `abort`. The loop body is ~40 lines.

### Gates

Guardrails become lists of small functions rather than nested conditionals:

```python
COMPLETION_GATES = [gate_files_changed, gate_tests_pass]
DELEGATION_GATES = [gate_target_files]
```

Each gate is `(session, decision) -> str | None`, returning a rejection message or
`None`. Adding a guardrail after a bad run is appending a function; removing one
that proves wrong is deleting a line.

This matters more than it appears. Every existing guardrail is an **untested
hypothesis**. Real runs will prove some of them wrong. The structure must make
revision cheap, or the same pressure that produced 24 orphan modules will reassert
itself.

Ported verbatim from `main.py`, changed in expression only:

| Gate | Origin | Behavior |
|---|---|---|
| `gate_files_changed` | `main.py:409` | Reject `COMPLETE` when the goal contains action verbs, zero files changed, and `allow_zero_changes` is unset |
| `gate_tests_pass` | `main.py:479` | Run the project test command before accepting `COMPLETE`; retain the `just_verified` skip for redundant reruns |
| `gate_target_files` | `main.py:52` | Reject `DELEGATE` to a coding agent without `target_files` or an explicit file path in the instruction |

### Moved out of the loop

| Concern | From | To | Why |
|---|---|---|---|
| Consecutive-failure counting, 2-strike escalation, 3-strike abort | inline | `Session` | Session state, not loop logic |
| JSON parse-retry with format correction | inline | `reason()` | A reasoner concern |
| Lead failover on quota error | inline | executor layer | A routing concern |
| Post-execution protected-path check | inline | `python` executor only | Worktree makes it defense-in-depth |

### Modes

A task declares `code` or `review`. The mode selects gates and provisioning:

| | `code` | `review` |
|---|---|---|
| Completion gates | files changed + tests pass | document produced and substantive |
| Zero file changes | rejected | expected |
| Test suite | must pass | never run |
| Provisioning | full | skipped — nothing executes |
| Output | a diff to squash-merge | a markdown file |

`review` mode covers codebase reviews and note-writing — the most common
unsupervised workload, which the current design actively fights via
`require_tests_before_stop` and the zero-change guardrail. It is safer by
construction: no tests run, no provisioning holes, and the deliverable is a file.

It needs its own completion gate — did the agent actually write something
substantive, or claim success over an empty file? — as the `review` analogue of
`gate_files_changed`.

---

## 3. Executors & the quota ledger

### Verified flags

Checked against installed binaries on 2026-09-21. Contrary to the initial review,
the Claude and agy adapters pass mostly-valid flags; `--system-prompt-snapshot`,
`--tools`, `--json-schema`, `--mode plan`, and `--effort` are all real.

Confirmed defects:

- `CursorExecutor` searches for `cursor`; the binary is `cursor-agent`, invoked as
  `cursor-agent -p`, not `cursor agent -p`.
- `CursorExecutor` accepts `read_only` and silently ignores it.
- All adapters pass `--dangerously-skip-permissions` unconditionally, including in
  read-only runs.
- Claude's read-only path uses `--tools Read,Bash`; `Bash` writes files, so this is
  not read-only.
- `projects/medicoder/project.yaml` pins `claude-3-7-sonnet-20250219`, long
  superseded.

### Permission model

Every CLI has a genuine read-only mode and a genuine accept-edits mode.
`--dangerously-skip-permissions` is never required.

| | `review` (read-only) | `code` |
|---|---|---|
| `claude` | `--permission-mode plan` | `--permission-mode acceptEdits` |
| `agy` | `--mode plan --sandbox` | `--mode accept-edits --sandbox` |
| `cursor-agent` | `--mode plan` | `-f --sandbox enabled` |

Claude additionally receives `--permission-prompts none`, so anything that would
prompt is denied rather than hanging a non-interactive run indefinitely. This
matters for unsupervised runs, where a prompt blocks forever.

The result: the CLI enforces permissions, the worktree bounds the blast radius, and
`safety.py` shrinks to a protected-path check on the `python` executor.

### Adapter interface

Six knobs — `mode`, `model`, `effort`, `session`, `output_format`, `schema`. Each
adapter is ~80 lines of argv construction. `capabilities.py`, `roles.py`,
`cost_aware.py`, and `intelligence.py` are deleted (~1,000 lines).

### Quota ledger

The rate-limit signals these CLIs emit are **unknown** and cannot be determined
without hitting limits. The design accommodates that rather than guessing.

Preference is configured, not inferred:

```yaml
executors:
  lead:      claude                 # reasoning: spend the expensive one
  implement: [agy, cursor, claude]  # mechanical: cheap first, failover rightward
```

The ledger:

1. **Logs every invocation** — executor, exit code, duration, first 200 chars of
   stderr — to `~/.polyphony/quota.jsonl`. Detection rules get written later from
   observed evidence rather than invented now.
2. **Fails over conservatively.** Only an explicit pattern list counts as a quota
   signal. An unrecognized failure is **never** treated as quota; failing over on a
   real bug would hide the bug and consume cheap subscriptions on broken work.
   Unknown failure surfaces and stops.

This is deliberately less clever than `cost_aware.py`. It makes an unknown visible
instead of pretending a heuristic resolved it.

### Smoke tests

Every flag above is *documented* as correct, not *demonstrated*. Each adapter needs
one real smoke test — prompt a scratch repository, assert exit 0 and non-empty
output — and these run **first**, because everything downstream assumes these
subprocesses behave.

---

## 4. Observability

`events.py` exists because a structured event stream is genuinely wanted. The
mistake was building it beside the loop rather than inside it. **One writer, two
renderers:** the loop emits events, stdout renders them for humans, `session.jsonl`
records them for tooling. This deletes `events.py`, `observability.py`,
`explain.py`, and `bundles.py` (~640 lines) while keeping what they reached for.

### Watched output

```
── iter 3/10 ─────────────────────────────── 2m14s elapsed
  claude   DELEGATE → agy
           Ranking bug is in tie-break ordering, not the score
           calculation. Narrowing to icd10/ranker.py:88-140.
  agy      ✓ 6.2s   ranker.py (+12 −4)
  pytest   ✓ 41 passed
```

The reasoning line is load-bearing: a wrong diagnosis is visible a full iteration
before a wrong diff is, which is what makes interruption useful.

### Completion summary

```
✓ COMPLETED  medicoder/task-a3f9   4 iterations   6m51s
  goal      fix the ICD-10 ranking tie-break bug
  changed   icd10/ranker.py, tests/ranking/test_order.py
  tests     41 passed
  executors agy ×3, claude ×4, python ×2

  review    git -C ~/.polyphony/worktrees/medicoder/task-a3f9 diff main
  keep      git merge --squash polyphony/task-a3f9 && git commit
  discard   polyphony clean task-a3f9
  full log  ~/.polyphony/runs/medicoder/task-a3f9/log.txt
```

In `review` mode, `changed` is replaced by the path to the document produced.

### Disk layout

Runs move out of the Polyphony repository so it stays clean and can serve many
projects:

```
~/.polyphony/
  worktrees/<project>/<task-id>/   isolated checkout + provisioned paths
  runs/<project>/<task-id>/
    state.json                     existing StateManager format, unchanged
    iterations/0001.json           existing pattern, unchanged
    session.jsonl                  structured events, written live
    log.txt                        verbatim copy of stdout
    summary.md                     the completion block; review-mode output
  quota.jsonl                      cross-project executor ledger
```

`state.py` retains its atomic-write machinery (tmp → `fsync` → backup rotation →
atomic rename, with iterations stored separately to avoid O(N²) I/O). Only
`root_dir` changes. This is the best-engineered file in the repository and is not
rewritten.

### CLI surface

27 commands → 8: `run`, `resume`, `status`, `log`, `project`, `doctor`, `migrate`,
`clean`.

Removed: `approve`, `reject`, `replay`, `events`, `explain`, `export`, `benchmark`,
`metrics`, `inspect`, `diff`, `watch`, `pause`, `abort`, `cancel`, `retry`. Each
either served a dead subsystem or is now one line in the completion summary.

---

## Deletions

Counts are disjoint — `intelligence.py`, `policy.py`, `worktrees.py`, and
`observability.py` are inside the 5,652 orphan total and are not counted again.

| Category | Lines | Rationale |
|---|---|---|
| 24 unreachable modules | 5,652 | Never executed, never validated |
| `capabilities` (82), `roles` (81), `cost_aware` (275) | 438 | Serve capability routing; quota arbitrage does not need them |
| `benchmarks/` | 396 | Fabricates results |
| `rollback.py` + checkpoint commits in `router.py` | ~350 | Replaced by worktree isolation |
| `bundles.py` (142), `explain.py` (207), `events.py` (202) | 551 | Replaced by one live event writer + summary block |
| `budgets.py` + cost model in `report.py` | ~310 | Fictional cost figures that gate real aborts |
| Most of `safety.py` | ~300 | Worktree + CLI permission modes replace it |
| 19 CLI commands | ~880 | Served dead subsystems |
| `docs/BASELINE_v0.1.0.md`, `docs/COMPATIBILITY_CONTRACT.md` | — | Contracts for a system that has never run |
| ~190 tests covering deleted modules | ~5,000 | Test deleted code |

**Total deleted: ~8,900 lines** of the current ~14,500.

## Retained unchanged

| Module | Lines | Rationale |
|---|---|---|
| `state.py` | 419 | Careful crash-safe persistence; a rewrite is pure loss |
| `context.py` | 474 | Competent prompt assembly; unvalidated, but replacing it would swap one guess for another |
| `executors/{base,claude,agy,cursor,python}.py` | ~900 | Sound structure; flag fixes only |
| `migrate/` | 1,054 | Self-contained and working |
| `models_config.py`, `doctor.py` | ~575 | Useful as-is |

## Rewritten as new files

To prevent "restructure" degrading into "patch," these are written as new files and
the originals deleted in the same commit:

| New | Replaces | Est. lines |
|---|---|---|
| `loop.py` | `main.py` (924) | ~250 |
| `session.py` | (new — worktree, provisioning, event emission) | ~250 |
| `gates.py` | (extracted from `main.py`) | ~100 |
| `quota.py` | `router.py` (420), `cost_aware.py` (275) | ~150 |
| `render.py` | `logging.py` (133), `report.py` (133) | ~200 |
| `cli.py` | `cli.py` (1,182 → 8 commands) | ~300 |

**Total new: ~1,250 lines** replacing ~3,100.

---

## Testing strategy

The current suite is 219 tests, ~190 of which cover deleted modules. Several
remaining ones are tautological — they assert the same constants the code was
written with, so they stay green through any change and catch nothing.

Replacement, in priority order:

1. **Adapter smoke tests (3).** Real subprocess invocation against a scratch repo.
   Everything else assumes these work; nothing has ever demonstrated it.
2. **Worktree + provisioning integration (1).** Create a worktree on a repo with a
   gitignored `env/`, provision, run the test command, assert it passes. This is
   the failure mode most likely to break `code` mode on day one.
3. **Loop tests with mocked executors.** Port the existing nine from
   `test_orchestrator_loop.py` — these genuinely exercise the loop.
4. **One test per gate.** Each is a small pure function; each gets a test that
   fails when the gate is removed.
5. **A reachability test.** Walk the import graph from the CLI entrypoint; fail if
   any module under `orchestrator/` is unreachable. ~20 lines, and it is what would
   have caught this entire situation months ago.

## Sequencing

Ordered so the riskiest unknowns surface first:

1. Adapter smoke tests + flag fixes. **If the subprocesses do not behave, nothing
   else matters.**
2. Session: worktree, provisioning, squash-merge handoff, push block.
3. Loop rewrite: `Step`, handlers, gates, ported guardrails.
4. Quota ledger (logging first; failover rules only once evidence exists).
5. Observability: renderers, summary, disk layout.
6. Deletions, CLI reduction, reachability test.
7. README rewritten to describe only what runs.

## Open questions

- **Cursor prompt delivery.** The adapter pipes via stdin; `cursor-agent` documents
  the prompt as a positional argument. Resolved by smoke test 1.
- **Quota signal patterns.** Unknown by construction. Resolved by reading
  `quota.jsonl` after a week of real use.
- **`review` substantiveness gate.** What counts as a real document versus an empty
  claim of success? Start with a word-count floor plus a non-empty-file check, and
  revise once a real run produces a bad review.
- **Model IDs.** `project.yaml` pins a stale Claude model. Current IDs to be
  confirmed at implementation time rather than guessed here.
