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
| `config.py` | Per-repository provisioning, pool order, models, check command, job limits. Found in the repo's `.polyphony.yaml`, then `$POLYPHONY_HOME/projects/`, then the legacy package-relative `projects/` |
| `jobs.py` | Job records, launch, cancel, revise, snapshot, check, diff, apply, apply_many, discard, gc |
| `ledger.py` | One line per job's outcome (applied, discarded, cancelled), and the `stats` summary |
| `worker.py` | The detached process that runs one job |
| `usage.py` | Remaining quota, read from each CLI's own report, and its on-disk cache |
| `server.py` | MCP tools: thin wrappers over `jobs.py`, `ledger.py` and `usage.py` |
| `cli.py` | `mcp`, plus `jobs`, `discard`, `gc`, `stats`, `usage`, `doctor` for a human |

## Decisions that are not obvious from the code

**No automatic failover.** When a job fails, the lead reads why and decides
whether to re-delegate. An automatic rule would have to tell quota exhaustion
apart from real bugs using output patterns nobody has observed yet. Failing over
on a real bug would hide it and spend cheap quota on broken work.

**Quota and job limits steer an unnamed choice only.** With no executor
named, `delegate` walks the pool and passes over one that is unavailable, at
its limit of active jobs, or whose latest usage report says it is out of quota,
recording why in `skipped`. A named executor is never skipped for quota (the
caller chose it) but is refused at its job limit. Usage reports are cached in
`<home>/usage-cache.json` for 300s, failures included, because a cursor check
runs a pseudo-terminal for seconds and a broken one would otherwise cost its
timeout on every delegate. A missing, failed or unparsed report means "don't
skip". agy counts as out only when every model group has a window at 0%, since
which group a job's model draws on isn't known; cursor counts as out when every
top-level category is 100% used or disabled. Neither CLI has been observed out
of quota, so both rules are read from healthy output and may need adjusting.

**Job limits are per account, so they span projects.** Active jobs are counted
across the whole store, refreshing each so a dead worker frees its slot. The
limit comes from the delegating project's `max_parallel`. There is none by
default: real use has run seven cursor jobs at once, all of them applied. A file
lock on `<home>/delegate.lock` is held from counting to recording the job, so
two servers can't both take the last slot; it serialises delegations, usage
checks included.

**Fan-out is opt-in.** `delegate_many` sends one brief to several named
executors so the lead can compare diffs on a risky change. It checks every
executor and makes every copy before launching any, so a failure part way
leaves nothing running. It never picks executors itself: spending quota twice
is the caller's decision.

**A worker runs only the attempt it was launched for.** `launch` passes the
attempt number, and the worker claims the job (queued to running) under the
store lock only if that attempt is still current. So a job cancelled while
queued and then revised can't be run by both its old worker and its new one.
A queued job that no worker claims within a minute (the server stopped
between creating and launching it) is marked `died`, so it stops holding a
job slot. The lock is reentrant per thread, because `delegate` holds it while
counting jobs and counting refreshes them.

**The worker double-forks.** The server is long-lived. If it were the worker's
parent, a worker that died would linger as a zombie, `os.kill(pid, 0)` would keep
succeeding, and `died` would never be detected. `launch()` waits on an
intermediate process that exits at once, so the real worker is reparented to
init. The worker, the executor, and the check each lead their own process
group; the job records all three and `cancel` kills them all. On macOS,
signalling a group that is still being reaped briefly returns `EPERM` before
`ESRCH`, so treating `EPERM` as alive only delays `died` by a poll, and `cancel`
ignores it.

**Output is streamed to disk, and the executor gets its own process group.**
The executor's stdout goes straight into the job's `output.txt`, so `status`
can show a running job's progress; stderr goes to a separate temporary file,
because it is what explains a non-zero exit and would clutter a review's
output. Both are files rather than pipes, so no buffer can fill and block the
CLI. How often the file grows depends on the CLI's own buffering. The executor
starts a new session, so a timeout kills everything it started, not only the
CLI. That puts it outside the worker's group, so the worker records the
executor's group in `job.json` for `cancel`. A `cancel` in the
instant between the executor starting and that record being written still
misses the executor.

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

**The clone's git dir is outside the agent's workspace, and Polyphony trusts
none of it.** The executor can write anything in its copy. Git runs code
named in its config (fsmonitor, filter drivers, `include.path`, `hooksPath`)
and in hooks, and follows a `.git` file or a `commondir` file to another
repository. Before this, an agent that replaced `.git` with `gitdir: <the
user's repo>/.git` made the snapshot commit write into the user's own objects,
and a planted hook ran on the host at snapshot time; both were reproduced in
tests. Now the clone is made with `--separate-git-dir` into
`jobs/<id>/git`, beside the copy rather than in it, so a CLI whose sandbox
confines writes to its workspace can't reach it. And every git command
Polyphony runs there goes through `copy_git`, which first puts back the config
saved when the copy was made, removes `commondir` and object alternates,
rewrites the copy's `.git` pointer, and passes the git dir and work tree
explicitly with hooks and fsmonitor off. Files are unlinked before being
rewritten, since the agent may have made them symlinks. What the executor
itself runs is still bounded only by its CLI's own sandbox: an agent with an
unrestricted shell can write wherever the user can, including a global
`core.hooksPath` directory.

