---
name: polyphony-delegate
description: Delegate a coding task or read-only review to a cheaper agent CLI (agy, cursor, claude) through the Polyphony MCP tools, then review and apply the result. Use when the polyphony tools are connected and a task is mechanical, long, or read-heavy enough to hand off.
---

# Delegating through Polyphony

The executor is a separate agent working in a private copy of the repository. It sees only the
instruction you write: none of this conversation, none of your notes. Nothing it
does reaches the repository until you `apply`.

## 1. Decide

Delegate work you could specify completely in a brief: a mechanical change across
files, a well-understood fix with a known cause, tests for existing behaviour, a
codebase review, notes. Keep work whose next step depends on judgement you hold
here: design choices, bugs whose cause is still unknown, anything the user is
steering turn by turn.

## 2. Write the brief

The `instruction` is a **self-contained brief**: the goal, the files involved, the
constraints (style, what to leave alone), the command that proves it works, and
what done looks like. Done when a competent stranger could finish the task from the
brief alone.

Anything over a few paragraphs goes in a file, passed as `brief_path` (with a
one-line `instruction`, or none): a long inline `instruction` can be cut short
on the way. Then check that `instruction_chars` and `instruction_tail` in the
result match what you wrote. The file is copied when you delegate, so editing
it afterwards changes nothing. A brief is at most 100 KB and the whole task
under 120 KB; for more, have the brief point the agent at files in the
repository. Pass `model` only when the user asked for one; it is refused
without `executor`, since a model belongs to one CLI.

## 3. Delegate and wait

1. `delegate(instruction, repo=<repository root>, mode="code")`, or
   `mode="review"` for read-only work. Leave `executor` unset unless the user
   named one: the first executor with quota and a free slot is used, and
   `skipped` says what was passed over. In code mode, pass the brief's check
   command as `check` unless the repository already configures one.
   For a risky change where two independent attempts are worth twice the quota,
   `delegate_many(instruction, repo, executors=[...])` runs the same brief on
   each; compare the diffs, apply at most one, and discard the rest.
2. `status(job_id, wait_seconds=240)`, repeated until `state` is `succeeded`,
   `failed`, `cancelled`, or `died`. `output_tail` shows progress while it runs;
   `cancel` a job that is plainly off track. Carry on with other work between
   calls if there is any.
3. With more than one job out (several delegates, or `delegate_many`), don't
   poll each with `status`: `wait(job_ids=[...], wait_seconds=240)` returns as
   soon as any of them finishes (`until="all"` waits for every one). Handle the
   `finished` ones, then call `wait` again with only the ids still `active`,
   since a job already finished ends an `any` wait at once.

## 4. Review like a pull request

On `succeeded` in code mode:

1. `diff(job_id)` and read every hunk. Scope creep, deleted tests, and edits
   outside the brief are grounds to discard.
2. If `status` shows `check_passed: true`, the check already passed in the
   job's copy; don't run it again. If it shows `false`, read `check_output_tail`.
   With no check reported, run the brief's check command inside the job's
   `workdir` (from `status`).
3. `apply(job_id)`: the changes land **staged, not committed**. When most files
   are right and a few are not, `apply(job_id, paths=[...])` with only the good
   ones and fix the rest yourself. Then `discard(job_id)`. Tell the user what is
   staged; committing is theirs.

After a fan-out of separate tasks to one repository, review each diff as above,
then land the good ones together with `apply_many(job_ids=[...])` rather than
one `apply` at a time: it checks every patch on top of the ones before it and
applies all or none, so two jobs that conflict are found before either lands.
Run it with `dry_run=true` first to see `overlaps` (files more than one job
touched: read those hunks together) and `unstaged` (jobs that will land unstaged
over the user's own edits). On `error`, it names the job that does not fit; if
`applied` is empty, nothing changed, and otherwise the jobs in `applied` are
already staged (the repository changed while it ran), so leave them out next
time. Call `apply_many` again without the failing job, then apply that one's work by
hand or delegate it again on top (its copy never sees the other jobs, so
`revise` cannot fix a conflict with them). Not for `delegate_many` results, which are alternatives: apply one.

Done when every hunk is read, the check passed (by you or as `check_passed`),
and the job is applied or discarded.

In review mode the product is `output_tail` (the full text is at `output_path`).
`files_changed` is empty. `discard` when you have what you need.

For an audit whose findings you want as a document, use `mode="report"` rather
than `review`, and don't ask for a file in the brief: Polyphony tells the agent to
write `REPORT.md`. If the repository already tracks a `REPORT.md`, tell the
agent to overwrite it: one left unchanged is not taken as the report, and the
job fails. On `succeeded`, read it with `report(job_id)`, paging with
`offset` while `more` is true. A non-empty `stray_changes` means the agent edited
other files too; the report can still stand, but `apply` is refused, so save the
report where the user wants it yourself, then `discard`.

## 5. When it fails

Read `error` and `output_tail`.

- **Executor problem** (out of quota, unavailable, `died`): `discard` and
  delegate again with `executor` unset. An executor out of quota by its last
  usage report is skipped; `usage()` refreshes those reports.
- **Wrong work**: before applying anything, `revise(job_id, feedback)` once, with
  specific feedback: what is wrong, where, and what right looks like. The agent
  keeps its previous changes, the check runs again, and the diff covers both
  attempts, so review it all again. If the second attempt is also wrong,
  `discard` and do the task yourself.
- **Missing secret**: `withheld` in `status` lists secret-looking files (`.env`,
  keys) kept out of the copy; a committed one is there, but without the user's
  uncommitted edits to it. If the failure comes from one being missing, tell
  the user; only they should add it to `allow_secrets` in the project config.
