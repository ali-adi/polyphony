# Polyphony design

## Why it is shaped this way

Polyphony started as an orchestrator: a loop that ran Claude as the lead and
drove `agy` and `cursor-agent` underneath it. None of that loop had ever run, and
it duplicated what the user's own agent already does well: planning, reviewing,
and deciding what to do next.

So the roles are reversed. The agent the user is already working with is the
lead. Polyphony is an MCP server offering a **pool** of cheaper executors. The
goal is quota: Claude Max weekly limits are the binding constraint, agy is cheap,
and cursor-agent is free on a team plan. Executor choice is a preference order,
not capability routing. There is no evidence behind any "agent X is better at Y"
rule.

Because the protocol is MCP and every tool describes itself without naming a
client, switching the lead (to Codex, say) means registering the same server
there. State lives in `~/.polyphony/`, not in any client's session.

## Components

| Module | Role |
|---|---|
| `executors/` | One adapter per CLI: binary discovery, argv for `review` and `code` modes, and failures a CLI reports while exiting 0 |
| `workspace.py` | A job's private clone of the repo, provisioning of gitignored paths |
| `guard.py` | The only way git is spawned. Refuses `push` before a process exists |
| `config.py` | Per-repository provisioning, pool order, models |
| `jobs.py` | Job records, launch, cancel, snapshot, diff, apply, discard |
| `worker.py` | The detached process that runs one job |
| `usage.py` | Remaining quota, read from each CLI's own report |
| `server.py` | MCP tools: thin wrappers over `jobs.py` and `usage.py` |
| `cli.py` | `mcp`, plus `jobs`, `discard`, `doctor` for a human |

## Decisions that are not obvious from the code

**No automatic failover.** When a job fails, the lead reads why and decides
whether to re-delegate. An automatic rule would have to tell quota exhaustion
apart from real bugs using output patterns nobody has observed yet. Failing over
on a real bug would hide it and spend cheap quota on broken work.

**The worker double-forks.** The server is long-lived. If it were the worker's
parent, a worker that died would linger as a zombie, `os.kill(pid, 0)` would keep
succeeding, and `died` would never be detected. `launch()` waits on an
intermediate process that exits at once, so the real worker is reparented to
init. The worker records its process group, and `cancel` kills the group, which
takes the executor with it. On macOS, signalling a group that is still being
reaped briefly returns `EPERM` before `ESRCH`, so treating `EPERM` as alive only
delays `died` by a poll.

**A private clone, not a git worktree.** A worktree writes a branch, a worktree
record and commit objects into the user's repository, and shares its `origin`.
So an agent with a shell could push with the user's GitHub remote. Each job
instead gets `git clone --no-hardlinks` into its own directory, with the remote
removed. The user's repository is read once and written only by `apply`. The
clone must not share object files with the repository (`--local`'s default hard
links would). Git refreshes the timestamps of objects a commit reuses, which
would reach through a hard link. An agent writing into an object file would
corrupt both. A full copy of medicoder's `.git` is 87 MB and takes under a
second. Tests hash every file in the source repository before and after a job to
hold this.

**Snapshot commits.** After the executor finishes, the worker commits in the
clone, so `diff` and `apply` work from git rather than from filesystem
timestamps. Plain `git add -A` skips gitignored clone-mode paths. A link-mode
path is a symlink, which a directory pattern like `env/` does not ignore, so it
is unstaged explicitly. An exclude pathspec can't do this, because git exits 1
when an excluded path is also ignored. The commit uses `--no-verify` and a fixed
identity, and never leaves the clone.

**`apply` is a patch.** The job's changes are exported with
`git diff --binary` and staged with `git apply --index`, which is atomic. If any
hunk does not apply to the repository as it is now, including over uncommitted
edits, nothing changes and git's message is passed back. No conflict markers are
ever written.

**Review mode also uses a copy.** It keeps the blast radius at zero even if a
CLI's read-only mode is weaker than documented.

**Errors the caller can act on are `ToolError`s.** In the MCP SDK (2.x), any
other exception reaches the client as a generic "Error executing tool" and the
message stays on the server. Bad input, git refusals, and wrong job states are
converted. Real bugs are left to surface as crashes rather than being disguised
as refusals.

**Usage comes from the CLIs, never from their credentials.** agy prints its
`/usage` and `/credits` slash commands in print mode as tab-separated rows.
cursor-agent shows `/usage` only in its interactive UI, so Polyphony runs it in a
pseudo-terminal, renders the screen with `pyte`, and parses the panel. That is
brittle by nature. When the layout changes, the check fails loudly and returns
the screen it saw rather than guessing. The CLIs' own tokens are never read.
Cleanup closes the pseudo-terminal before waiting on the process: on macOS the
real cursor-agent otherwise never finishes exiting, and the check hung forever.
No stand-in process reproduced that, so the real-binary smoke test is the
guard.

**Provisioning failure is fatal.** A partly provisioned copy runs, then
fails tests for reasons unrelated to the agent's work
(`evidence/provisioning-spike.md`).

## Verified, and not yet

Verified: each adapter's flags against the real binaries
(`evidence/smoke-results.md`), copy-on-write provisioning of medicoder's
virtualenv (`evidence/provisioning-spike.md`), and the full delegate, status,
diff, apply, discard cycle against scratch repositories with a stand-in CLI.

Not yet: a job against a real work repository.
