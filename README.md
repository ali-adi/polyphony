# Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP server that lets the agent you're already working with hand a task to
Antigravity (`agy`, Gemini models). Your agent calls `delegate`; Polyphony runs
`agy` in a private copy of your repository; your agent reads the report or
reviews the diff before anything touches the real one. Use it for a Gemini seat
on a judgement (a report-mode audit) and for mechanical code changes.

## Tools

| Tool | What it does |
|---|---|
| `delegate(instruction?, repo, mode?, timeout_minutes?, check?, brief_path?, model?)` | Start a `code` or `report` job in a fresh copy of the repo; returns a `job_id` at once. A model at 5% quota or less is refused |
| `status(job_id, wait_seconds?)` | State, agy's recent steps and touched files, and once finished its response, changed files and check result. Blocks up to 100 s |
| `wait(job_ids, until?, wait_seconds?)` | Block until `any` or `all` of several jobs finish, up to 100 s |
| `report(job_id, offset?, limit?)` | A report job's `REPORT.md`, paged |
| `diff(job_id)` | The job's full diff |
| `apply(job_id, paths?)` | Stage the changes, uncommitted; deletes the job once all of it is applied |
| `apply_many(job_ids, dry_run?, paths?)` | Apply several jobs in order, all or none |
| `revise(job_id, feedback, timeout_minutes?)` | Run agy again in the same copy with your feedback |
| `discard(job_id)` / `cancel(job_id)` | Delete a finished job / kill and delete a running one |
| `jobs()` / `usage()` / `stats()` | Recent jobs / agy's quota per model group / outcomes from the ledger |

Jobs left unresolved for 7 days are deleted on the next `delegate`.

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

Link `integrations/delegate/SKILL.md` into your agent's skills directory.

## Project config

Optional. The first match wins: `.polyphony.yaml` at the repository root (`name`
and `path` default to the repository), then `~/.polyphony/projects/<name>/project.yaml`
matched by `path`. `polyphony doctor` prints which file applies.

```yaml
name: medicoder
path: /absolute/path/to/repo
provision:                          # gitignored paths a fresh copy lacks
  - { path: env/, mode: clone }     # clone = copy-on-write; link = symlink
models:                             # agy model per mode (default: gemini-3.8-flash-low)
  report: gemini-4-argon-high
  code: gemini-3.8-flash-low
check: .venv/bin/pytest -q          # run sandboxed in the copy after a code job succeeds
check_timeout_minutes: 10
max_parallel: 2                     # active jobs across all projects (default: no limit)
allow_secrets: [.env.test]          # withheld secret-looking files the copy gets anyway
env_scrub: [AWS_*, OPENAI_API_KEY]  # env vars kept from both the agent and the check
```

## Command line

`polyphony mcp` serves the tools on stdio. `polyphony jobs [JOB_ID]`, `discard`,
`report`, `usage`, `stats`, `doctor` and `gc --older-than 7d [--dry-run]` are for
checking by hand.

## Development

```bash
.venv/bin/pytest                 # unit and integration tests
.venv/bin/pytest -m smoke        # real agy /usage call; spends no model quota
.venv/bin/ruff check .
.venv/bin/vulture
```

## License

MIT. See [LICENSE](LICENSE).
