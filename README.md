# Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP server that lets the agent you're already working with hand a task to a
cheaper one. Your main agent (Claude Code, Codex, anything that speaks MCP) calls
`delegate`. Polyphony runs `agy`, `cursor-agent`, or `claude` on the task in a
private copy of your repository, and your agent reviews the diff before anything
touches the real one.

The point is quota. A Claude Max weekly limit runs out long before a cheap agy
plan or a team Cursor seat does, so mechanical work goes to those instead.

## Tools

| Tool | What it does |
|---|---|
| `executors(repo?)` | The pool in preference order: whether each CLI is available, its modes, its active jobs against its limit, and its last cached quota check |
| `delegate(instruction?, repo, executor?, mode?, timeout_minutes?, check?, brief_path?, model?)` | Start a job in a fresh copy of the repo. Returns a `job_id` at once, and in `skipped` any executors it passed over. `check` overrides the project's check command (`""` skips it) |
| `delegate_many(instruction?, repo, executors, mode?, timeout_minutes?, check?, brief_path?, models?)` | The same brief to several executors, one job each, to compare diffs. Spends quota on every one |
| `status(job_id, wait_seconds?)` | State and the tail of the agent's output so far; once finished, also changed files, diff stat, and the check's result and output tail. Can block up to 240s |
| `wait(job_ids, until?, wait_seconds?)` | Block until `any` (default) or `all` of several jobs finish, up to 240s: one call instead of `status` on each. Returns `done`, the `finished` and `active` ids, and `jobs`: finished ones in full as `status` gives them, active ones only as id, state, executor, and elapsed time. With `any`, an already finished job counts, so pass only the ids still awaited |
| `diff(job_id)` | The job's full diff |
| `apply(job_id, paths?)` | Stage the changes in your repo, uncommitted. `paths` takes only some files; a later call without it applies the rest. Refuses without touching anything on conflict |
| `apply_many(job_ids, dry_run?)` | Apply several whole jobs in order, all or none: each patch is checked on top of the ones before it, on scratch copies of the index, before anything lands. Returns `applied`, `not_applied`, `overlaps` (file: jobs), `unstaged`, `dry_run`, and `error` naming the job that would not apply. `dry_run` only reports |
| `revise(job_id, feedback, timeout_minutes?)` | Run the job's agent again in the same copy, on top of its last attempt, with your feedback. `diff` and `apply` then cover all attempts. Refused once any of it is applied |
| `discard(job_id)` | Delete the job's copy and record |
| `cancel(job_id)` | Kill a running job |
| `jobs()` | Recent jobs |
| `usage(executor?)` | agy's and cursor's remaining quota and reset times, as each CLI reports it. Refreshes the cache `delegate` reads |
| `stats()` | Per executor and model: jobs, succeeded, revised, applied, discarded, cancelled, check pass rate, median elapsed |
| `report(job_id, offset?, limit?)` | A finished `report`-mode job's report, `limit` (default 20000) characters from `offset`, with `total_chars` and `more` for paging |

`mode` is `code` (the agent may edit) or `review` (read-only). Each maps onto the
CLI's own permission mode. Nothing runs with permission checks bypassed.

`mode="report"` is an audit whose findings are a file: the agent is told to write
them as Markdown to `REPORT.md` at the copy's root and change nothing else. It
runs in the CLI's `code` mode, since writing a file needs edit permission, so a
review-only executor can't take it. The report is saved as the job's
`report.md`; `status` shows `report_path`, `report_chars`, and `stray_changes`
(files changed besides `REPORT.md`), and `report` reads it. A run that writes no
`REPORT.md` fails. So does one whose `REPORT.md` is a symlink, or is a file your
repository already tracks that the job left unchanged: an old report is never
passed off as the new one. If you track a `REPORT.md`, the agent has to rewrite
it. No check runs, and `apply` and `apply_many` refuse a report job.

With no `executor` named, `delegate` takes the first one in the project's `pool`
that is installed, supports the mode, is below its limit of active jobs, and is
not out of quota by its last usage report. Reports are cached for 5 minutes in
`~/.polyphony/usage-cache.json`, shared by every server, and a failed or
unreadable one never stops a delegation. A named executor is never skipped for
quota.

