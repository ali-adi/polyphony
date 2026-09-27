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

## 3. Delegate and wait

1. `delegate(instruction, repo=<repository root>, mode="code")`, or
   `mode="review"` for read-only work. Leave `executor` unset so the cheapest
   available one is used, unless the user named one.
2. `status(job_id, wait_seconds=240)`, repeated until `state` is `succeeded`,
   `failed`, `cancelled`, or `died`. Carry on with other work between calls if
   there is any.

## 4. Review like a pull request

On `succeeded` in code mode:

1. `diff(job_id)` and read every hunk. Scope creep, deleted tests, and edits
   outside the brief are grounds to discard.
2. Run the brief's check command inside the job's `workdir` (from `status`).
3. `apply(job_id)`: the changes land **staged, not committed**. Then
   `discard(job_id)`. Tell the user what is staged; committing is theirs.

Done when every hunk is read, the check passed in the `workdir`, and the job is
applied or discarded.

In review mode the product is `output_tail` (the full text is at `output_path`).
`files_changed` is empty. `discard` when you have what you need.

## 5. When it fails

Read `error` and `output_tail`.

- **Executor problem** (out of quota, unavailable, `died`): `discard`, check
  `usage()` for which executor still has quota, and delegate again with it.
- **Wrong work**: `discard`, sharpen the brief once, and delegate again. If the
  second attempt is also wrong, do the task yourself.
