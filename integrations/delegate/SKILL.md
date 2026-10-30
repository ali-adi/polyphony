---
name: polyphony-delegate
description: Hand a task to Antigravity (agy, Gemini models) through the Polyphony MCP tools, then review and apply or read the result. Use when the polyphony tools are connected and you want a non-Claude seat on a judgement (a report-mode audit, a judge or label panel), or a well-specified mechanical code change done off your quota.
---

# Delegating through Polyphony

agy is a separate agent working in a private copy of the repository. It sees only the
task you write: none of this conversation, none of your notes. Nothing it does
reaches the repository until you `apply`.

## 1. Decide

Two kinds of job:

- **Report** (`mode="report"`): an audit, review or verdict whose findings agy writes
  to `REPORT.md`. This is the non-Claude seat: on a panel of Claude judges or
  auditors, add one Argon report job (`model="gemini-4-argon-high"`), and use a flash
  model when Argon's quota is gated. You orchestrate the panel; Polyphony runs one
  job per call.
- **Code** (`mode="code"`): work you could specify completely in a brief, such as a
  mechanical change across files, a fix with a known cause, or tests for existing
  behaviour. Keep work whose next step depends on judgement you hold here.

## 2. Write the brief

The task is a **self-contained brief**: the goal, the files involved, the
constraints (style, what to leave alone), the command that proves it works, and
what done looks like. Done when a competent stranger could finish it from the
brief alone.

Anything over a few paragraphs goes in a file passed as `brief_path` (with a
one-line `instruction`, or none), then check that `instruction_chars` and
`instruction_tail` in the result match what you wrote. The file is copied at
delegate time. A brief is at most 100 KB and the whole task under 120 KB; for
more, point the agent at files in the repository.

## 3. Delegate and wait

1. `delegate(instruction, repo=<repository root>, mode=...)`. `model` defaults to the
   repository's model for the mode. A model at or below 5% quota is refused with its
   reset time; pick another model or wait. `quota_unknown` in the result means the
   quota could not be read and the job ran anyway. In code mode, pass the brief's
   check command as `check` unless the repository configures one.
2. `status(job_id, wait_seconds=90)` until `state` is `succeeded`, `failed`, or
   `died`. While it runs, `recent` shows agy's latest steps and `files_touched` what
   it has changed so far; `cancel` a job that is plainly off track (this deletes it).
   A job with no output and no CPU use for 10 minutes fails as stalled, keeping its
   partial work and report.
3. With more than one job out, `wait(job_ids=[...], wait_seconds=90)` returns as soon
   as any finishes (`until="all"` waits for every one). Handle the `finished` ones,
   then wait again on the ids still `active`.

## 4. Read a report

`report(job_id)`, paging with `offset` while `more` is true. `response` in `status`
is agy's closing message; the report is the product. A non-empty `stray_changes`
means agy edited other files too: the report can still stand, but there is nothing
to apply, so save the report where the user wants it and `discard`. If the
repository already has a `REPORT.md`, tell agy to overwrite it: one left unchanged
is not taken as the report.

## 5. Review code like a pull request

1. `diff(job_id)` and read every hunk. Scope creep, deleted tests, and edits outside
   the brief are grounds to discard.
2. `check_passed: true` means the check passed in the job's copy; with `false`, read
   `check_output_tail`. With no check reported, run the brief's check in the job's
   `workdir`.
3. `apply(job_id)`: the changes land **staged, not committed**, and the job is
   deleted. `apply(job_id, paths=[...])` takes only the good files and keeps the job
   for the rest; `discard` it when you are done. Tell the user what is staged;
   committing is theirs.

After a fan-out of separate code tasks to one repository, land the good ones with
`apply_many(job_ids=[...])`: it checks every patch on top of the ones before it and
applies all or none. `paths={job_id: [...]}` limits a job to its good files. Run it
with `dry_run=true` first to see `overlaps` (files more than one job touched: read
those hunks together) and `unstaged` (jobs that will land over the user's own
edits). On `error`, it names the job that does not fit; with `applied` empty
nothing changed, otherwise the jobs in `applied` are already staged. Call it again
without the failing job, then fix that one by hand.

Done when every hunk is read, the check passed, and the job is applied or discarded.

## 6. When it fails

Read `error` and `recent`.

- **Quota or agy problem** (refused for quota, `died`): `usage()` shows every model
  group's quota; delegate again with a model that has some.
- **Wrong work**: before applying anything, `revise(job_id, feedback)` once, with
  specific feedback: what is wrong, where, and what right looks like. The agent keeps
  its previous changes, the check runs again, and the diff covers both attempts. If
  the second attempt is also wrong, `discard` and do the task yourself.
- **Missing secret**: `withheld` in `status` lists secret-looking files kept out of
  the copy. If the failure comes from one, tell the user; only they should add it to
  `allow_secrets` in the project config.

Unresolved jobs are deleted after 7 days.
