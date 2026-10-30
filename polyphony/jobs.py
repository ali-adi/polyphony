from __future__ import annotations

import fcntl
import filecmp
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
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

from polyphony import ledger
from polyphony.config import DEFAULT_HOME, ProjectConfig
from polyphony.guard import run_git
from polyphony.workspace import DIFF_FLAGS, Workspace, WorkspaceError, copy_git

ACTIVE = ("queued", "running")
# agy takes the whole prompt as one argv string; Linux caps one argument at 128 KiB (MAX_ARG_STRLEN).
MAX_PROMPT_BYTES = 120 * 1024
MAX_BRIEF_BYTES = 100 * 1024
QUEUE_GRACE_SECONDS = 60
CANCEL_GRACE_SECONDS = 2

CODE = "code"
REPORT = "report"
MODES = (CODE, REPORT)
REPORT_FILE = "REPORT.md"
REPORT_INSTRUCTION = (
    f"Write your complete findings as Markdown to {REPORT_FILE} at the repository "
    "root. That file is the product of this task, so put everything in it, not only "
    "in your reply. Change no other file."
)


class JobNotFound(Exception):
    pass


class JobError(Exception):
    pass


class JobDisowned(JobError):
    pass


@dataclass
class Job:
    id: str
    project: str
    repo: str
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
    overlay_skipped: list[str] = field(default_factory=list)
    applied_unstaged: bool = False
    check_command: str | None = None
    check_timeout_seconds: int = 600
    check_exit_code: int | None = None
    check_passed: bool | None = None
    check_pgid: int | None = None
    outcome: str | None = None
    executor_pgid: int | None = None
    feedback: list[str] = field(default_factory=list)
    attempt: int = 1
    applied_paths: list[str] = field(default_factory=list)
    git_dir: str | None = None
    queued_at: float | None = None
    withheld: list[str] = field(default_factory=list)
    env_scrub: list[str] = field(default_factory=list)
    brief_path: str | None = None
    report_path: str | None = None
    stray_changes: list[str] = field(default_factory=list)
    head_commit: str | None = None
    report_before: list[int] | None = None
    report_chars: int | None = None
    report_truncated: bool = False

    @property
    def applied(self) -> bool:
        return bool(self.applied_paths)


_JOB_FIELDS = {f.name for f in fields(Job)}


