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
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from polyphony import ledger
from polyphony.config import DEFAULT_HOME, ProjectConfig
from polyphony.executors.base import Mode
from polyphony.guard import run_git
from polyphony.workspace import Workspace, WorkspaceError, copy_git

ACTIVE = ("queued", "running")
# agy, cursor, gemini and opencode take the whole prompt as one argv string, which
# Linux caps at 128 KiB (MAX_ARG_STRLEN); over it the executor cannot even start.
# The prompt limit stays under that, and a brief under the prompt limit leaves
# room for the instruction, report mode's request, and revise feedback.
MAX_PROMPT_BYTES = 120 * 1024
# A brief is read whole into the job record and the executor's prompt.
MAX_BRIEF_BYTES = 100 * 1024
# A queued job whose worker has not claimed it by now never will (launch waits ~1s).
QUEUE_GRACE_SECONDS = 60

# A report job is a read-only audit whose findings are a file rather than
# stdout, which a caller tends to lose. Writing that file needs edit
# permission, so the executor runs in its code mode; what keeps it to the
# report is the instruction, and stray_changes shows whether it listened.
REPORT = "report"
REPORT_FILE = "REPORT.md"
REPORT_INSTRUCTION = (
    f"Write your complete findings as Markdown to {REPORT_FILE} at the repository "
    "root. That file is the product of this task, so put everything in it, not only "
    "in your reply. Change no other file."
)


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
    # Report mode: where the report was saved (jobs/<id>/report.md), and the files
    # the executor changed besides REPORT.md, which it was told not to touch.
    report_path: str | None = None
    stray_changes: list[str] = field(default_factory=list)
    # Lane reportapi. REPORT.md as the worker found it before this attempt ran
    # (report_fingerprint), so collect_report takes only a file the attempt wrote;
    # the saved report's length, so status never reads it; and whether it was cut
    # at REPORT_MAX_BYTES.
    report_before: list[int] | None = None
    report_chars: int | None = None
    report_truncated: bool = False

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
    def report_path(self, job_id: str) -> Path:
        return self.path(job_id) / "report.md"

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
    caller writes it to a file instead. A relative path is taken from `base`,
    the repo directory the caller gave, not the server's working directory,
    which the caller cannot see. Read once, at delegate time: the job keeps a copy, so editing
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


def check_prompt(text: str) -> None:
    """Refuse a prompt too long for an executor that takes it as one argument,
    or one holding a NUL byte, which no argv string can carry.

    Checked when the job is created and on each revise, rather than left to
    fail at launch with "Argument list too long" or "embedded null byte",
    which the job would report as a Polyphony worker error. Applied to every
    executor, though claude and codex read stdin, so a task's limits do not
    depend on which executor happens to be chosen.
    """
    if "\0" in text:
        raise ValueError(
            "The task contains a NUL byte (in the instruction, brief or feedback), "
            "which an executor cannot be given; remove it."
        )
    size = len(text.encode("utf-8"))
    if size > MAX_PROMPT_BYTES:
        raise ValueError(
            f"The task is {size} bytes, over the {MAX_PROMPT_BYTES}-byte limit on what "
            "an executor can be given; shorten it, or have it point the agent at files "
            "in the repository instead."
        )


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
    base_commit = _check(copy_git(["rev-parse", "HEAD"], ws.git_dir, ws.path)).stdout.strip()
    if mode == REPORT:
        _drop_untracked_report(ws, base_commit)
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
        base_commit=base_commit,
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


def _drop_untracked_report(ws: Workspace, base_commit: str) -> None:
    """Remove a REPORT.md the copy has but its base commit lacks.

    That is a gitignored one the overlay brought over from the working tree:
    an old report, which the agent should not build on or be mistaken for
    having written. Being ignored, removing it changes nothing in the diff.
    A REPORT.md in the base commit stays, and counts only if rewritten (see
    collect_report).
    """
    stale = ws.path / REPORT_FILE
    if not (stale.is_symlink() or stale.is_file()):
        return
    if copy_git(["cat-file", "-e", f"{base_commit}:{REPORT_FILE}"],
                ws.git_dir, ws.path).returncode != 0:
        stale.unlink()