**Snapshot commits.** After the executor finishes, the worker commits in the
clone, so `diff` and `apply` work from git rather than from filesystem
timestamps. Plain `git add -A` skips gitignored clone-mode paths. A link-mode
path is a symlink, which a directory pattern like `env/` does not ignore, so it
is unstaged explicitly. An exclude pathspec can't do this, because git exits 1
when an excluded path is also ignored. The commit uses `--no-verify` and a fixed
identity, and never leaves the clone.

**The check runs sandboxed, after the snapshot, and never changes the job's state.**
The check runs code the executor may have written (a test, a `conftest.py`, a
`Makefile`), so it would otherwise hand an edit-only executor arbitrary code on
the host. It runs under `sandbox-exec` on macOS or `bwrap` on Linux: writes only
in the copy (not its `.git`) and a private `$TMPDIR` under the job, no network
beyond loopback, and on macOS no LaunchServices or Apple events, either of which
could start a process outside the sandbox. A link-mode path resolves to the
user's own files, so it is read-only to the check. With no sandbox available
the check does not run, and `check.txt` says why. Running it after the snapshot,
then resetting the copy to that snapshot, keeps what it writes (caches, coverage
files, lockfile updates) out of the diff, a revised attempt's included. A failing check still leaves the job `succeeded`: the executor did
its part, and whether the work is worth fixing or applying is the lead's call.
The check gets its own process group, killed on timeout, and the job records
that group so `cancel` kills it too.

**`apply` is a patch.** The job's changes are exported with
`git diff --binary` and staged with `git apply --index`. If any
hunk does not apply to the repository as it is now, including over uncommitted
edits, nothing changes and git's message is passed back. No conflict markers are
ever written. `git apply` is not atomic once it starts writing: it removes every
file it rewrites first, and a write that then fails (a file where a directory
still holds an ignored file) leaves those removals behind. So `apply` copies the
working-tree state of every path the patch touches into the job's directory
beforehand and puts it back after any failed `git apply`. Before applying it
refreshes the index's stat data (`update-index -q --refresh`, as `git status`
does), so a file touched but unchanged is not taken for an unstaged edit. It
falls back to the working tree alone only when the patch's files do have
unstaged edits; any other `--index` failure, such as a locked index, is
reported with git's reason.

`apply(paths=...)` exports only those files (`git diff -- <paths>`) through the
same path. A rename is one change with two paths, so naming either side exports
both. The job records `applied_paths`; a later apply without paths takes the rest,
and naming an applied path again is refused rather than applied twice. After
any apply, `revise` is refused.

**`apply_many` pre-checks the whole batch.** Applied one at a time, jobs from a
fan-out that conflict with each other are found only at the second one, with the
first already in the repository. `apply_many` first applies every patch, in
order, with `git apply --cached` to two scratch index files under the store: a
copy of the repository's index, and a copy that also takes the working tree's
current content of every file a job touches. A job whose files agree in both
and whose patch fits goes on both, as `apply --index` would stage it; one that
fits only the working-tree index would land unstaged, as `apply` falls back to.
Blobs go to a scratch object directory that borrows the repository's objects as
an alternate, and the scratch indexes are written whole (`core.splitIndex`
off, the split index's shared file copied alongside), so the pre-check writes
nothing to the repository. Only if every
patch fits does each go through `apply` itself, so the ledger and
`applied_paths` stay as they would be; if one fails then anyway (the repository
changed meanwhile), it stops and says which landed. It takes whole jobs only:
a partly applied job's remaining patch is not what its record describes.

**`revise` reruns in the same copy.** A wrong-but-close result is cheaper to
correct than to redo, so `revise` queues another run of the same executor in
the job's copy, on top of what the last attempt left. `base_commit` does not
move, so the next snapshot is a second commit and `diff` and `apply` cover every
attempt together. The CLIs are started fresh each time (no session resume, whose
flags have not been checked against the real binaries), so the prompt restates
the original instruction, says which attempt this is, and lists all feedback in
order. The attempt goes through the worker like the first, so its output streams
to a fresh `output.txt` and the check runs again; the previous attempt's are kept
as `output-<n>.txt` and `check-<n>.txt`, and every result field and process
group is cleared first. It counts against the executor's job limit. A job any
of whose files have been applied is refused: they are already in the
repository, and applying the cumulative patch again would conflict.

**The ledger sits beside `jobs/`, not in it,** so an outcome outlives `discard`.
A job's outcome is written once: at its first `apply` (partial or not, with how
many of its files were applied), at `cancel`, or at `discard` or `gc` if it had
none. Applying then discarding counts as one applied job. `revise` writes
nothing, and each line carries the job's attempt count. The one job with two
lines is a cancelled attempt that is then revised: `revise` clears the outcome,
and the ledger is read as each job's last line.

