# Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP server that lets the agent you're already working with hand a task to
Antigravity (`agy`, Gemini models). Your main agent (Claude Code, Codex, anything
that speaks MCP) calls `delegate`. Polyphony runs `agy` on the task in a private
copy of your repository, and your agent reads the report or reviews the diff
before anything touches the real one.

The point is model diversity: a Gemini seat (Argon, say) on judgements a panel of
Claude agents would otherwise make alone, and mechanical code work done off
Claude's quota when that binds.

## Tools

| Tool | What it does |
|---|---|
| `delegate(instruction?, repo, mode?, timeout_minutes?, check?, brief_path?, model?)` | Start a job in a fresh copy of the repo. Returns a `job_id` at once. `model` overrides the project's model for the mode. `check` overrides the project's check command (`""` skips it). `timeout_minutes` (default 30) is at most 1440 |
| `status(job_id, wait_seconds?)` | State; agy's latest steps (`recent`) and, while it runs, the files it has touched; once finished, agy's final `response`, changed files, diff stat, and the check's result and output tail. Can block up to 100s |
| `wait(job_ids, until?, wait_seconds?)` | Block until `any` (default) or `all` of several jobs finish, up to 100s: one call instead of `status` on each. Returns `done`, the `finished` and `active` ids, and `jobs`: finished ones in full as `status` gives them, active ones as id, state, elapsed time, and their last steps and touched files. With `any`, an already finished job counts, so pass only the ids still awaited |
| `diff(job_id)` | The job's full diff |
| `apply(job_id, paths?)` | Stage the changes in your repo, uncommitted. `paths` takes only some files; a later call without it applies the rest. Refuses without touching anything on conflict. Once every file is applied, the job is deleted |
| `apply_many(job_ids, dry_run?, paths?)` | Apply several jobs in order, all or none: each patch is checked on top of the ones before it, on scratch copies of the index, before anything lands. `paths` maps a job id to the only files of it to apply. Returns `applied`, `not_applied`, `overlaps` (file: jobs), `unstaged`, `dry_run`, and `error` naming the job that would not apply. If the repository changes while the jobs land, `error` can come with some jobs already in `applied`. `dry_run` only reports |
| `revise(job_id, feedback, timeout_minutes?)` | Run agy again in the same copy, on top of its last attempt, with your feedback. `diff` and `apply` then cover all attempts. Refused once any of it is applied |
| `discard(job_id)` | Delete the job's copy and record |
| `cancel(job_id)` | Kill a running job and delete it |
| `jobs()` | Recent jobs |
| `usage()` | agy's remaining quota per model group and window, with reset times. Refreshes the cache `delegate` reads |
| `stats()` | Per executor and model: jobs, succeeded, revised, applied, discarded, cancelled, check pass rate, median elapsed |
| `report(job_id, offset?, limit?)` | A finished `report`-mode job's report, `limit` (default 20000) characters from `offset`, with `total_chars` and `more` for paging |

`mode` is `code` (the agent may edit) or `report`. agy always runs as
`agy -p --mode accept-edits --sandbox --output-format stream-json`: its own edit
policy, with its terminal sandboxed.

`mode="report"` is an audit whose findings are a file: the agent is told to write
them as Markdown to `REPORT.md` at the copy's root and change nothing else. The
report is saved as the job's `report.md`; `status` shows `report_path`,
`report_chars`, and `stray_changes` (files changed besides `REPORT.md`), and
`report` reads it. A run that writes no `REPORT.md` fails. So does one whose
`REPORT.md` is a symlink or a hard link, or is one that was already there and the
run left unchanged (one your repository has, or an earlier attempt's before a
`revise`): an old report is never passed off as the new one. If your working tree
has a `REPORT.md`, the agent has to rewrite it; a gitignored one is left out of
the job's copy. Only the first 5 MB of a report are kept (`status` then shows
`report_truncated`). No check runs, and `apply` and `apply_many` refuse a report
job.