def executor_mode(mode: str) -> Mode:
    """The mode the executor runs in for a job of `mode`: a report job needs
    edit permission to write its report, so it is a code-mode run."""
    return Mode.CODE if mode == REPORT else Mode(mode)


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


def task_text(instruction: str, mode: str) -> str:
    """A first attempt's prompt: the instruction, plus report mode's request."""
    return f"{instruction}\n\n{REPORT_INSTRUCTION}" if mode == REPORT else instruction


def prompt(job: Job) -> str:
    """What the executor is told on this attempt.

    The executor keeps no memory between runs, so a revision restates the
    whole task: the original instruction, where it stands, and every piece of
    feedback so far rather than only the latest.
    """
    task = task_text(job.instruction, job.mode)
    if not job.feedback:
        return task
    notes = "\n\n".join(f"{i}. {text}" for i, text in enumerate(job.feedback, 1))
    return (
        f"{task}\n\n---\n"
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
    # Every attempt restates all feedback so far, so the prompt only grows.
    check_prompt(prompt(replace(job, feedback=[*job.feedback, feedback.strip()],
                                attempt=job.attempt + 1)))

    # Keep each attempt's output, check result and report; the next run writes fresh ones.
    for current in (store.output_path(job.id), store.check_path(job.id),
                    store.report_path(job.id)):
        if current.exists():
            os.replace(current, current.with_name(
                f"{current.stem}-{job.attempt}{current.suffix}"))
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
    job.report_path = None
    job.stray_changes = []
    job.report_chars = None
    job.report_truncated = False
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


def _fingerprint(st: os.stat_result) -> list[int]:
    # ctime cannot be set from user space, so any write, rename or touch changes it.
    return [st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def report_fingerprint(job: Job) -> list[int] | None:
    """REPORT.md in the job's copy as it stands, or None if there is none.

    The worker records it before each attempt runs, so collect_report can tell
    a report this attempt wrote from one already there: an earlier attempt's,
    or one the repository had.
    """
    try:
        return _fingerprint(os.lstat(Path(job.workdir) / REPORT_FILE))
    except OSError:
        return None


# A report is read in 20,000-character pages; far past this, it is not a report.
REPORT_MAX_BYTES = 5 * 1024 * 1024


def collect_report(store: JobStore, job: Job) -> None:
    """Save a report job's REPORT.md as jobs/<id>/report.md, after snapshot().

    Only a regular file with one link counts: a symlink could point anywhere
    on the machine, and a hard link could be another file on it, whose
    contents report() would hand back. It is opened without following a
    symlink and checked on the open file, so it cannot be swapped between the
    check and the read. It counts only if this attempt wrote it (see
    report_fingerprint), and a REPORT.md the repository already tracks only
    if the job changed it, so an old report is never taken for this job's.
    At most REPORT_MAX_BYTES are kept, so the executor cannot fill the disk
    or the server's memory with it.
    """
    job.stray_changes = [f for f in job.files_changed if f != REPORT_FILE]
    try:
        # O_NONBLOCK, so a FIFO named REPORT.md cannot hang the open.
        fd = os.open(Path(job.workdir) / REPORT_FILE,
                     os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return  # none, or a symlink
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return
        if job.report_before is not None and _fingerprint(st) == job.report_before:
            return
        tracked = _jgit(job, ["cat-file", "-e", f"{job.base_commit}:{REPORT_FILE}"],
                        check=False)
        if tracked.returncode == 0 and REPORT_FILE not in job.files_changed:
            return
        data = f.read(REPORT_MAX_BYTES + 1)
    job.report_truncated = len(data) > REPORT_MAX_BYTES
    data = data[:REPORT_MAX_BYTES]
    store.report_path(job.id).write_bytes(data)
    job.report_path = str(store.report_path(job.id))
    job.report_chars = len(data.decode("utf-8", errors="replace"))


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
REPORT_LIMIT = 20_000


def read_report(store: JobStore, job_id: str) -> str:
    """A finished report job's whole report."""
    job = store.refresh(store.load(job_id))
    if job.mode != REPORT:
        raise JobError(f"Job {job.id} is a {job.mode} job; only a report job has a report.")
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is still {job.state}; its report is not written yet.")
    if not job.report_path or not Path(job.report_path).is_file():
        raise JobError(
            f"Job {job.id} has no report: it wrote no {REPORT_FILE}. "
            f"Its output is in {store.output_path(job.id)}."
        )
    # Bounded, for a report saved before collect_report capped its size.
    with open(job.report_path, "rb") as f:
        return f.read(REPORT_MAX_BYTES).decode("utf-8", errors="replace")


def report(store: JobStore, job_id: str, offset: int = 0, limit: int = REPORT_LIMIT) -> dict:
    """One page of a report job's report, so a long one can be read in parts
    rather than cut short."""
    if offset < 0:
        raise ValueError("offset must not be negative.")
    if limit <= 0:
        raise ValueError("limit must be positive.")
    text = read_report(store, job_id)
    return {
        "job_id": job_id,
        "total_chars": len(text),
        "offset": offset,
        "text": text[offset:offset + limit],
        "more": offset + limit < len(text),
    }


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
    if job.mode == REPORT:
        raise JobError(
            f"Job {job.id} is a report job: its product is its report, not changes to "
            "apply. Read it with report()."
        )
    if job.state != "succeeded":
        raise JobError(f"Job {job.id} {job.state}; only a succeeded job can be applied.")
    if not job.files_changed:
        raise JobError(f"Job {job.id} changed nothing, so there is nothing to apply.")
    files, pathspecs = _select(job, paths)

    patch = _export(store, job, pathspecs)
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


def _export(store: JobStore, job: Job, pathspecs: list[str]) -> Path:
    """Write the job's changes to its changes.patch, only `pathspecs` if any, and return it.

    Binary, so an image or other non-text file survives the trip. Literal
    pathspecs, so a file named like a glob exports only itself.
    """
    patch = store.path(job.id) / "changes.patch"
    _jgit(job, ["--literal-pathspecs", "diff", "--binary", f"--output={patch}",
                f"{job.base_commit}..HEAD", "--", *pathspecs])
    return patch


def apply_many(store: JobStore, job_ids: list[str], dry_run: bool = False) -> dict:
    """Apply several succeeded jobs to one repository in order, or none of them.

    Applying a fan-out one job at a time finds a conflict between two jobs
    only when the second is reached, with the first already in the
    repository. Here every patch is first applied, in order, to throwaway
    copies of the repository's index and of its working tree's state (see
    _precheck), so the second job is checked on top of the first before
    anything changes. Then each goes through apply, so the ledger,
    applied_paths and applied_unstaged stay exactly as one apply leaves them.

    Only whole jobs: a job partly applied already is refused (use apply for
    the rest of it). Refusals raise, changing nothing. What the pre-check
    or the apply itself finds is returned instead, next to the report:
    applied and not_applied (job ids), overlaps (each file more than one job
    touches, with those jobs), unstaged (jobs that land, or would land,
    unstaged because they touch files with unstaged edits), dry_run, and
    error (None, or which job did not apply and why).
    """
    if not job_ids:
        raise ValueError("Name at least one job.")
    repeated = sorted({i for i in job_ids if job_ids.count(i) > 1})
    if repeated:
        raise ValueError(f"Job(s) named more than once: {', '.join(repeated)}.")
    batch = [store.load(i) for i in job_ids]
    for job in batch:
        if job.state != "succeeded":
            raise JobError(f"Job {job.id} {job.state}; only a succeeded job can be applied.")
        if job.mode == REPORT:
            # apply refuses it, so letting it through would stop the run part way.
            raise JobError(f"Job {job.id} is a report job: it has no changes to apply; "
                           "leave it out and read it with report().")
        if not job.files_changed:
            raise JobError(f"Job {job.id} changed nothing, so there is nothing to apply.")
        if job.applied and all(f in job.applied_paths for f in job.files_changed):
            raise JobError(f"Job {job.id} is already applied; leave it out.")
        if job.applied:
            raise JobError(
                f"Job {job.id} is already partly applied ({', '.join(job.applied_paths)}); "
                "apply_many takes only whole jobs. Use apply for the rest of it."
            )
    repos = sorted({job.repo for job in batch})
    if len(repos) > 1:
        raise JobError(f"The jobs are for different repositories ({', '.join(repos)}); "
                       "apply_many applies to one.")

    touched = {job.id: _touched(job) for job in batch}
    by_path: dict[str, list[str]] = {}
    for job in batch:
        for path in touched[job.id]:
            by_path.setdefault(path, []).append(job.id)
    result = {
        "applied": [],
        "not_applied": list(job_ids),
        "overlaps": {p: ids for p, ids in sorted(by_path.items()) if len(ids) > 1},
        "unstaged": [],
        "dry_run": dry_run,
        "error": None,
    }
    patches = {job.id: _export(store, job, []) for job in batch}
    result["unstaged"], result["error"] = _precheck(store, repos[0], batch, patches, touched)
    if result["error"] or dry_run:
        return result

    result["unstaged"] = []  # from here on, what apply actually did
    for job in batch:
        try:
            apply(store, job.id)
        except JobError as e:
            result["error"] = (
                f"Stopped at job {job.id}: the pre-check passed, so the repository changed "
                f"while the jobs were being applied. {e}"
            )
            break
        result["applied"].append(job.id)
        result["not_applied"].remove(job.id)
        if store.load(job.id).applied_unstaged:
            result["unstaged"].append(job.id)
    return result


def _touched(job: Job) -> list[str]:
    """Every path the job's diff touches, both sides of a rename included."""
    names = _jgit(job, ["diff", "--name-only", "--no-renames", "-z",
                        f"{job.base_commit}..HEAD"]).stdout
    return [name for name in names.split("\0") if name]


def _precheck(
    store: JobStore, repo: str, batch: list[Job], patches: dict[str, Path],
    touched: dict[str, list[str]],
) -> tuple[list[str], str | None]:
    """Apply each patch in turn to scratch copies of the repository's state,
    as apply would: the jobs that would land unstaged, and the first failure.

    Two temporary index files stand in for the repository. One is a copy of
    its index; the other starts as that copy and takes the working tree's
    current content of every file a job touches, so it stands for the
    working tree. apply's `git apply --index` needs a file's index and
    working-tree content to agree, and the patch to fit: then the patch goes
    on both. Otherwise apply falls back to the working tree alone, leaving
    the change unstaged, which here means the second index alone.

    `git apply --cached` and `update-index` write blobs, so git is pointed
    at a scratch object directory that borrows the repository's objects as
    an alternate: the repository's index, objects and files are only read.
    """
    store.root.mkdir(parents=True, exist_ok=True)
    located = _check(run_git(
        ["rev-parse", "--path-format=absolute", "--git-path", "objects", "--git-path", "index"],
        cwd=repo,
    )).stdout.splitlines()
    objects, index = located[0], Path(located[1])
    with tempfile.TemporaryDirectory(prefix="apply-many-", dir=store.root) as tmp:
        staged, tree = Path(tmp) / "index", Path(tmp) / "worktree-index"
        if index.exists():
            shutil.copyfile(index, staged)
            shutil.copyfile(index, tree)
        base_env = dict(os.environ, GIT_OBJECT_DIRECTORY=str(Path(tmp) / "objects"),
                        GIT_ALTERNATE_OBJECT_DIRECTORIES=objects)
        (Path(tmp) / "objects").mkdir()

        def git(index_file: Path, args: list[str]) -> subprocess.CompletedProcess:
            return run_git(args, cwd=repo, env=dict(base_env, GIT_INDEX_FILE=str(index_file)))

        every = sorted({p for paths in touched.values() for p in paths})
        res = git(tree, ["update-index", "--add", "--remove", "--", *every])
        if res.returncode != 0:
            return [], f"Could not read the working tree's state: {res.stderr.strip()}"
        unstaged: list[str] = []
        for n, job in enumerate(batch):
            patch = str(patches[job.id])
            listing = ["--literal-pathspecs", "ls-files", "-s", "-z", "--", *touched[job.id]]
            agree = git(staged, listing).stdout == git(tree, listing).stdout
            fits_index = agree and git(staged, ["apply", "--cached", patch]).returncode == 0
            res = git(tree, ["apply", "--cached", patch])
            if res.returncode != 0:
                onto = (f"on top of job(s) {', '.join(j.id for j in batch[:n])}" if n
                        else "to the repository as it is now")
                return unstaged, (
                    f"Job {job.id} does not apply cleanly {onto}; nothing was changed:\n"
                    f"{res.stderr.strip()}"
                )
            if not fits_index:
                unstaged.append(job.id)
        return unstaged, None


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