**A brief file is copied into the job's instruction.** Long inline instructions
were cut short on the way in, so `brief_path` names a file instead. It is read
once, at delegate time (at most 100 KB, UTF-8, relative to the repo), and the
instruction, a blank line, and its text are stored together as the job's
`instruction`: `prompt()` and every `revise` then restate the whole task from
`job.json` alone, and later edits to the file reach no queued or revised job.
`brief.md` keeps the brief by itself for reading, and `brief_path` is kept for
display only. `status` gives the stored task's length, SHA-256, and last 200
characters so the lead can confirm it arrived whole. agy, cursor, gemini, and
opencode take the prompt as one argv string, which Linux caps at 128 KiB
(MAX_ARG_STRLEN); over it the executor fails to start with "Argument list too
long". So the whole prompt, as `prompt()` builds it, is held to 120 KB
(`MAX_PROMPT_BYTES`, in UTF-8 bytes, which is what the kernel counts), checked
at delegate time before any copy is made and again on each `revise`, whose
feedback only adds to it. The limit applies whichever executor runs, although
claude and codex read stdin, so whether a task fits never depends on which one
the pool picks. The brief's own 100 KB leaves room for the instruction, report
mode's request and feedback.

**A model needs its executor.** `model` on `delegate` is refused without
`executor`: a model name belongs to one CLI, and with the pool choosing, it
would go to whichever executor was free, which may not know it.

**Old jobs are removed only on request.** `polyphony gc --older-than` has no
default and never runs on its own. A finished job may hold work nobody has
applied, and deleting that silently is worse than the disk it uses. Sizes count
files without following link-mode symlinks; clone-mode copies share blocks with
their source until written, so the figure is an upper bound. A job removed by
`gc` with no outcome yet is recorded in the ledger as discarded.

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

**Config does not depend on how Polyphony is installed.** A package-relative
`projects/` exists only in a source checkout, so config is also read from the
repository itself and from `$POLYPHONY_HOME`. A `.polyphony.yaml` whose `path`
names another directory is refused: a file in one repository must not make a
job clone another.

**An adapter with no safe edit mode is review-only.** `BaseExecutor.modes`
lists what an adapter supports, and the server refuses or skips one that lacks
the requested mode. opencode's edit-capable agent allows everything without
asking and has no sandbox, so it gets no `code` mode.

**Secrets are withheld by name, and the check's environment is scrubbed.**
The overlay copies untracked and gitignored files so the copy matches the
working tree, which would also hand every agent the repository's `.env`. So
files whose basename looks like a secret (`SECRET_PATTERNS` in `workspace.py`)
are left out, including one staged but never committed, and listed in the
job's `withheld`; `allow_secrets` lets named ones through. Both match without
regard to case, since `.ENV` holds keys as surely as `.env`, and on macOS's
default file system they are the same file. Matching is by name, not content: a key in `settings.toml` still goes, and a committed `.env` is in
the clone regardless. Explicit `provision` entries are the user's choice and are
not filtered. The check runs executor-written code, so it loses
`*_API_KEY`-style variables by default. The executor does not, because agent
CLIs authenticate with them; `env_scrub` names variables removed from both, and
is recorded on the job so the detached worker applies it.

**A report is a job mode, not an executor mode.** Audits run in review mode
left their findings only in stdout, which callers lost, and users worked around
it by running code mode with "only create ERROR_AUDIT.md". `report` makes that
the contract: the executor runs in its `code` mode (writing a file needs edit
permission), the prompt asks for `REPORT.md` and nothing else, and the worker
copies it out as the job's `report.md`. Other edits are listed as
`stray_changes` rather than prevented, since no CLI can grant write access to
one file. A symlinked `REPORT.md` is not read, since it could point at any
file on the machine. A tracked `REPORT.md` the job left unchanged is not taken
as the report either, so an old report is never returned as the new one; the
cost is that an agent writing exactly the tracked text fails the job. That is
kept, rather than accepting any `REPORT.md` present, because a stale report
passed off as fresh is worse than a rerun.

**Provisioning failure is fatal.** A partly provisioned copy runs, then
fails tests for reasons unrelated to the agent's work
(`evidence/provisioning-spike.md`).

## Verified, and not yet

Verified: each adapter's flags against the real binaries
(`evidence/smoke-results.md`), copy-on-write provisioning of medicoder's
virtualenv (`evidence/provisioning-spike.md`), and the full delegate, status,
diff, apply, discard cycle against scratch repositories with a stand-in CLI.
The check, streaming, revise, job limits, partial apply, and gc are covered the
same way, with stand-in CLIs only.

A job copy of medicoder, provisioned from its project config, ran the repo's
tracked suite (1245 tests) as a sandboxed check, with a stand-in executor.

Not yet: a real executor's job against a real work repository. How often each real CLI flushes
its output when stdout is not a terminal. Whether real agents build on an
"attempt N" prompt as intended. The out-of-quota rules for agy and cursor,
which no exhausted account has confirmed. The opt-in `codex`, `gemini`,
and `opencode` adapters: their flags are from official docs only, never run
against a real binary (`evidence/new-adapters-unverified.md`).
