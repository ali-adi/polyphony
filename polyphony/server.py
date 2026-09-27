"""MCP server: hand isolated coding tasks to agent CLIs.

Tools are thin wrappers over polyphony.jobs. A failure the caller can act
on becomes a ToolError with a readable message. Anything else is a
Polyphony bug, which the SDK reports as a generic crash and logs here.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from polyphony import jobs
from polyphony.config import DEFAULT_POOL, ConfigError, ProjectConfig, find_project
from polyphony.executors import EXECUTORS, BaseExecutor, Mode
from polyphony.guard import run_git
from polyphony.jobs import ACTIVE, Job, JobError, JobNotFound, JobStore
from polyphony.usage import check_usage
from polyphony.workspace import WorkspaceError

MAX_WAIT_SECONDS = 240  # below MCP clients' tool-call timeouts
OUTPUT_TAIL_CHARS = 8000
MODES = [m.value for m in Mode]

INSTRUCTIONS = (
    "Polyphony runs a coding task with a separate agent CLI (agy, cursor, or "
    "claude) in a private copy of the repository, so nothing touches it "
    "until you apply it. Use it for well-specified mechanical work and read-only "
    "reviews; keep work that needs your own judgment. The loop is: delegate, "
    "status with wait_seconds, diff, then apply or discard. apply stages the "
    "changes without committing."
)


@contextmanager
def _anticipated():
    try:
        yield
    except (JobError, JobNotFound, ConfigError, WorkspaceError, ValueError) as e:
        raise ToolError(str(e)) from e


def _toplevel(repo: str) -> Path:
    path = Path(repo).expanduser()
    if not path.is_dir():
        raise ValueError(f"{repo} is not a directory.")
    res = run_git(["rev-parse", "--show-toplevel"], cwd=str(path))
    if res.returncode != 0:
        raise ValueError(f"{repo} is not inside a git repository.")
    return Path(res.stdout.strip()).resolve()


def _choose(
    executor: str | None, pool: list[str], executors: dict[str, type[BaseExecutor]]
) -> str:
    if executor is not None:
        if executor not in executors:
            raise ValueError(
                f"Unknown executor {executor!r}; expected one of {', '.join(executors)}."
            )
        if not executors[executor]().is_available():
            raise ValueError(f"Executor {executor!r} is not available right now.")
        return executor
    for name in pool:
        if name in executors and executors[name]().is_available():
            return name
    raise ValueError(f"No executor in {', '.join(pool)} is available right now.")


def _summary(store: JobStore, job: Job) -> dict:
    end = job.finished_at or time.time()
    info = {
        "job_id": job.id,
        "state": job.state,
        "executor": job.executor,
        "model": job.model,
        "mode": job.mode,
        "repo": job.repo,
        "workdir": job.workdir,
        "elapsed_seconds": round(end - (job.started_at or job.created_at), 1),
    }
    if job.state not in ACTIVE:
        output = store.output_path(job.id)
        text = output.read_text() if output.exists() else ""
        info.update(
            exit_code=job.exit_code,
            error=job.error,
            files_changed=job.files_changed,
            diff_stat=job.diff_stat,
            output_tail=text[-OUTPUT_TAIL_CHARS:],
            output_path=str(output),
        )
    return info


def build_server(
    store: JobStore | None = None,
    projects_dir: Path | None = None,
    executors: dict[str, type[BaseExecutor]] = EXECUTORS,
) -> MCPServer:
    store = store or JobStore()
    server = MCPServer(name="polyphony", instructions=INSTRUCTIONS)

    def project_for(root: Path) -> ProjectConfig:
        return find_project(root, projects_dir) or ProjectConfig(name=root.name, path=root)

    @server.tool(name="executors")
    def list_executors(repo: str | None = None) -> dict:
        """List the agent CLIs in preference order, whether each is available
        right now, and the model it would use. Pass repo to use that
        repository's preferences."""
        with _anticipated():
            project = project_for(_toplevel(repo)) if repo else None
            pool = project.pool if project else DEFAULT_POOL
            models = project.models if project else {}
            return {
                "executors": [
                    {"name": n, "available": executors[n]().is_available(), "model": models.get(n)}
                    for n in pool
                    if n in executors
                ]
            }

    @server.tool()
    def delegate(
        instruction: str,
        repo: str,
        executor: str | None = None,
        mode: str = "code",
        timeout_minutes: int = 30,
    ) -> dict:
        """Start a task with another agent CLI in a private copy of repo,
        returning a job_id at once. mode "code" lets the agent edit files;
        "review" is read-only. executor defaults to the first available one in
        the repository's preference order. Nothing reaches the repository until
        you call apply. Follow up with status."""
        with _anticipated():
            if mode not in MODES:
                raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}.")
            if timeout_minutes <= 0:
                raise ValueError("timeout_minutes must be positive.")
            project = project_for(_toplevel(repo))
            chosen = _choose(executor, project.pool, executors)
            job = jobs.create_job(
                store,
                project=project,
                instruction=instruction,
                executor=chosen,
                mode=mode,
                model=project.models.get(chosen),
                timeout_seconds=timeout_minutes * 60,
            )
            jobs.launch(store, job)
            return _summary(store, store.refresh(store.load(job.id)))

    @server.tool()
    def status(job_id: str, wait_seconds: int = 0) -> dict:
        """A job's state and, once it has finished, what it changed and the
        tail of its output. wait_seconds (at most 240) blocks until the job
        finishes or the time runs out, which is cheaper than polling."""
        with _anticipated():
            deadline = time.monotonic() + min(max(wait_seconds, 0), MAX_WAIT_SECONDS)
            while True:
                job = store.refresh(store.load(job_id))
                if job.state not in ACTIVE or time.monotonic() >= deadline:
                    return _summary(store, job)
                time.sleep(1)

    @server.tool()
    def diff(job_id: str) -> str:
        """The full diff a finished job made, against the commit it started from."""
        with _anticipated():
            return jobs.diff(store, job_id)

    @server.tool()
    def apply(job_id: str) -> str:
        """Stage a succeeded job's changes in the repository without committing.
        If they touch files with unstaged edits, they're applied to the working
        tree and left unstaged. Refuses, changing nothing, if they don't apply
        cleanly to the repository as it is now. Call discard afterwards."""
        with _anticipated():
            files = jobs.apply(store, job_id)
            if store.load(job_id).applied_unstaged:
                return (f"Applied {len(files)} file(s) to the working tree, unstaged because "
                        f"they overlap unstaged edits; not committed: {', '.join(files)}")
            return f"Staged {len(files)} file(s), not committed: {', '.join(files)}"

    @server.tool()
    def discard(job_id: str) -> str:
        """Delete a finished job: its copy of the repository and its record.
        Cancel a running job first."""
        with _anticipated():
            jobs.discard(store, job_id)
            return f"Discarded job {job_id}."

    @server.tool()
    def cancel(job_id: str) -> dict:
        """Stop a queued or running job and kill its agent."""
        with _anticipated():
            return _summary(store, jobs.cancel(store, job_id))

    @server.tool(name="jobs")
    def list_jobs(limit: int = 20) -> dict:
        """Recent jobs, newest first."""
        return {
            "jobs": [
                {
                    "job_id": j.id,
                    "state": store.refresh(j).state,
                    "executor": j.executor,
                    "project": j.project,
                    "created": datetime.fromtimestamp(j.created_at).isoformat(timespec="seconds"),
                    "instruction": j.instruction[:100],
                }
                for j in store.all()[:limit]
            ]
        }

    @server.tool()
    def usage(executor: str | None = None) -> dict:
        """How much quota agy and cursor have left, as each CLI reports it:
        limits, percentages, and reset times. Takes several seconds. Pass
        executor ("agy" or "cursor") to check just one."""
        with _anticipated():
            return {"usage": check_usage([executor] if executor else None)}

    return server