class JobStore:
    def __init__(self, root: Path | None = None):
        # An MCP config's env block passes POLYPHONY_HOME=~/... unexpanded.
        self.root = (Path(root) if root is not None else DEFAULT_HOME).expanduser().resolve()
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
        d = self.path(job.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"job.json.{os.getpid()}-{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps(asdict(job), indent=2))
        os.replace(tmp, d / "job.json")

    def load(self, job_id: str) -> Job:
        f = self.path(job_id) / "job.json"
        if not f.exists():
            raise JobNotFound(f"No job {job_id!r} in {self.dir}.")
        data = json.loads(f.read_text())
        return Job(**{k: v for k, v in data.items() if k in _JOB_FIELDS})

    def all(self) -> list[Job]:
        if not self.dir.is_dir():
            return []
        jobs = [self.load(p.name) for p in self.dir.iterdir() if (p / "job.json").exists()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    @contextmanager
    def lock(self):
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
        if job.state == "running" and job.pid and not _alive(job.pid):
            error = "The worker process exited without recording a result."
        elif job.state == "queued" and _stuck(job):
            error = "The job's worker never started."
        else:
            return job
        with self.lock():
            current = self.load(job.id)
            if current.state != job.state or current.attempt != job.attempt:
                return current
            if current.state == "queued" and not _stuck(current):
                return current
            if current.state == "running":
                _signal_groups((current.executor_pgid, current.check_pgid), signal.SIGKILL)
                current.executor_pgid = current.check_pgid = None
            current.state = "died"
            current.error = error
            current.finished_at = time.time()
            self.save(current)
            return current


def active_count(store: JobStore) -> int:
    return sum(j.state in ACTIVE for j in map(store.refresh, store.all()))


def _stuck(job: Job) -> bool:
    return time.time() - (job.queued_at or job.created_at) > QUEUE_GRACE_SECONDS


def claim(store: JobStore, job_id: str, attempt: int) -> Job | None:
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


def save_running(store: JobStore, job: Job) -> None:
    with store.lock():
        try:
            current = store.load(job.id)
        except JobNotFound:
            raise JobDisowned(f"Job {job.id} was deleted; this worker stops.") from None
        if current.state != "running" or current.attempt != job.attempt or current.pid != job.pid:
            raise JobDisowned(f"Job {job.id} is {current.state} now; this worker stops.")
        store.save(job)


def _signal_groups(pgids: Iterable[int | None], sig: int) -> None:
    for pgid in pgids:
        if pgid:
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                pass  # already gone, or (macOS) still being reaped


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # macOS: EPERM while a killed group is still being reaped
    return True


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
    file = (base / Path(path).expanduser()).resolve()
    if not file.exists():
        raise ValueError(f"brief_path {path!r}: no such file ({file}).")
    if not file.is_file():
        raise ValueError(f"brief_path {path!r}: {file} is not a regular file.")
    try:
        with file.open("rb") as f:
            data = f.read(MAX_BRIEF_BYTES + 1)
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
    if brief is None:
        return instruction
    return f"{instruction}\n\n{brief}" if instruction.strip() else brief


def create_job(
    store: JobStore,
    project: ProjectConfig,
    instruction: str,
    mode: str,
    model: str | None = None,
    timeout_seconds: int = 1800,
    check: str | None = None,
    check_timeout_seconds: int = 600,
    brief: tuple[Path, str] | None = None,
) -> Job:
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
        check_command=check if mode == CODE else None,
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
    stale = ws.path / REPORT_FILE
    if not (stale.is_symlink() or stale.is_file()):
        return
    if copy_git(["cat-file", "-e", f"{base_commit}:{REPORT_FILE}"],
                ws.git_dir, ws.path).returncode != 0:
        stale.unlink()


def launch(store: JobStore, job: Job) -> None:
    job_dir = store.path(job.id)
    with store.lock():
        current = store.load(job.id)
        if current.state == "queued" and current.attempt == job.attempt:
            current.queued_at = time.time()
            store.save(current)
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
    return f"{instruction}\n\n{REPORT_INSTRUCTION}" if mode == REPORT else instruction


def prompt(job: Job) -> str:
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
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is still {job.state}; wait for it or cancel it first.")
    if job.mode not in MODES:
        raise JobError(f"Job {job.id} is a {job.mode} job, a mode Polyphony no longer has; "
                       "discard it and delegate again.")
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
    check_prompt(prompt(replace(job, feedback=[*job.feedback, feedback.strip()],
                                attempt=job.attempt + 1)))

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
    job.pid = job.pgid = job.executor_pgid = job.check_pgid = None
    job.started_at = job.finished_at = job.exit_code = job.error = None
    job.check_exit_code = job.check_passed = None
    job.report_path = None
    job.stray_changes = []
    job.report_chars = None
    job.report_truncated = False
    job.outcome = None
    store.save(job)
    return job


def cancel(store: JobStore, job_id: str) -> Job:
    with store.lock():
        job = store.load(job_id)
        if job.state not in ACTIVE:
            return job
        groups = [g for g in (job.pgid, job.executor_pgid, job.check_pgid) if g]
        _signal_groups(groups, signal.SIGTERM)
        job.state = "cancelled"
        job.error = "Cancelled."
        job.finished_at = time.time()
        _record(store, job, "cancelled")
    deadline = time.monotonic() + CANCEL_GRACE_SECONDS
    while groups and time.monotonic() < deadline:
        time.sleep(0.05)
        groups = [g for g in groups if _group_alive(g)]
    _signal_groups(groups, signal.SIGKILL)
    shutil.rmtree(store.path(job.id), ignore_errors=True)
    return job


def notify(job: Job) -> None:
    if sys.platform != "darwin" or os.environ.get("POLYPHONY_NO_NOTIFY"):
        return
    script = ["-e", "on run argv", "-e",
              "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run"]
    try:
        subprocess.run(["osascript", *script, f"Polyphony: {job.mode} job {job.state}",
                        f"{job.id}: {job.instruction[:100]}"],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _record(store: JobStore, job: Job, outcome: str) -> None:
    job.outcome = outcome
    store.save(job)
    ledger.record(store.root, job, outcome)


def snapshot(job: Job) -> None:
    _jgit(job, ["add", "-A"])
    for path in job.link_paths:
        _jgit(job, ["rm", "-r", "--cached", "--ignore-unmatch", "-q", "--", path])
    if _jgit(job, ["diff", "--cached", "--quiet"], check=False).returncode != 0:
        _jgit(job, [
            "-c", "user.name=Polyphony",
            "-c", "user.email=polyphony@localhost",
            "commit", "--no-verify", "-q", "-m", f"polyphony job {job.id}",
        ])
    job.head_commit = _jgit(job, ["rev-parse", "--verify", "HEAD^{commit}"]).stdout.strip()
    # -z: git C-quotes non-ASCII, quote and newline paths otherwise.
    names = _jgit(job, ["diff", "--name-only", "-z", _range(job)]).stdout
    job.files_changed = [name for name in names.split("\0") if name]
    job.diff_stat = _jgit(job, ["diff", "--stat", "--no-color", _range(job)]).stdout.rstrip()


def pending_changes(job: Job) -> list[str]:
    # Without --no-optional-locks, status takes index.lock and can fail the worker's own git.
    out = _jgit(job, ["--no-optional-locks", "status", "--porcelain", "-z", "--no-renames"],
                check=False).stdout
    return [entry[3:] for entry in out.split("\0") if len(entry) > 3]


def _range(job: Job) -> str:
    return f"{job.base_commit}..{job.head_commit or 'HEAD'}"


def _fingerprint(st: os.stat_result) -> list[int]:
    # ctime cannot be set from user space, so any write, rename or touch changes it.
    return [st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def report_fingerprint(job: Job) -> list[int] | None:
    try:
        return _fingerprint(os.lstat(Path(job.workdir) / REPORT_FILE))
    except OSError:
        return None


REPORT_MAX_BYTES = 5 * 1024 * 1024


def collect_report(store: JobStore, job: Job) -> None:
    job.stray_changes = [f for f in job.files_changed if f != REPORT_FILE]
    try:
        # O_NONBLOCK: opening a FIFO named REPORT.md would otherwise hang.
        fd = os.open(Path(job.workdir) / REPORT_FILE,
                     os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return
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
        try:
            save_running(store, job)
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
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass  # already gone, or (macOS) still being reaped
            job.check_pgid = None
            save_running(store, job)
    _restore(job, snapshot_head)


CHECK_SCRUB = ("*_API_KEY", "*_TOKEN", "*_SECRET", "*_PASSWORD", "*_CREDENTIALS")


def scrub_env(env: Mapping[str, str], patterns: Iterable[str]) -> dict[str, str]:
    patterns = tuple(patterns)
    return {k: v for k, v in env.items()
            if not any(fnmatch.fnmatchcase(k, p) for p in patterns)}


def _restore(job: Job, head: str) -> None:
    _jgit(job, ["reset", "--hard", "-q", head])
    keep = [arg for path in job.link_paths for arg in ("-e", f"/{path}")]
    _jgit(job, ["clean", "-f", "-d", "-q", *keep])


# LaunchServices and Apple events can start a process outside the sandbox (`open -a`, `osascript`).
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
        # bwrap cannot mount a tmpfs on a symlink, and /var/run's target /run is already hidden.
        hidden = [d for d in ("/run", "/var/run", "/tmp", "/var/tmp")
                  if os.path.isdir(d) and not os.path.islink(d)]
        linked = [os.path.realpath(Path(job.repo) / p) for p in job.link_paths]
        return [exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                *(arg for d in hidden for arg in ("--tmpfs", d)),
                *(arg for p in (str(work.parent), *linked) if os.path.exists(p)
                  for arg in ("--ro-bind", p, p)),
                "--bind", str(work), str(work), "--ro-bind", str(gitdir), str(gitdir),
                "--bind", str(tmp), str(tmp),
                "--unshare-all", "--new-session", "--die-with-parent", "--"]
    return None


def _jgit(job: Job, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    res = copy_git(args, job.git_dir or Path(job.workdir) / ".git", job.workdir)
    return _check(res) if check else res


def _check(res: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(res.args[1:])} failed: {res.stderr.strip()}")
    return res


DIFF_LIMIT = 60_000
REPORT_LIMIT = 20_000


def read_report(store: JobStore, job_id: str) -> str:
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
    with open(job.report_path, "rb") as f:
        return f.read(REPORT_MAX_BYTES).decode("utf-8", errors="replace")


def report(store: JobStore, job_id: str, offset: int = 0, limit: int = REPORT_LIMIT) -> dict:
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
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is still {job.state}.")
    text = _jgit(job, ["diff", *DIFF_FLAGS, _range(job)]).stdout
    if not text:
        return f"Job {job.id} changed nothing."
    if len(text) > limit:
        return text[:limit] + (
            f"\n\n[Truncated at {limit} of {len(text)} characters. Full diff: "
            f"git -C {job.workdir} diff {_range(job)}]"
        )
    return text


def apply(store: JobStore, job_id: str, paths: list[str] | None = None) -> tuple[list[str], Job]:
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
    _require_repo(job.repo)

    patch = _export(store, job, pathspecs)
    covered = _covered(job, pathspecs)
    # `apply --index` compares stat data, so a touched but unchanged file looks like an unstaged edit.
    run_git(["update-index", "-q", "--refresh"], cwd=job.repo)
    lost: list[str] = []
    with tempfile.TemporaryDirectory(prefix="saved-", dir=store.path(job.id)) as keep:
        saved = _save(Path(job.repo), covered, Path(keep))
        res = run_git(["apply", "--index", str(patch)], cwd=job.repo)
        unstaged = False
        if res.returncode != 0:
            lost = _put_back(Path(job.repo), saved)
            if (not lost and _unstaged_edits(job.repo, covered)
                    and run_git(["apply", "--check", str(patch)], cwd=job.repo).returncode == 0):
                res = run_git(["apply", str(patch)], cwd=job.repo)
                unstaged = res.returncode == 0
                if not unstaged:
                    lost = _put_back(Path(job.repo), saved)
    if res.returncode != 0:
        changed = (f"git stopped part way, and these could not be put back as they were: "
                   f"{', '.join(lost)}" if lost else "nothing was changed")
        raise JobError(
            f"Job {job.id} does not apply cleanly to the repository as it is now; "
            f"{changed}:\n{res.stderr.strip()}"
        )
    job.applied_unstaged = unstaged
    job.applied_paths += files
    store.save(job)
    if job.outcome is None:
        _record(store, job, "applied")
    if all(f in job.applied_paths for f in job.files_changed):
        shutil.rmtree(store.path(job.id), ignore_errors=True)
    return files, job


def _export(store: JobStore, job: Job, pathspecs: list[str]) -> Path:
    patch = store.path(job.id) / "changes.patch"
    _jgit(job, ["--literal-pathspecs", "diff", "--binary", *DIFF_FLAGS, f"--output={patch}",
                _range(job), "--", *pathspecs])
    return patch


def _require_repo(repo: str) -> None:
    if not Path(repo).is_dir():
        raise JobError(f"The repository {repo} no longer exists (moved or deleted?); "
                       "nothing was applied.")


def _covered(job: Job, pathspecs: list[str]) -> list[str]:
    touched = _touched(job)
    if not pathspecs:
        return touched
    return [p for p in touched if any(p == s or p.startswith(s + "/") for s in pathspecs)]


def _unstaged_edits(repo: str, paths: list[str]) -> bool:
    res = run_git(["--literal-pathspecs", "diff", "--no-ext-diff", "--quiet", "--", *paths],
                  cwd=repo)
    return res.returncode == 1


def _save(repo: Path, paths: list[str], into: Path) -> list[tuple[str, str, str, int]]:
    saved = []
    for n, rel in enumerate(paths):
        parts = rel.split("/")
        if any(repo.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts))):
            continue
        path = repo / rel
        if path.is_symlink():
            saved.append((rel, "link", os.readlink(path), 0))
        elif path.is_dir():
            saved.append((rel, "dir", "", 0))
        elif path.is_file():
            copy = into / str(n)
            shutil.copyfile(path, copy)
            saved.append((rel, "file", str(copy), path.stat().st_mode & 0o777))
        elif not path.exists():
            saved.append((rel, "absent", "", 0))
    return saved


def _put_back(repo: Path, saved: list[tuple[str, str, str, int]]) -> list[str]:
    def clear(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        elif os.path.lexists(path):
            path.unlink()

    rank = {"absent": 0, "dir": 1, "file": 2, "link": 2}
    lost = []
    for rel, kind, value, mode in sorted(
        saved, key=lambda s: (rank[s[1]], -s[0].count("/") if s[1] == "absent" else s[0].count("/"))
    ):
        path = repo / rel
        try:
            if kind == "absent":
                clear(path)
            elif kind == "dir":
                if not path.is_dir() or path.is_symlink():
                    clear(path)
                    path.mkdir(parents=True)
            elif kind == "link":
                if not path.is_symlink() or os.readlink(path) != value:
                    clear(path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(value, path)
            elif (path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != mode
                  or not filecmp.cmp(value, path, shallow=False)):
                clear(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(value, path)
                os.chmod(path, mode)
        except OSError:
            lost.append(rel)
    return lost


def apply_many(
    store: JobStore, job_ids: list[str], dry_run: bool = False,
    paths: dict[str, list[str]] | None = None,
) -> dict:
    if not job_ids:
        raise ValueError("Name at least one job.")
    repeated = sorted({i for i in job_ids if job_ids.count(i) > 1})
    if repeated:
        raise ValueError(f"Job(s) named more than once: {', '.join(repeated)}.")
    paths = paths or {}
    stray = sorted(set(paths) - set(job_ids))
    if stray:
        raise ValueError(f"paths names job(s) not in job_ids: {', '.join(stray)}.")
    batch = [store.load(i) for i in job_ids]
    for job in batch:
        if job.state != "succeeded":
            raise JobError(f"Job {job.id} {job.state}; only a succeeded job can be applied.")
        if job.mode == REPORT:
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
    _require_repo(repos[0])

    pathspecs = {job.id: _select(job, paths.get(job.id))[1] for job in batch}
    touched = {job.id: _covered(job, pathspecs[job.id]) for job in batch}
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
    patches = {job.id: _export(store, job, pathspecs[job.id]) for job in batch}
    result["unstaged"], result["error"] = _precheck(store, repos[0], batch, patches, touched)
    if result["error"] or dry_run:
        return result

    result["unstaged"] = []
    for job in batch:
        try:
            _, applied = apply(store, job.id, paths.get(job.id))
        except JobError as e:
            result["error"] = (
                f"Stopped at job {job.id}: the pre-check passed, so the repository changed "
                f"while the jobs were being applied. {e}"
            )
            break
        result["applied"].append(job.id)
        result["not_applied"].remove(job.id)
        if applied.applied_unstaged:
            result["unstaged"].append(job.id)
    return result


def _touched(job: Job) -> list[str]:
    names = _jgit(job, ["diff", "--name-only", "--no-renames", "-z", _range(job)]).stdout
    return [name for name in names.split("\0") if name]


def _precheck(
    store: JobStore, repo: str, batch: list[Job], patches: dict[str, Path],
    touched: dict[str, list[str]],
) -> tuple[list[str], str | None]:
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
            # core.splitIndex keeps entries in a sharedindex.* file that git reads from beside the index.
            for shared in index.parent.glob("sharedindex.*"):
                shutil.copyfile(shared, Path(tmp) / shared.name)
        base_env = dict(os.environ, GIT_OBJECT_DIRECTORY=str(Path(tmp) / "objects"),
                        GIT_ALTERNATE_OBJECT_DIRECTORIES=objects)
        (Path(tmp) / "objects").mkdir()

        def git(index_file: Path, args: list[str]) -> subprocess.CompletedProcess:
            return run_git(["-c", "core.splitIndex=false", *args], cwd=repo,
                           env=dict(base_env, GIT_INDEX_FILE=str(index_file)))

        every = sorted({p for paths in touched.values() for p in paths})
        # update-index cannot read a directory as a file, except a submodule's (it records the commit).
        every = [p for p in every if not (Path(repo, p).is_dir() and not Path(repo, p).is_symlink()
                                          and not Path(repo, p, ".git").exists())]
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
    partner = _renames(job)
    if paths is None:
        files = [f for f in job.files_changed if f not in job.applied_paths]
        if not files:
            raise JobError(f"Job {job.id} is already applied in full.")
        if not job.applied_paths:
            return files, []
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
    out = _jgit(
        job, ["diff", "--name-status", "-z", "--find-renames", _range(job)]
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


AUTO_GC_SECONDS = 7 * 86400


def gc(store: JobStore, older_than_seconds: float, dry_run: bool = False) -> list[GcRecord]:
    now = time.time()

    def expired(job: Job) -> bool:
        return (job.state not in ACTIVE
                and now - (job.finished_at or job.created_at) >= older_than_seconds)

    removed = []
    for job in store.all():
        if not expired(store.refresh(job)):
            continue
        size = disk_usage(store.path(job.id))
        if not dry_run:
            with store.lock():
                try:
                    job = store.refresh(store.load(job.id))
                except JobNotFound:
                    continue
                if not expired(job):
                    continue
                if job.outcome is None:
                    ledger.record(store.root, job, "discarded", via="gc")
                shutil.rmtree(store.path(job.id), ignore_errors=True)
        removed.append(GcRecord(job.id, job.state, now - (job.finished_at or job.created_at), size))
    return removed


def disk_usage(path: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except FileNotFoundError:
                pass
    return total
