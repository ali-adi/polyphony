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
| `delegate(instruction, repo, executor?, mode?, timeout_minutes?, check?)` | Start a job in a fresh copy of the repo. Returns a `job_id` at once, and in `skipped` any executors it passed over. `check` overrides the project's check command (`""` skips it) |
| `delegate_many(instruction, repo, executors, mode?, timeout_minutes?, check?)` | The same brief to several executors, one job each, to compare diffs. Spends quota on every one |
| `status(job_id, wait_seconds?)` | State and the tail of the agent's output so far; once finished, also changed files, diff stat, and the check's result and output tail. Can block up to 240s |
| `wait(job_ids, until?, wait_seconds?)` | Block until `any` (default) or `all` of several jobs finish, up to 240s: one call instead of `status` on each. Returns `done`, the `finished` and `active` ids, and `jobs`: finished ones in full as `status` gives them, active ones only as id, state, executor, and elapsed time. With `any`, an already finished job counts, so pass only the ids still awaited |
| `diff(job_id)` | The job's full diff |
| `apply(job_id, paths?)` | Stage the changes in your repo, uncommitted. `paths` takes only some files; a later call without it applies the rest. Refuses without touching anything on conflict |
| `revise(job_id, feedback, timeout_minutes?)` | Run the job's agent again in the same copy, on top of its last attempt, with your feedback. `diff` and `apply` then cover all attempts. Refused once any of it is applied |
| `discard(job_id)` | Delete the job's copy and record |
| `cancel(job_id)` | Kill a running job |
| `jobs()` | Recent jobs |
| `usage(executor?)` | agy's and cursor's remaining quota and reset times, as each CLI reports it. Refreshes the cache `delegate` reads |
| `stats()` | Per executor and model: jobs, succeeded, revised, applied, discarded, cancelled, check pass rate, median elapsed |

`mode` is `code` (the agent may edit) or `review` (read-only). Each maps onto the
CLI's own permission mode. Nothing runs with permission checks bypassed.

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
```

A repository with no config works too, just with no provisioning and the default
pool.

## Command line

`polyphony mcp` serves the tools on stdio. The rest are for checking by hand:

- `polyphony jobs [JOB_ID]`: recent jobs and the disk they use, or one job with
  its check, attempts, and applied files.
- `polyphony discard JOB_ID`
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
