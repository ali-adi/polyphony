# Polyphony usage review and redesign decisions (2026-10-30)

## Evidence

Sources: `~/.polyphony` (88-row ledger, 19 job folders). 20 Claude Code sessions that called polyphony, from 09-29 to 10-30. About 60 sessions that did not call it, scanned for moments where another model's view was wanted. Raw transcript counts (206 `delegate`) are inflated by compaction replays. Deduplicated, there were 113 job ids and 9 delegate calls that errored.

### What landed
- Code mode applied 27 of 40 jobs: 82% of the jobs that succeeded. A passing check went with an apply in 26 of 28 jobs. A failing check went with an apply in 1 of 4.
- By executor and model:

  | Executor / model | Applied | Median time |
  |---|---|---|
  | cursor composer-2.5 | 10/11 | 284 s |
  | agy gemini-3.8-flash-low | 12/15 | 514 s |
  | cursor grok-4.7-high | 5/6 | 1320 s |
  | agy gemini-4-argon-high, code mode | 0/2 (both failed) | |

- Best fits:
  - Bulk translation: 7,975 phrases in 8 agy jobs of 20 to 40 s each.
  - About 25 refac-v3 builds from one spec (10-07).
  - A cursor regression review of Claude's own fixes found 9 regressions, 3 of them high (09-29).
- Code-mode use ran from 09-25 to 10-07 and on 10-21, while Claude limits were binding. Since then the only use has been Argon as an extra judge alongside Opus (10-29, 10-30).

### What failed
1. agy writes REPORT.md and then idles. Polyphony shows the job as running for 10+ minutes until someone cancels it (10-30, twice). A job with a 52 KB brief sat 11 minutes with no output (10-29). After a cancel, `report_path` is null.
2. Quota:
   - The gate is skipped when an executor is named, and the main agent always names one.
   - The usage cache was last written 10-22.
   - Argon was delegated at 1% weekly quota left.
   - A 429 killed 2 of 3 code jobs after about 25 minutes (10-21).
3. cursor review mode returned empty output 3 of 3 times (79 s, 159 s, 1180 s).
4. No pre-flight checks:
   - The invalid model name `gemini-4-argon` was accepted and run.
   - cursor showed `available: true` while logged out.
5. `wait_seconds=240` exceeds the roughly 120 s MCP limit, so calls were auto-backgrounded 4 times (10-07).
6. Disk:
   - 12 GB in 19 job folders, and gc has never run.
   - cancel never deletes a folder.
   - The overlay copies gitignored data into every copy: `results/` is 1.5 GB and `database/` is 214 MB.
7. Calling-agent misuse:
   - malformed JSON, 6 times
   - wrong parameter names
   - `diff` skipped; reports read with Bash
   - `apply_many` has no per-job `paths`
8. No progress is visible while a job runs. `worker.log` is 0 bytes in every job, and `output.txt` holds only the final message.

### Second-opinion demand outside polyphony
- About 37 cross-check moments, roughly 31 of them Claude-only.
- The non-Claude views came from grokbot (retired 10-13) and from Antigravity sessions the user drove.
- The highest-stakes medical-coding panels had no Argon seat:
  - 10-23 ground-truth label audit (3 Opus, 2-of-3 vote)
  - 10-23 six-stance panel
  - 10-26 label auditors and clarity judges

## Debate
Three Sonnet advocates argued two rounds: reliability, subtraction and economics. They converged on these points:
- stall and auto-finish detection in the executor loop
- the quota gate applied to named executors
- deleting review mode and the unverified adapters
- folding cancel into discard
- dropping the gitignored overlay
- keeping `apply_many`, which caught a real overlap on 10-21

They disagreed on two:
- usage.py: delete it, or extend it into the gate
- gates on task shape (brief size, a required check): the reliability advocate showed a 70 KB brief that produced 5 clean applies

## Decisions (grilling with the user)

| Branch | Decision |
|---|---|
| Purpose | Model diversity, especially Argon on medical coding. Claude quota rarely binds now. |
| Code mode | Keep and improve; limits may bind again |
| Executors | agy only. Cut cursor, claude, codex, gemini and opencode. |
| Read-only mode | Report only; delete review mode |
| Panels | Claude orchestrates. Polyphony runs one non-Claude job per call, so `delegate_many` goes. |
| Gemini quota | Hard gate at 5% or less per model, even when named. Tiering lives in project config, set per mode: medicoder report jobs default to Argon, code jobs to 3.8 flash, and other projects use flash. `config.py` today only has a model per executor, so this needs a mode key. |
| Speed and visibility | Auto-finish idle report jobs and fail stalls; live heartbeat via agy `--output-format stream-json`; macOS notification on finish |
| PHI | `results/` is de-identified or synthetic, so copying it is acceptable. Disk is fixed by deleting on resolve. |
| Cleanup | Delete the job folder on discard, cancel and apply; auto-gc unresolved jobs older than 7 days; delete the existing 19 folders now |
| Argon adoption | Claude Code mod: a PreToolUse reminder on Agent and Workflow calls whose prompt mentions judge, audit, ground truth, label or verdict: "add one polyphony Argon seat (flash if gated)". A reminder by design, not a block. |

## Work list
1. Executor loop in `executors/base.py`:
   - Report mode finishes when REPORT.md has changed and then stays stable for about 120 s.
   - Any mode fails as "stalled; partial kept" when CPU time and the newest mtime stay flat for about 600 s.
   - Keep `report_path` when a job ends this way.
2. agy stream-json: `status` and `wait` show elapsed time, the files the agent touched, and its last events. Send a macOS notification when a job ends.
3. Per-model quota gate in `server.delegate` for named executors, refusing at 5% or less. Pass `model` through project config. Fix the stale path in `projects/medicoder/project.yaml`.
4. Cut the cursor, claude, codex, gemini and opencode adapters, review mode, `delegate_many`, and the cursor PTY quota scraper. With only agy left, also collapse the executor registry, the pool order, `_choose`, the `executor` parameter and the `executors` tool. One implementation needs no interface. This also gives up cursor composer-2.5, the best code performer (10/11 applied).
   - Check agy's stream-json for a final result event first. If it has one, it is the done-signal and item 1 shrinks to the stall killer.
5. `discard`, `cancel` and `apply` delete the job folder. Run gc on unresolved jobs older than 7 days when a job is created.
6. Set `MAX_WAIT_SECONDS` to 100; add per-job `paths` to `apply_many`.
7. Update SKILL.md and the README to match.
8. The Argon reminder hook in the Claude Code mod is a separate change and lives outside this repo.