The model is `delegate`'s `model`, else the project's for the mode (see Project
config), else `gemini-3.8-flash-low`. Before every `delegate` and `revise`,
Polyphony reads agy's `/usage` (cached for 5 minutes in
`~/.polyphony/usage-cache.json`, shared by every server) and refuses a model whose
quota group (Gemini 4 Argon, Gemini Models, Claude and GPT models) has a window at
5% or less, naming its reset time. A usage check that fails does not block the
job; the result says `quota_unknown`.

While a job runs, agy's event stream goes to its `output.txt`. agy's final
`result` event ends the run: agy gets 10 seconds to exit and is then stopped, so
a run that idles after finishing does not hold the job. A run with no new output
and no CPU use for 10 minutes is stopped as stalled; the job fails but keeps its
diff and any report. On macOS a notification is posted when a job ends.

In `code` mode, once the agent succeeds, the check command (the project's
`check`, or `delegate`'s) runs in the job's copy, and `status` reports whether it
passed. A failing check does not fail the job; you decide. The check runs
sandboxed (`sandbox-exec` on macOS, `bwrap` on Linux): it can write only in the
copy and a private `$TMPDIR`, with no network beyond loopback. On Linux that
network rule does not cover Unix sockets, so `/run`, `/var/run`, `/tmp` and
`/var/tmp` are hidden from it (Docker, D-Bus, ssh-agent, tmux and X11 sockets
live there), and it gets its own PID namespace, so it cannot see or signal your
processes. A Unix socket elsewhere, such as under your home directory, is still
reachable. Without a sandbox it does not run.

A long brief can be cut short when passed inline, so `delegate` also takes
`brief_path`: a UTF-8 file of at most 100 KB (relative paths are from the `repo`
directory as given). It is copied into the job at once as `brief.md`, and the
agent is told `instruction`, a blank line, then the brief; either may be left
out, not both. The whole task (instruction, brief, and report mode's request)
must stay under 120 KB and hold no NUL byte, and `revise` refuses feedback that
would break either: agy gets the task as one command-line argument, which Linux
caps at 128 KiB. `status` reports `instruction_chars`, `instruction_sha256`, and
`instruction_tail` (the last 200 characters) of that task, before any `revise`
feedback, so you can check it arrived whole. `revise` keeps the job's model.

A finished job is applied (all of it, or some files), revised, or discarded; a
running one can be cancelled. Applying in full, discarding and cancelling delete
the job's folder. `delegate` also deletes any job left unresolved for 7 days.
Each job's outcome goes once into `~/.polyphony/ledger.jsonl`, which outlives the
job, and `stats` summarizes it.

## Guarantees

- The agent works in its own clone under `~/.polyphony/jobs/<job_id>/repo`. Nothing
  is written to your repository while a job exists: no branch, no worktree, no
  git objects. The clone has no remote, so the agent has no route to GitHub.
- The clone's git directory sits beside the copy, not in it, and Polyphony's own
  git commands there ignore anything the agent planted: hooks, config, and
  `.git` or `commondir` pointers to other repositories. A symlink anywhere in
  that git directory (an `index` or `objects` pointing into your repository,
  say) fails the job rather than letting git write through it.
- Nothing lands until you call `apply`, and `apply` only stages. You commit.
  It applies a patch, so the job's internal commit never enters your history.
- Secret-looking files the copy would otherwise take from your working tree
  (untracked or gitignored `.env`, `.env.*` but not `.env.example`, `*.env`,
  `.envrc`, private keys, `.netrc`, `.npmrc`, `credentials.json`, and so on;
  `SECRET_PATTERNS` in `workspace.py`) are withheld, at any depth and in any
  case (`.ENV` too), and `status` lists them as `withheld`. A secret you have
  committed is in the clone regardless, but only as committed: your
  uncommitted edits to it are withheld too.
- `diff` shows exactly what `apply` stages: both read the commit the job's run
  ended on, not whatever the copy holds later, and neither follows your git
  diff settings (`diff.noprefix`, `diff.external`, ...) or the agent's
  `.gitattributes`.
- The check does not see credential-looking environment variables (`*_API_KEY`,
  `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `*_CREDENTIALS`). The agent keeps them,
  since its CLI may authenticate with one; `env_scrub` removes others from both.
- Polyphony refuses `git push` before spawning git.
- Jobs run in a detached process and survive the client disconnecting. State is
  in `~/.polyphony/jobs/`, so any MCP client can check any job.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/polyphony doctor
```

**Claude Code:**

```bash
claude mcp add --scope user polyphony -- /absolute/path/to/.venv/bin/polyphony mcp
```

**Codex** (`~/.codex/config.toml`):

```toml
[mcp_servers.polyphony]
command = "/absolute/path/to/.venv/bin/polyphony"
args = ["mcp"]
tool_timeout_sec = 300
```

`integrations/delegate/SKILL.md` teaches the calling agent when to delegate and how
to review the result. Link it into your agent's skills directory.

## Project config

Optional. Polyphony looks in three places and the first match wins:

1. `.polyphony.yaml` at the repository root. `name` and `path` are optional
   there and default to the repository itself.
2. `~/.polyphony/projects/<name>/project.yaml` (or under `$POLYPHONY_HOME`),
   matched by `path`.
3. `projects/<name>/project.yaml` in a Polyphony source checkout. Legacy; it
   only exists with an editable install.

`polyphony mcp --projects-dir DIR` searches DIR instead of 2 and 3.
`polyphony doctor`, run inside a repository, prints which file applies.

```yaml
name: medicoder                     # 2 and 3 need name and path
path: /absolute/path/to/repo
provision:                          # gitignored paths a fresh copy lacks
  - { path: env/, mode: clone }     # clone = APFS copy-on-write; link = symlink
models:                             # agy model per mode (default: gemini-3.8-flash-low)
  report: gemini-4-argon-high
  code: gemini-3.8-flash-low
check: .venv/bin/pytest -q          # run in the copy after a code job succeeds
check_timeout_minutes: 10           # default 10
max_parallel: 2                     # active jobs across all projects (default: no limit)
allow_secrets: [.env.test]          # withheld secret-looking files the copy gets anyway (path or basename globs, any case)
env_scrub: [AWS_*, OPENAI_API_KEY]  # env vars kept from both the agent and the check
```

A repository with no config works too, just with no provisioning and the default
models.

A provision `path` is one path from the repository root (`./data/` and `data`
are the same), so provisioning `models` leaves an untracked `src/models/` alone.

The copy never takes `node_modules` from the working tree (nor caches such as
`__pycache__`, nor environments: an `env`, `venv` or `.venv` directory at the
repository root, or one anywhere holding `pyvenv.cfg` or `conda-meta/`; a
`src/env/` of source is copied), so a frontend check such as `npm test`
fails there unless the project provisions it:
`provision: [{ path: node_modules, mode: clone }]` gives each job its own copy
(copy-on-write on APFS, a full copy elsewhere). `mode: link` symlinks yours
instead: instant and free on disk, but the agent's installs then write into your
real `node_modules`, and the sandboxed check sees it read-only, so a tool that
caches inside it (`node_modules/.cache`) may fail there.

## Command line

`polyphony mcp` serves the tools on stdio. The rest are for checking by hand:

- `polyphony jobs [JOB_ID]`: recent jobs and the disk they use, or one job with
  its check, attempts, and applied files.
- `polyphony discard JOB_ID`
- `polyphony report JOB_ID`: a report-mode job's whole report.
- `polyphony usage`: agy's remaining quota.
- `polyphony stats`: the ledger, per executor and model.
- `polyphony doctor`: whether agy is installed, and which config applies to the
  repository in the current directory.

`polyphony gc --older-than 7d [--dry-run]` deletes finished jobs that ended longer
ago than that (`12h`, `30m` also work), applied or not, and prints what it freed.

## Development

```bash
.venv/bin/pytest                 # unit and integration tests
.venv/bin/pytest -m smoke        # real agy /usage call; spends no model quota
.venv/bin/ruff check .
```

`docs/design.md` covers the design. `docs/evidence/` records what was verified
against the real CLIs, and `usage-review-2026-10.md` why Polyphony is agy-only.

## License

MIT. See [LICENSE](LICENSE).
