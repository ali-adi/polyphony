"""Delegated jobs: one executor run in a private copy of the repository, tracked on disk.

State lives in ~/.polyphony/jobs/<id>/ rather than in any client's session,
so a job started from one MCP client can be checked from another.
"""

from __future__ import annotations

import fcntl
import fnmatch
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from polyphony import ledger
from polyphony.config import DEFAULT_HOME, ProjectConfig
from polyphony.guard import run_git
from polyphony.workspace import Workspace, WorkspaceError, copy_git

ACTIVE = ("queued", "running")
# A brief is read whole into the job record and the executor's prompt.
MAX_BRIEF_BYTES = 200 * 1024
# A queued job whose worker has not claimed it by now never will (launch waits ~1s).
QUEUE_GRACE_SECONDS = 60


class JobNotFound(Exception):
    pass


class JobError(Exception):
    """A request the job's current state cannot satisfy."""


@dataclass
class Job:
    id: str
    project: str
    repo: str
    executor: str
    mode: str
    instruction: str
    timeout_seconds: int
    workdir: str
    base_commit: str
    model: str | None = None
    link_paths: list[str] = field(default_factory=list)
    state: str = "queued"
    pid: int | None = None
    pgid: int | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    error: str | None = None
    files_changed: list[str] = field(default_factory=list)
    diff_stat: str = ""
    # Working-tree files too large to copy into the job (over OVERLAY_MAX_BYTES).
    overlay_skipped: list[str] = field(default_factory=list)
    # Set when the latest apply had to leave its changes unstaged (they touch files with
    # unstaged edits).
    applied_unstaged: bool = False
    # The check command, run in the copy after a code-mode executor succeeds.
    check_command: str | None = None
    check_timeout_seconds: int = 600
    check_exit_code: int | None = None
    check_passed: bool | None = None  # None: not run
    check_pgid: int | None = None  # the check's own process group, for cancel
    # "applied", "discarded" or "cancelled" once written to the ledger, so it is written once.
    outcome: str | None = None
    # The executor leads its own process group (so a timeout can kill all it
    # started), which the worker's group no longer covers. cancel kills both.
    executor_pgid: int | None = None
    # Feedback from each revise, oldest first. attempt counts runs in this copy.
    feedback: list[str] = field(default_factory=list)
    attempt: int = 1
    # Entries of files_changed already applied, so a later apply takes only the rest.
    applied_paths: list[str] = field(default_factory=list)
    # The copy's git dir, kept outside the executor's workspace (see copy_git).
    # None for a job from before that, whose git dir is inside the copy.
    git_dir: str | None = None
    # When the job last became queued, so a worker that never claims it is noticed.
    queued_at: float | None = None
    # Lane r2-secrets. Secret-looking files the copy was not given (see
    # workspace.SECRET_PATTERNS), and the project's env_scrub globs, recorded so
    # the detached worker can keep those variables from the executor and check.
    withheld: list[str] = field(default_factory=list)
    env_scrub: list[str] = field(default_factory=list)
    # Lane r2-brief. The brief file the task came from, resolved, for display
    # only: its text was copied into `instruction` and brief.md at create.
    brief_path: str | None = None

    @property
    def applied(self) -> bool:
        """Whether any of the job has reached the repository."""
        return bool(self.applied_paths)


class JobStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else DEFAULT_HOME
        self.dir = self.root / "jobs"
        self._held = threading.local()

    def path(self, job_id: str) -> Path:
        return self.dir / job_id

    def output_path(self, job_id: str) -> Path:
        return self.path(job_id) / "output.txt"

    def check_path(self, job_id: str) -> Path:
        return self.path(job_id) / "check.txt"

    def brief_copy_path(self, job_id: str) -> Path:
        return self.path(job_id) / "brief.md"

    def save(self, job: Job) -> None:
        """Write atomically, so a reader never sees a half-written file."""
        d = self.path(job.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "job.json.tmp"
        tmp.write_text(json.dumps(asdict(job), indent=2))
        os.replace(tmp, d / "job.json")

    def load(self, job_id: str) -> Job:
        f = self.path(job_id) / "job.json"
        if not f.exists():
            raise JobNotFound(f"No job {job_id!r} in {self.dir}.")
        return Job(**json.loads(f.read_text()))

    def all(self) -> list[Job]:
        if not self.dir.is_dir():
            return []
        jobs = [self.load(p.name) for p in self.dir.iterdir() if (p / "job.json").exists()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    @contextmanager
    def lock(self):
        """Held from counting an executor's active jobs until the new job is
        recorded, so two servers can't both take its last slot, and while a
        job changes hands between states (claim, refresh, revise).

        Reentrant within a thread: delegate holds it while refresh takes it,
        and flock on a second descriptor would wait on its own process.
        """
        if getattr(self._held, "depth", 0):
            self._held.depth += 1
            try:
                yield
            finally:
                self._held.depth -= 1
            return
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "delegate.lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self._held.depth = 1
            try:
                yield
            finally:
                self._held.depth = 0

    def refresh(self, job: Job) -> Job:
        """Mark a job whose worker vanished without recording a result, or
        never claimed it (the server stopped between create_job and launch)."""
        if job.state == "running" and job.pid and not _alive(job.pid):
            error = "The worker process exited without recording a result."
        elif job.state == "queued" and _stuck(job):
            error = "The job's worker never started."
        else:
            return job
        with self.lock():  # the worker claims under this lock, so it can't start now
            current = self.load(job.id)  # it may have moved on since `job` was read
            if current.state != job.state or current.attempt != job.attempt:
                return current
            if current.state == "queued" and not _stuck(current):
                return current
            current.state = "died"
            current.error = error
            current.finished_at = time.time()
            self.save(current)
            return current


def active_counts(store: JobStore) -> Counter[str]:
    """Queued and running jobs per executor, across every project. Each job
    is refreshed first, so a dead worker doesn't hold a slot."""
    return Counter(j.executor for j in map(store.refresh, store.all()) if j.state in ACTIVE)


def _stuck(job: Job) -> bool:
    return time.time() - (job.queued_at or job.created_at) > QUEUE_GRACE_SECONDS


def claim(store: JobStore, job_id: str, attempt: int) -> Job | None:
    """Move a queued job to running for the worker launched for `attempt`.

    None if it is not that worker's to run: cancelled before it started, or
    revised since, when a newer worker owns the next attempt. Under the
    store lock, so revise, refresh and a late worker can't interleave.
    """
    with store.lock():
        job = store.load(job_id)
        if job.state != "queued" or job.attempt != attempt:
            return None
        job.state = "running"
        job.pid = os.getpid()
        job.pgid = os.getpgid(0)
        job.started_at = time.time()
        store.save(job)
        return job


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def read_brief(path: str, base: Path) -> tuple[Path, str]:
    """The brief file's resolved path and text, or a ValueError saying what is wrong.

    A long instruction can be cut short on its way through a client, so a
    caller writes it to a file instead. A relative path is taken from the
    repository (`base`), not the server's working directory, which the caller
    cannot see. Read once, at delegate time: the job keeps a copy, so editing
    the file afterwards changes neither a queued job nor a revision.
    """
    file = (base / Path(path).expanduser()).resolve()
    if not file.exists():
        raise ValueError(f"brief_path {path!r}: no such file ({file}).")
    if not file.is_file():
        raise ValueError(f"brief_path {path!r}: {file} is not a regular file.")
    try:
        with file.open("rb") as f:
            data = f.read(MAX_BRIEF_BYTES + 1)  # no more, however large the file
    except OSError as e:
        raise ValueError(f"brief_path {path!r}: cannot read it: {e.strerror or e}.") from e
    if len(data) > MAX_BRIEF_BYTES:
        raise ValueError(
            f"brief_path {path!r} is over the {MAX_BRIEF_BYTES}-byte limit; split the task, "
            "or have the brief point the agent at files in the repository instead."
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"brief_path {path!r}: not valid UTF-8 ({e}).") from e
    if not text.strip():
        raise ValueError(f"brief_path {path!r}: the file is empty.")
    return file, text


def with_brief(instruction: str, brief: str | None) -> str:
    """The task as the executor gets it: the instruction, a blank line, the brief."""
    if brief is None:
        return instruction
    return f"{instruction}\n\n{brief}" if instruction.strip() else brief


def create_job(
    store: JobStore,
    project: ProjectConfig,
    instruction: str,
    executor: str,
    mode: str,
    model: str | None = None,
    timeout_seconds: int = 1800,
    check: str | None = None,
    check_timeout_seconds: int = 600,
    brief: tuple[Path, str] | None = None,
) -> Job:
    """Copy the repository, provision the copy, and record the job as queued.

    A check only makes sense after edits, so review mode drops it.

    `brief` is read_brief's result. Its text is joined to the instruction and
    stored as the job's instruction, so prompt() and every revision see the
    whole task from job.json alone; brief.md keeps the brief by itself for a
    person to read.
    """
    job_id = new_job_id()
    workdir = store.path(job_id) / "repo"
    ws = Workspace.create(
        project.path, workdir,
        exclude=tuple(str(e.get("path", "")) for e in project.provision),
        git_dir=store.path(job_id) / "git",
        allow_secrets=tuple(project.allow_secrets),
    )
    try:
        ws.provision(project.provision)
    except WorkspaceError:
        shutil.rmtree(store.path(job_id), ignore_errors=True)
        raise
    job = Job(
        id=job_id,
        project=project.name,
        repo=str(project.path),
        executor=executor,
        mode=mode,
        instruction=with_brief(instruction, brief[1] if brief else None),
        timeout_seconds=timeout_seconds,
        workdir=str(ws.path),
        git_dir=str(ws.git_dir),
        base_commit=_check(copy_git(["rev-parse", "HEAD"], ws.git_dir, ws.path)).stdout.strip(),
        model=model,
        link_paths=[
            str(e["path"]).rstrip("/") for e in project.provision if e.get("mode") == "link"
        ],
        overlay_skipped=ws.skipped,
        check_command=check if mode == "code" else None,
        check_timeout_seconds=check_timeout_seconds,
        queued_at=time.time(),
        withheld=ws.withheld,
        env_scrub=list(project.env_scrub),
        brief_path=str(brief[0]) if brief else None,
    )
    if brief:
        store.brief_copy_path(job_id).write_text(brief[1], encoding="utf-8")
    store.save(job)
    return job


def launch(store: JobStore, job: Job) -> None:
    """Start the job's worker, detached from the caller.

    The worker double-forks (see polyphony.worker), so the process started
    here exits almost at once. Waiting on it means no zombie is left behind
    in a long-lived server, where it would make a dead worker look alive.
    """
    job_dir = store.path(job.id)
    with open(job_dir / "worker.log", "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "polyphony.worker", str(job_dir), str(job.attempt)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    if proc.wait(timeout=30) != 0:
        job = store.load(job.id)
        job.state = "failed"
        job.error = f"The worker failed to start. See {job_dir / 'worker.log'}."
        job.finished_at = time.time()
        store.save(job)


def prompt(job: Job) -> str:
    """What the executor is told on this attempt.

    The executor keeps no memory between runs, so a revision restates the
    whole task: the original instruction, where it stands, and every piece of
    feedback so far rather than only the latest.
    """
    if not job.feedback:
        return job.instruction
    notes = "\n\n".join(f"{i}. {text}" for i, text in enumerate(job.feedback, 1))
    return (
        f"{job.instruction}\n\n---\n"
        f"This is attempt {job.attempt} at the task above, in the same working copy. "
        "The previous attempt's changes are already in the files: build on them, "
        "fix what the feedback points out, and do not start over.\n\n"
        f"Feedback on the earlier attempts, oldest first:\n\n{notes}"
    )


def revise(
    store: JobStore, job_id: str, feedback: str, timeout_seconds: int | None = None
) -> Job:
    """Queue another attempt in the job's copy, on top of what the last one left.

    base_commit stays put, so diff and apply cover every attempt together.
    The caller launches the worker, as after create_job.
    """
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is still {job.state}; wait for it or cancel it first.")
    if job.applied:
        raise JobError(
            f"Job {job.id} has already been applied ({', '.join(job.applied_paths)}). "
            "Revising it would apply the same changes again; discard it and delegate "
            "a new job instead."
        )
    if not Path(job.workdir).is_dir():
        raise JobError(f"Job {job.id} no longer has its copy of the repository to revise.")
    if not feedback.strip():
        raise ValueError("feedback must say what to change.")

    # Keep each attempt's output and check result; the next run writes fresh ones.
    for current in (store.output_path(job.id), store.check_path(job.id)):
        if current.exists():
            os.replace(current, current.with_name(f"{current.stem}-{job.attempt}.txt"))
    job.feedback.append(feedback.strip())
    job.attempt += 1
    if timeout_seconds is not None:
        job.timeout_seconds = timeout_seconds
    job.state = "queued"
    job.queued_at = time.time()
    # Old process groups may belong to other processes by now; cancel must not signal them.
    job.pid = job.pgid = job.executor_pgid = job.check_pgid = None
    job.started_at = job.finished_at = job.exit_code = job.error = None
    job.check_exit_code = job.check_passed = None
    # A cancelled attempt is not the job's outcome. The ledger keeps the last
    # entry per job, so the outcome of this attempt replaces it.
    job.outcome = None
    store.save(job)
    return job


def cancel(store: JobStore, job_id: str) -> Job:
    """Stop a queued or running job, killing its executor with it."""
    job = store.load(job_id)
    if job.state not in ACTIVE:
        return job
    # The worker first, so it cannot record the executor's death as a failure.
    for pgid in (job.pgid, job.executor_pgid, job.check_pgid):
        if pgid:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass  # already gone, or (macOS) still being reaped
    job = store.load(job_id)
    job.state = "cancelled"
    job.error = "Cancelled."
    job.finished_at = time.time()
    _record(store, job, "cancelled")
    return job


def _record(store: JobStore, job: Job, outcome: str) -> None:
    """Save the job's outcome and write it to the ledger, once per job."""
    job.outcome = outcome
    store.save(job)
    ledger.record(store.root, job, outcome)


def snapshot(job: Job) -> None:
    """Commit the executor's work in the copy and record what changed.

    Plain `git add -A` skips gitignored clone-mode paths on its own. A
    link-mode path is a symlink, which a directory pattern like `env/` does
    not ignore, so each one is unstaged explicitly. An exclude pathspec
    can't do this: git exits 1 when an excluded path is also ignored.

    The commit lives only in the job's private copy. apply turns it into a
    patch, so its message and author never reach the repository's history.
    """
    _jgit(job, ["add", "-A"])
    for path in job.link_paths:
        _jgit(job, ["rm", "-r", "--cached", "--ignore-unmatch", "-q", "--", path])
    if _jgit(job, ["diff", "--cached", "--quiet"], check=False).returncode != 0:
        _jgit(job, [
            "-c", "user.name=Polyphony",
            "-c", "user.email=polyphony@localhost",
            "commit", "--no-verify", "-q", "-m", f"polyphony job {job.id}",
        ])
    # -z, so a path git would C-quote (non-ASCII, quotes, newlines) keeps its real name.
    names = _jgit(job, ["diff", "--name-only", "-z", f"{job.base_commit}..HEAD"]).stdout
    job.files_changed = [name for name in names.split("\0") if name]
    job.diff_stat = _jgit(job, ["diff", "--stat", f"{job.base_commit}..HEAD"]).stdout.rstrip()


def run_check(store: JobStore, job: Job) -> None:
    """Run the job's check command in its copy, output to check.txt.

    The check runs code the executor may have written (a test, a conftest, a
    Makefile), so it runs in an OS sandbox: it can write only in its copy
    (not the copy's .git) and in a private temp dir, and it has no network
    beyond loopback. Without a sandbox it does not run at all. See
    _sandbox_argv. Its environment is the server's minus credential-looking
    variables (CHECK_SCRUB) and the project's env_scrub.

    It runs after snapshot(), and the copy is reset to that snapshot
    afterwards, so whatever it writes (caches, coverage files, lockfile
    updates) stays out of the diff, including a revised attempt's. It gets
    its own process group so a timeout can kill everything it started, and
    records that group so cancel can too. A failed check leaves the job's
    state alone: the executor did succeed, and whether the work is still
    worth applying is the caller's call.
    """
    tmp = store.path(job.id) / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    sandbox = _sandbox_argv(job, tmp)
    with store.check_path(job.id).open("w") as out:
        if sandbox is None:
            job.check_passed = False
            out.write(
                "The check did not run: it runs code the executor may have written, so "
                "Polyphony runs it only in a sandbox, and none was found (sandbox-exec on "
                "macOS, bwrap on Linux).\n"
            )
            return
        env = dict(scrub_env(os.environ, (*CHECK_SCRUB, *job.env_scrub)),
                   TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp),
                   XDG_CACHE_HOME=str(tmp / "cache"))
        snapshot_head = _jgit(job, ["rev-parse", "HEAD"]).stdout.strip()
        proc = subprocess.Popen(
            [*sandbox, "/bin/sh", "-c", job.check_command], cwd=job.workdir, env=env,
            stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        job.check_pgid = proc.pid
        store.save(job)
        try:
            job.check_exit_code = proc.wait(timeout=job.check_timeout_seconds)
            job.check_passed = job.check_exit_code == 0
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()
            job.check_passed = False
            out.write(f"\n--- check timed out after {job.check_timeout_seconds}s; "
                      f"its process group was killed ---\n")
        finally:
            # Anything it left running in the background would keep writing to the copy.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass  # already gone, or (macOS) still being reaped
            job.check_pgid = None
            store.save(job)
    _restore(job, snapshot_head)


# Environment variables the check never gets, on top of the project's env_scrub.
# The check runs code the executor may have written, and the sandbox has no
# network, so it has no use for credentials; a test that needs one can be
# given it by name in the check command. The executor keeps these (agent CLIs
# authenticate with them) unless env_scrub names them.
CHECK_SCRUB = ("*_API_KEY", "*_TOKEN", "*_SECRET", "*_PASSWORD", "*_CREDENTIALS")


def scrub_env(env: Mapping[str, str], patterns: Iterable[str]) -> dict[str, str]:
    """`env` without the variables whose names match any of `patterns`.

    Case-sensitive, as names are: `*_TOKEN` leaves `my_token` alone.
    """
    patterns = tuple(patterns)
    return {k: v for k, v in env.items()
            if not any(fnmatch.fnmatchcase(k, p) for p in patterns)}


def _restore(job: Job, head: str) -> None:
    """Put the copy back to the snapshot, dropping whatever the check wrote.

    Ignored files stay (snapshot never picks them up). Link-mode paths are
    untracked symlinks, so they are kept out of the clean by name.
    """
    _jgit(job, ["reset", "--hard", "-q", head])
    keep = [arg for path in job.link_paths for arg in ("-e", f"/{path}")]
    _jgit(job, ["clean", "-f", "-d", "-q", *keep])


# macOS sandbox profile for the check. Writes are allowed only under WORKDIR
# (minus its .git) and TMP; network only on loopback. LaunchServices and Apple
# events are denied because either can start a process outside the sandbox
# (`open -a Terminal x.command`, `osascript`).
_SEATBELT_PROFILE = """\
(version 1)
(allow default)
(deny network*)
(allow network* (local ip "localhost:*"))
(allow network* (remote ip "localhost:*"))
(deny file-write*)
(allow file-write*
  (subpath (param "WORKDIR"))
  (subpath (param "TMP"))
  (literal "/dev/null") (literal "/dev/zero") (literal "/dev/tty")
  (literal "/dev/dtracehelper") (regex #"^/dev/fd/"))
(deny file-write* (subpath (param "GITDIR")))
(deny appleevent-send)
(deny mach-lookup
  (global-name "com.apple.coreservices.launchservicesd")
  (global-name "com.apple.lsd.mapdb")
  (global-name "com.apple.lsd.modifydb"))
"""


def _sandbox_argv(job: Job, tmp: Path) -> list[str] | None:
    """The command prefix that confines the check, or None if there is no sandbox.

    Paths are resolved, because the sandboxes match real paths (/tmp is
    /private/tmp on macOS), and a link-mode symlink in the copy resolves to
    the user's own files, which stay read-only.
    """
    work = Path(os.path.realpath(job.workdir))
    tmp = Path(os.path.realpath(tmp))
    gitdir = Path(os.path.realpath(job.git_dir)) if job.git_dir else work / ".git"
    if sys.platform == "darwin":
        exe = shutil.which("sandbox-exec") or (
            "/usr/bin/sandbox-exec" if os.path.exists("/usr/bin/sandbox-exec") else None
        )
        if exe is None:
            return None
        return [exe, "-p", _SEATBELT_PROFILE,
                "-D", f"WORKDIR={work}", "-D", f"TMP={tmp}", "-D", f"GITDIR={gitdir}"]
    if sys.platform.startswith("linux"):
        exe = shutil.which("bwrap")
        if exe is None:
            return None
        return [exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                "--bind", str(work), str(work), "--ro-bind", str(gitdir), str(gitdir),
                "--bind", str(tmp), str(tmp), "--unshare-net", "--die-with-parent", "--"]
    return None


def _jgit(job: Job, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """git in the job's copy, only ever through copy_git."""
    res = copy_git(args, job.git_dir or Path(job.workdir) / ".git", job.workdir)
    return _check(res) if check else res


def _check(res: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(res.args[1:])} failed: {res.stderr.strip()}")
    return res


DIFF_LIMIT = 60_000


def diff(store: JobStore, job_id: str, limit: int = DIFF_LIMIT) -> str:
    """The job's changes against the commit it started from."""
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is still {job.state}.")
    text = _jgit(job, ["diff", f"{job.base_commit}..HEAD"]).stdout
    if not text:
        return f"Job {job.id} changed nothing."
    if len(text) > limit:
        return text[:limit] + (
            f"\n\n[Truncated at {limit} of {len(text)} characters. Full diff: "
            f"git -C {job.workdir} diff {job.base_commit}..HEAD]"
        )
    return text


def apply(store: JobStore, job_id: str, paths: list[str] | None = None) -> list[str]:
    """Stage a succeeded job's changes in the repository, without committing.

    The only operation that writes to the user's repository. `git apply` is
    atomic: if any hunk does not apply to the repository as it is now,
    including over uncommitted edits, nothing is changed.

    `paths` limits it to some of the job's files; without it, everything not
    yet applied goes. Returns the entries of files_changed applied this time.
    """
    job = store.load(job_id)
    if job.state != "succeeded":
        raise JobError(f"Job {job.id} {job.state}; only a succeeded job can be applied.")
    if not job.files_changed:
        raise JobError(f"Job {job.id} changed nothing, so there is nothing to apply.")
    files, pathspecs = _select(job, paths)

    patch = store.path(job.id) / "changes.patch"
    # Literal pathspecs, so a file named like a glob exports only itself.
    _jgit(job, ["--literal-pathspecs", "diff", "--binary", f"--output={patch}",
                f"{job.base_commit}..HEAD", "--", *pathspecs])
    res = run_git(["apply", "--index", str(patch)], cwd=job.repo)
    unstaged = False
    if res.returncode != 0 and run_git(["apply", "--check", str(patch)], cwd=job.repo).returncode == 0:
        # The job started from the working tree, so a file the user had edited but not staged
        # no longer matches the index. Apply to the working tree only, leaving staging to them.
        res = run_git(["apply", str(patch)], cwd=job.repo)
        unstaged = res.returncode == 0
    if res.returncode != 0:
        raise JobError(
            f"Job {job.id} does not apply cleanly to the repository as it is now; "
            f"nothing was changed:\n{res.stderr.strip()}"
        )
    job.applied_unstaged = unstaged
    job.applied_paths += files
    store.save(job)
    if job.outcome is None:
        _record(store, job, "applied")
    return files


def _select(job: Job, paths: list[str] | None) -> tuple[list[str], list[str]]:
    """The files_changed entries an apply covers, and the pathspecs that export them.

    A rename is one change with two paths, and files_changed may list either
    or both. Either side is accepted, and both are exported, so a partial
    apply never adds the new file while leaving the old one behind.
    """
    partner = _renames(job)
    if paths is None:
        files = [f for f in job.files_changed if f not in job.applied_paths]
        if not files:
            raise JobError(f"Job {job.id} is already applied in full.")
        if not job.applied_paths:
            return files, []  # the whole diff, exactly as the job made it
        wanted = set(files)
    else:
        if not paths:
            raise JobError("paths is empty; leave it out to apply everything.")
        unknown = [p for p in paths if p not in job.files_changed and p not in partner]
        if unknown:
            raise JobError(
                f"Job {job.id} did not change: {', '.join(unknown)}. "
                f"It changed: {', '.join(job.files_changed)}."
            )
        wanted = set(paths)
    wanted |= {partner[p] for p in wanted if p in partner}
    files = [f for f in job.files_changed if f in wanted]
    already = [f for f in files if f in job.applied_paths]
    if already:
        raise JobError(
            f"Job {job.id} already applied {', '.join(already)}; nothing was changed."
        )
    return files, sorted(wanted)


def _renames(job: Job) -> dict[str, str]:
    """Map each side of every file the job renamed to the other side."""
    out = _jgit(
        job, ["diff", "--name-status", "-z", "--find-renames", f"{job.base_commit}..HEAD"]
    ).stdout.split("\0")
    partner: dict[str, str] = {}
    i = 0
    while i < len(out) - 1:
        if out[i].startswith("R"):
            old, new = out[i + 1], out[i + 2]
            partner[old], partner[new] = new, old
            i += 3
        else:
            i += 2
    return partner


def discard(store: JobStore, job_id: str) -> None:
    """Delete a finished job: its copy and its record. The ledger keeps its
    outcome, as "discarded" unless it was already applied or cancelled."""
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is {job.state}; cancel it before discarding.")
    if job.outcome is None:
        ledger.record(store.root, job, "discarded")
    shutil.rmtree(store.path(job.id), ignore_errors=True)


@dataclass
class GcRecord:
    job_id: str
    state: str
    age_seconds: float
    bytes: int


def gc(store: JobStore, older_than_seconds: float, dry_run: bool = False) -> list[GcRecord]:
    """Delete finished jobs that ended more than `older_than_seconds` ago.

    Never run automatically: a finished job may hold work nobody has applied
    yet, and deleting that silently is worse than the disk it uses. A job
    that never recorded an end is aged from its creation.
    """
    now = time.time()

    def expired(job: Job) -> bool:
        return (job.state not in ACTIVE
                and now - (job.finished_at or job.created_at) >= older_than_seconds)

    removed = []
    for job in store.all():
        if not expired(store.refresh(job)):
            continue
        size = disk_usage(store.path(job.id))  # slow on a big copy, so outside the lock
        if not dry_run:
            # revise holds this lock while it requeues a job, so the job is read
            # again under it: one revised since store.all() is now active, and kept.
            with store.lock():
                try:
                    job = store.refresh(store.load(job.id))
                except JobNotFound:
                    continue  # discarded meanwhile
                if not expired(job):
                    continue
                if job.outcome is None:
                    ledger.record(store.root, job, "discarded", via="gc")
                shutil.rmtree(store.path(job.id), ignore_errors=True)
        removed.append(GcRecord(job.id, job.state, now - (job.finished_at or job.created_at), size))
    return removed


def disk_usage(path: Path) -> int:
    """Apparent size of the files under `path`, not following symlinks.

    Link-mode paths are symlinks to the user's own files, so following them
    would count bytes that deleting the job never frees. Clone-mode copies
    share blocks with their source until written, so this is an upper bound.
    """
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except FileNotFoundError:
                pass
    return total
