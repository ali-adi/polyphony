"""Delegated jobs: one executor run in a private copy of the repository, tracked on disk.

State lives in ~/.polyphony/jobs/<id>/ rather than in any client's session,
so a job started from one MCP client can be checked from another.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from polyphony.config import ProjectConfig
from polyphony.guard import run_git
from polyphony.workspace import Workspace, WorkspaceError

DEFAULT_HOME = Path.home() / ".polyphony"

ACTIVE = ("queued", "running")


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
    # Set when apply had to leave the changes unstaged (they touch files with unstaged edits).
    applied_unstaged: bool = False


class JobStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else DEFAULT_HOME
        self.dir = self.root / "jobs"

    def path(self, job_id: str) -> Path:
        return self.dir / job_id

    def output_path(self, job_id: str) -> Path:
        return self.path(job_id) / "output.txt"

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

    def refresh(self, job: Job) -> Job:
        """Mark a job whose worker vanished without recording a result."""
        if job.state != "running" or not job.pid or _alive(job.pid):
            return job
        current = self.load(job.id)  # it may have finished since `job` was read
        if current.state != "running":
            return current
        current.state = "died"
        current.error = "The worker process exited without recording a result."
        current.finished_at = time.time()
        self.save(current)
        return current


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


def create_job(
    store: JobStore,
    project: ProjectConfig,
    instruction: str,
    executor: str,
    mode: str,
    model: str | None = None,
    timeout_seconds: int = 1800,
) -> Job:
    """Copy the repository, provision the copy, and record the job as queued."""
    job_id = new_job_id()
    workdir = store.path(job_id) / "repo"
    ws = Workspace.create(
        project.path, workdir,
        exclude=tuple(str(e.get("path", "")) for e in project.provision),
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
        instruction=instruction,
        timeout_seconds=timeout_seconds,
        workdir=str(ws.path),
        base_commit=_git(["rev-parse", "HEAD"], str(ws.path)).stdout.strip(),
        model=model,
        link_paths=[
            str(e["path"]).rstrip("/") for e in project.provision if e.get("mode") == "link"
        ],
        overlay_skipped=ws.skipped,
    )
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
            [sys.executable, "-m", "polyphony.worker", str(job_dir)],
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


def cancel(store: JobStore, job_id: str) -> Job:
    """Stop a queued or running job, killing its executor with it."""
    job = store.load(job_id)
    if job.state not in ACTIVE:
        return job
    if job.pgid:
        try:
            os.killpg(job.pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    job = store.load(job_id)
    job.state = "cancelled"
    job.error = "Cancelled."
    job.finished_at = time.time()
    store.save(job)
    return job


def snapshot(job: Job) -> None:
    """Commit the executor's work in the copy and record what changed.

    Plain `git add -A` skips gitignored clone-mode paths on its own. A
    link-mode path is a symlink, which a directory pattern like `env/` does
    not ignore, so each one is unstaged explicitly. An exclude pathspec
    can't do this: git exits 1 when an excluded path is also ignored.

    The commit lives only in the job's private copy. apply turns it into a
    patch, so its message and author never reach the repository's history.
    """
    cwd = job.workdir
    _git(["add", "-A"], cwd)
    for path in job.link_paths:
        _git(["rm", "-r", "--cached", "--ignore-unmatch", "-q", "--", path], cwd)
    if run_git(["diff", "--cached", "--quiet"], cwd=cwd).returncode != 0:
        _git(
            [
                "-c", "user.name=Polyphony",
                "-c", "user.email=polyphony@localhost",
                "commit", "--no-verify", "-q", "-m", f"polyphony job {job.id}",
            ],
            cwd,
        )
    names = _git(["diff", "--name-only", f"{job.base_commit}..HEAD"], cwd).stdout
    job.files_changed = [line for line in names.splitlines() if line.strip()]
    job.diff_stat = _git(["diff", "--stat", f"{job.base_commit}..HEAD"], cwd).stdout.rstrip()


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    res = run_git(args, cwd=cwd)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {res.stderr.strip()}")
    return res


DIFF_LIMIT = 60_000


def diff(store: JobStore, job_id: str, limit: int = DIFF_LIMIT) -> str:
    """The job's changes against the commit it started from."""
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is still {job.state}.")
    text = _git(["diff", f"{job.base_commit}..HEAD"], job.workdir).stdout
    if not text:
        return f"Job {job.id} changed nothing."
    if len(text) > limit:
        return text[:limit] + (
            f"\n\n[Truncated at {limit} of {len(text)} characters. Full diff: "
            f"git -C {job.workdir} diff {job.base_commit}..HEAD]"
        )
    return text


def apply(store: JobStore, job_id: str) -> list[str]:
    """Stage a succeeded job's changes in the repository, without committing.

    The only operation that writes to the user's repository. `git apply` is
    atomic: if any hunk does not apply to the repository as it is now,
    including over uncommitted edits, nothing is changed.
    """
    job = store.load(job_id)
    if job.state != "succeeded":
        raise JobError(f"Job {job.id} {job.state}; only a succeeded job can be applied.")
    if not job.files_changed:
        raise JobError(f"Job {job.id} changed nothing, so there is nothing to apply.")

    patch = store.path(job.id) / "changes.patch"
    _git(["diff", "--binary", f"--output={patch}", f"{job.base_commit}..HEAD"], job.workdir)
    res = run_git(["apply", "--index", str(patch)], cwd=job.repo)
    if res.returncode != 0 and run_git(["apply", "--check", str(patch)], cwd=job.repo).returncode == 0:
        # The job started from the working tree, so a file the user had edited but not staged
        # no longer matches the index. Apply to the working tree only, leaving staging to them.
        res = run_git(["apply", str(patch)], cwd=job.repo)
        if res.returncode == 0:
            job.applied_unstaged = True
            store.save(job)
    if res.returncode != 0:
        raise JobError(
            f"Job {job.id} does not apply cleanly to the repository as it is now; "
            f"nothing was changed:\n{res.stderr.strip()}"
        )
    return job.files_changed


def discard(store: JobStore, job_id: str) -> None:
    """Delete a finished job: its copy and its record."""
    job = store.load(job_id)
    if job.state in ACTIVE:
        raise JobError(f"Job {job.id} is {job.state}; cancel it before discarding.")
    shutil.rmtree(store.path(job.id), ignore_errors=True)