While a job runs, the agent's output streams to its `output.txt`, and `status`
shows the tail. In `code` mode, once the agent succeeds, the check command (the
project's `check`, or `delegate`'s) runs in the job's copy, and `status` reports
whether it passed. A failing check does not fail the job; you decide. The check
runs sandboxed (`sandbox-exec` on macOS, `bwrap` on Linux): it can write only in
the copy and a private `$TMPDIR`, with no network beyond loopback. Without a
sandbox it does not run.

A long brief can be cut short when passed inline, so `delegate` and
`delegate_many` also take `brief_path`: a UTF-8 file of at most 100 KB (relative
paths are from the repo). It is copied into the job at once as `brief.md`, and
the agent is told `instruction`, a blank line, then the brief; either may be
left out, not both. The whole task (instruction, brief, and report mode's
request) must stay under 120 KB, and `revise` refuses feedback that would take
it over: agy, cursor, gemini and opencode get the task as one command-line
argument, which Linux caps at 128 KiB. `status` reports `instruction_chars`, `instruction_sha256`,
and `instruction_tail` (the last 200 characters) of that task, before any
`revise` feedback, so you can check it arrived whole. `model` overrides the
project's model and needs `executor`, since a model belongs to one CLI
(`delegate_many` takes `models`, keyed by executor); `revise` keeps it.

A finished job is applied (all of it, or some files), revised, or discarded.
Each job's outcome goes once into `~/.polyphony/ledger.jsonl`, which outlives the
job, and `stats` summarizes it.

`codex`, `gemini`, and `opencode` adapters also exist, opt-in: they are never in
the default pool, so name them in a project's `pool` or pass `executor`. Their
flags come from each CLI's docs and have not been run against a real binary
(`docs/evidence/new-adapters-unverified.md`). `opencode` is review-only: its
edit-capable agent allows every tool, shell included, without asking.

## Guarantees

- The agent works in its own clone under `~/.polyphony/jobs/<job_id>/repo`. Nothing
  is written to your repository while a job exists: no branch, no worktree, no
  git objects. The clone has no remote, so the agent has no route to GitHub.
- The clone's git directory sits beside the copy, not in it, and Polyphony's own
  git commands there ignore anything the agent planted: hooks, config, and
  `.git` or `commondir` pointers to other repositories.
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
tool_timeout_sec = 300  # lets status(wait_seconds=240) finish
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
pool: [agy, cursor, claude]         # preference order when no executor is named
models:
  cursor: composer-2.5
check: .venv/bin/pytest -q          # run in the copy after a code job succeeds
check_timeout_minutes: 10           # default 10
max_parallel:                       # active jobs per executor, across all projects (default: no limit)
  agy: 2
allow_secrets: [.env.test]          # withheld secret-looking files the copy gets anyway (path or basename globs, any case)
env_scrub: [AWS_*, OPENAI_API_KEY]  # env vars kept from both the agent and the check
```

A repository with no config works too, just with no provisioning and the default
pool.

The copy never takes `node_modules` from the working tree (nor `env`, `.venv`,
or the other environments and caches), so a frontend check such as `npm test`
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
- `polyphony usage [agy|cursor]`: remaining quota, as each CLI reports it.
- `polyphony stats`: the ledger, per executor and model.
- `polyphony doctor`: which CLIs are installed, and which config applies to the
  repository in the current directory.

`polyphony gc --older-than 7d [--dry-run]` deletes finished jobs that ended longer
ago than that (`12h`, `30m` also work), applied or not, and prints what it freed.
Nothing is deleted automatically.

## Development

```bash
.venv/bin/pytest                 # unit and integration tests
.venv/bin/pytest -m smoke        # real CLI calls; uses subscription quota
.venv/bin/ruff check .
```

`docs/design.md` covers the design. `docs/evidence/` records what was verified
against the real CLIs.

## License

MIT. See [LICENSE](LICENSE).
