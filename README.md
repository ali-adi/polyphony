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
| `executors(repo?)` | Which agent CLIs are available right now, in preference order |
| `delegate(instruction, repo, executor?, mode?, timeout_minutes?)` | Start a job in a fresh copy of the repo. Returns a `job_id` at once |
| `status(job_id, wait_seconds?)` | State, and once finished: changed files, diff stat, output tail. Can block up to 240s |
| `diff(job_id)` | The job's full diff |
| `apply(job_id)` | Stage the changes in your repo, uncommitted. Refuses without touching anything on conflict |
| `discard(job_id)` | Delete the job's copy and record |
| `cancel(job_id)` | Kill a running job |
| `jobs()` | Recent jobs |
| `usage(executor?)` | agy's and cursor's remaining quota and reset times, as each CLI reports it |

`mode` is `code` (the agent may edit) or `review` (read-only). Each maps onto the
CLI's own permission mode. Nothing runs with permission checks bypassed.

## Guarantees

- The agent works in its own clone under `~/.polyphony/jobs/<job_id>/repo`. Nothing
  is written to your repository while a job exists: no branch, no worktree, no
  git objects. The clone has no remote, so the agent has no route to GitHub.
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

Optional, one file per repository in `projects/<name>/project.yaml`:

```yaml
name: medicoder
path: /absolute/path/to/repo
provision:                          # gitignored paths a fresh copy lacks
  - { path: env/, mode: clone }     # clone = APFS copy-on-write; link = symlink
pool: [agy, cursor, claude]         # preference order when no executor is named
models:
  cursor: composer-2.5
```

A repository with no config works too, just with no provisioning and the default
pool.

## Command line

`polyphony mcp` serves the tools on stdio. `polyphony usage [agy|cursor]`,
`polyphony jobs [JOB_ID]`, `polyphony discard JOB_ID`, and `polyphony doctor` are
for checking by hand.

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
