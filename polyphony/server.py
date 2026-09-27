"""MCP server: hand isolated coding tasks to agent CLIs.

Tools are thin wrappers over polyphony.jobs. A failure the caller can act
on becomes a ToolError with a readable message. Anything else is a
Polyphony bug, which the SDK reports as a generic crash and logs here.
"""

from __future__ import annotations

import hashlib
import shutil
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from polyphony import jobs, ledger
from polyphony.config import (
    DEFAULT_MAX_PARALLEL,
    DEFAULT_POOL,
    ConfigError,
    ProjectConfig,
    find_project,
)
from polyphony.executors import EXECUTORS, BaseExecutor, Mode
from polyphony.guard import run_git
from polyphony.jobs import ACTIVE, Job, JobError, JobNotFound, JobStore, active_counts
from polyphony.usage import USAGE_TTL_SECONDS, UsageCache, check_usage, out_of_quota
from polyphony.workspace import WorkspaceError

MAX_WAIT_SECONDS = 240  # below MCP clients' tool-call timeouts
OUTPUT_TAIL_CHARS = 8000
CHECK_TAIL_CHARS = 4000
INSTRUCTION_TAIL_CHARS = 200
MODES = [m.value for m in Mode]
WITHHELD_NOTE = (
    "These secret-looking files were kept out of the job's copy. If the task needs "
    "one, list it under allow_secrets in the project config and delegate again."
)

INSTRUCTIONS = (
    "Polyphony runs a coding task with a separate agent CLI (agy, cursor, or "
    "claude) in a private copy of the repository, so nothing touches it "
    "until you apply it. Use it for well-specified mechanical work and read-only "
    "reviews; keep work that needs your own judgment. The loop is: delegate, "
    "status with wait_seconds, diff, then apply, revise with feedback, or "
    "discard. apply stages the changes without committing."
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


def _check_args(mode: str, timeout_minutes: int, check: str | None) -> None:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}.")
    if timeout_minutes <= 0:
        raise ValueError("timeout_minutes must be positive.")
    if check and mode != "code":
        raise ValueError("check runs only in code mode; review mode edits nothing.")


def _task(instruction: str, brief_path: str | None, root: Path) -> tuple[Path, str] | None:
    """The brief, read and checked, if one was named; refuses a delegate with no task.

    Before any executor is chosen or copy made, so a bad path costs nothing.
    """
    if brief_path:
        return jobs.read_brief(brief_path, root)
    if not instruction.strip():
        raise ValueError("Give the task as instruction, brief_path, or both.")
    return None


def _model(model: str | None, what: str = "model") -> str | None:
    """A model the caller named, or None for the project's. Blank is a mistake,
    not a request for the default: the default is what leaving it out gives."""
    if model is None:
        return None
    if not model.strip():
        raise ValueError(f"{what} is blank; name a model, or leave it out for the project's.")
    return model.strip()


def _check_named(
    name: str,
    executors: dict[str, type[BaseExecutor]],
    running: dict[str, int],
    project: ProjectConfig,
    mode: Mode,
) -> None:
    """An executor the caller named must exist, support the mode, be
    installed, and have a free slot. Quota is not checked: they chose it."""
    if name not in executors:
        raise ValueError(f"Unknown executor {name!r}; expected one of {', '.join(executors)}.")
    if mode not in executors[name].modes:
        raise ValueError(f"Executor {name!r} has no {mode.value} mode.")
    if not executors[name]().is_available():
        raise ValueError(f"Executor {name!r} is not available right now.")
    cap = project.max_parallel.get(name, DEFAULT_MAX_PARALLEL)
    if cap is not None and running.get(name, 0) >= cap:
        raise ValueError(
            f"Executor {name!r} already has {running[name]} active job(s), its limit of {cap}. "
            "Wait for one to finish, or name another executor."
        )


def _choose(
    executor: str | None,
    project: ProjectConfig,
    executors: dict[str, type[BaseExecutor]],
    running: dict[str, int],
    quota: Callable[[str], str | None],
    mode: Mode,
) -> tuple[str, list[dict]]:
    """The executor to use, and the ones passed over on the way with why.

    `quota(name)` gives the reason name is out of quota, or None. It is only
    asked about an executor that would otherwise be chosen, since a check
    takes seconds when not cached.
    """
    if executor is not None:
        _check_named(executor, executors, running, project, mode)
        return executor, []
    skipped: list[dict] = []
    for name in project.pool:
        if name not in executors:
            continue
        if mode not in executors[name].modes:
            skipped.append({"executor": name, "reason": f"has no {mode.value} mode"})
            continue
        if not executors[name]().is_available():
            skipped.append({"executor": name, "reason": "not available"})
            continue
        cap = project.max_parallel.get(name, DEFAULT_MAX_PARALLEL)
        if cap is not None and running.get(name, 0) >= cap:
            skipped.append({"executor": name, "reason": f"at its limit of {cap} active jobs"})
            continue
        reason = quota(name)
        if reason:
            skipped.append({"executor": name, "reason": reason})
            continue
        return name, skipped
    if all(s["reason"] in ("not available", f"has no {mode.value} mode") for s in skipped):
        raise ValueError(
            f"No executor in {', '.join(project.pool)} is available right now "
            f"for {mode.value} mode."
        )
    raise ValueError(
        "No executor can take this job: "
        + "; ".join(f"{s['executor']}: {s['reason']}" for s in skipped)
        + "."
    )


def _summary(store: JobStore, job: Job) -> dict:
    end = job.finished_at or time.time()
    info = {
        "job_id": job.id,
        "state": job.state,
        "executor": job.executor,
        "model": job.model,
        "mode": job.mode,
        "attempt": job.attempt,
        "repo": job.repo,
        "workdir": job.workdir,
        "elapsed_seconds": round(end - (job.started_at or job.created_at), 1),
        # So the caller can confirm the whole task arrived. Revise feedback is not included.
        "instruction_chars": len(job.instruction),
        "instruction_sha256": hashlib.sha256(job.instruction.encode()).hexdigest(),
        "instruction_tail": job.instruction[-INSTRUCTION_TAIL_CHARS:],
    }
    if job.withheld:  # known from the start, so shown even while queued
        info.update(withheld=job.withheld, withheld_note=WITHHELD_NOTE)
    if job.brief_path:
        info["brief_path"] = job.brief_path
    if job.state == "queued":
        return info
    # A running job's output is whatever the executor has written so far.
    output = store.output_path(job.id)
    text = output.read_text(errors="replace") if output.exists() else ""
    info.update(output_tail=text[-OUTPUT_TAIL_CHARS:], output_path=str(output))
    if job.state not in ACTIVE:
        info.update(
            exit_code=job.exit_code,
            error=job.error,
            files_changed=job.files_changed,
            diff_stat=job.diff_stat,
        )
    if job.check_command:
        info["check_command"] = job.check_command
    if job.state not in ACTIVE and job.check_passed is not None:
        check = store.check_path(job.id)
        info.update(
            check_passed=job.check_passed,
            check_exit_code=job.check_exit_code,
            check_output_tail=check.read_text(errors="replace")[-CHECK_TAIL_CHARS:] if check.exists() else "",
            check_output_path=str(check),
        )
    return info


def build_server(
    store: JobStore | None = None,
    projects_dir: Path | None = None,
    executors: dict[str, type[BaseExecutor]] = EXECUTORS,
    usage_check: Callable[[list[str] | None], list[dict]] = check_usage,
    usage_ttl: float = USAGE_TTL_SECONDS,
) -> MCPServer:
    store = store or JobStore()
    server = MCPServer(name="polyphony", instructions=INSTRUCTIONS)
    usage_cache = UsageCache(store.root, check=usage_check, ttl=usage_ttl)
    known = executors  # delegate_many's parameter shadows the name

    def project_for(root: Path) -> ProjectConfig:
        return (find_project(root, projects_dir, home=store.root)
                or ProjectConfig(name=root.name, path=root))

    def create(project: ProjectConfig, instruction: str, executor: str, mode: str,
               timeout_minutes: int, check: str | None,
               brief: tuple[Path, str] | None = None, model: str | None = None) -> Job:
        """check None uses the project's command; "" runs none. model None
        uses the project's for the executor."""
        return jobs.create_job(
            store,
            project=project,
            instruction=instruction,
            executor=executor,
            mode=mode,
            model=model or project.models.get(executor),
            timeout_seconds=timeout_minutes * 60,
            check=project.check if check is None else (check.strip() or None),
            check_timeout_seconds=project.check_timeout_minutes * 60,
            brief=brief,
        )

    def launched(job: Job) -> Job:
        jobs.launch(store, job)
        return store.refresh(store.load(job.id))

    def start(project: ProjectConfig, instruction: str, executor: str, mode: str,
              timeout_minutes: int, check: str | None,
              brief: tuple[Path, str] | None = None, model: str | None = None) -> Job:
        return launched(create(project, instruction, executor, mode, timeout_minutes, check,
                               brief, model))

    def quota_state(name: str) -> dict | None:
        entry = usage_cache.cached(name)
        if entry is None:
            return None
        report = entry["report"]
        state = {
            "checked_at": datetime.fromtimestamp(entry["checked_at"]).isoformat(timespec="seconds"),
            "out_of_quota": out_of_quota(report),
        }
        if not report.get("ok"):
            state["error"] = report.get("error")
        return state

    @server.tool(name="executors")
    def list_executors(repo: str | None = None) -> dict:
        """List the agent CLIs in preference order, whether each is available
        right now, the model it would use, its modes (some are review only),
        its active jobs against its limit, and its quota as of the last usage
        check, if there was one (this never runs a check). Pass repo to use
        that repository's preferences."""
        with _anticipated():
            project = project_for(_toplevel(repo)) if repo else None
            pool = project.pool if project else DEFAULT_POOL
            models = project.models if project else {}
            caps = project.max_parallel if project else {}
            running = active_counts(store)
            listed = []
            for n in pool:
                if n not in executors:
                    continue
                entry = {
                    "name": n,
                    "available": executors[n]().is_available(),
                    "model": models.get(n),
                    "modes": [m.value for m in executors[n].modes],
                    "active_jobs": running.get(n, 0),
                    "max_parallel": caps.get(n, DEFAULT_MAX_PARALLEL),
                }
                quota = quota_state(n)
                if quota is not None:
                    entry["quota"] = quota
                listed.append(entry)
            return {"executors": listed}

    @server.tool()
    def delegate(
        instruction: str = "",
        *,
        repo: str,
        executor: str | None = None,
        mode: str = "code",
        timeout_minutes: int = 30,
        check: str | None = None,
        brief_path: str | None = None,
        model: str | None = None,
    ) -> dict:
        """Start a task with another agent CLI in a private copy of repo,
        returning a job_id at once. mode "code" lets the agent edit files;
        "review" is read-only. executor defaults to the first one in the
        repository's preference order that is available, below its limit of
        active jobs, and not out of quota; "skipped" says why any before it
        were passed over. check is a shell command run in the copy once the
        agent succeeds (code mode only), overriding the repository's
        configured one; "" skips it. Nothing reaches the repository until you
        call apply. Follow up with status.

        brief_path names a UTF-8 file (at most 200 KB; relative to repo) whose
        text follows instruction, after a blank line, as the task; use it for
        any long brief, which can be cut short when passed inline. It is
        copied at once, so later edits to the file don't reach the job. Give
        instruction, brief_path, or both. instruction_chars and
        instruction_tail in the result show the task arrived whole. model
        overrides the repository's model for the executor that runs, so name
        executor with it."""
        with _anticipated():
            _check_args(mode, timeout_minutes, check)
            model = _model(model)
            root = _toplevel(repo)
            brief = _task(instruction, brief_path, root)
            project = project_for(root)
            with store.lock():
                chosen, skipped = _choose(
                    executor, project, executors, active_counts(store),
                    lambda name: out_of_quota(usage_cache.report(name)), Mode(mode),
                )
                job = start(project, instruction, chosen, mode, timeout_minutes, check,
                            brief, model)
            return {**_summary(store, job), "skipped": skipped}

    @server.tool()
    def delegate_many(
        instruction: str = "",
        *,
        repo: str,
        executors: list[str],
        mode: str = "code",
        timeout_minutes: int = 30,
        check: str | None = None,
        brief_path: str | None = None,
        models: dict[str, str] | None = None,
    ) -> dict:
        """Start the same task with each named executor at once, one job per
        executor, each in its own copy of repo. This spends quota on every
        executor named, so use it only for a risky change where comparing two
        diffs is worth that; apply at most one and discard the rest. Starts
        nothing unless every executor is available and below its limit of
        active jobs. check and brief_path work as in delegate; every job gets
        the same brief. models maps an executor named here to the model it
        should use instead of the repository's."""
        with _anticipated():
            _check_args(mode, timeout_minutes, check)
            if not executors:
                raise ValueError("Name at least one executor.")
            repeated = sorted({n for n in executors if executors.count(n) > 1})
            if repeated:
                raise ValueError(f"Executor(s) named more than once: {', '.join(repeated)}.")
            models = models or {}
            stray = [n for n in models if n not in executors]
            if stray:
                raise ValueError(
                    f"models names executor(s) not in executors: {', '.join(stray)}."
                )
            models = {n: _model(m, f"models[{n!r}]") for n, m in models.items()}
            root = _toplevel(repo)
            brief = _task(instruction, brief_path, root)
            project = project_for(root)
            with store.lock():
                running = active_counts(store)
                for name in executors:
                    _check_named(name, known, running, project, Mode(mode))
                # Every copy first, so a failure part way leaves nothing running.
                created: list[Job] = []
                try:
                    for n in executors:
                        created.append(create(project, instruction, n, mode, timeout_minutes,
                                              check, brief, models.get(n)))
                except BaseException:
                    for job in created:
                        shutil.rmtree(store.path(job.id), ignore_errors=True)
                    raise
                started = [launched(job) for job in created]
            return {"jobs": [_summary(store, job) for job in started]}

    @server.tool()
    def revise(job_id: str, feedback: str, timeout_minutes: int | None = None) -> dict:
        """Run a finished job's agent again in the same copy, on top of its
        previous changes, with your feedback on what to fix. The agent gets
        the original instruction plus all feedback so far, and the job's check
        runs again. diff and apply then cover every attempt together. Refused
        once any of the job has been applied. Follow up with status."""
        with _anticipated():
            if timeout_minutes is not None and timeout_minutes <= 0:
                raise ValueError("timeout_minutes must be positive.")
            job = store.load(job_id)
            name = job.executor
            if name not in executors or not executors[name]().is_available():
                raise ValueError(
                    f"Executor {name!r} is not available right now; discard the job "
                    "and delegate it with another executor."
                )
            with store.lock():
                running = active_counts(store)
                cap = project_for(Path(job.repo)).max_parallel.get(name, DEFAULT_MAX_PARALLEL)
                if cap is not None and running.get(name, 0) >= cap:
                    raise ValueError(
                        f"Executor {name!r} already has {running[name]} active job(s), its "
                        f"limit of {cap}. Wait for one to finish."
                    )
                job = jobs.revise(
                    store, job_id, feedback,
                    timeout_seconds=timeout_minutes * 60 if timeout_minutes else None,
                )
                jobs.launch(store, job)
            return _summary(store, store.refresh(store.load(job.id)))

    @server.tool()
    def status(job_id: str, wait_seconds: int = 0) -> dict:
        """A job's state and the tail of its output so far, and once it has
        finished, what it changed and whether its check passed. wait_seconds
        (at most 240) blocks until the job finishes or the time runs out,
        which is cheaper than polling."""
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
    def apply(job_id: str, paths: list[str] | None = None) -> str:
        """Stage a succeeded job's changes in the repository without committing.
        paths applies only those of its changed files, so a mostly good diff
        can land without its bad files; a later call without paths applies
        the rest. If the changes touch files with unstaged edits, they're
        applied to the working tree and left unstaged. Refuses, changing
        nothing, if they don't apply cleanly to the repository as it is now.
        Call discard afterwards."""
        with _anticipated():
            files = jobs.apply(store, job_id, paths)
            job = store.load(job_id)
            if job.applied_unstaged:
                msg = (f"Applied {len(files)} file(s) to the working tree, unstaged because "
                       f"they overlap unstaged edits; not committed: {', '.join(files)}")
            else:
                msg = f"Staged {len(files)} file(s), not committed: {', '.join(files)}"
            rest = [f for f in job.files_changed if f not in job.applied_paths]
            if rest:
                msg += f"\nLeft out, not applied: {', '.join(rest)}"
            return msg

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
        executor ("agy" or "cursor") to check just one. delegate reuses the
        result for a few minutes when choosing an executor."""
        with _anticipated():
            return {"usage": usage_cache.refresh([executor] if executor else None)}

    @server.tool()
    def stats() -> dict:
        """How each executor's (and model's) past jobs turned out: jobs,
        succeeded, revised, applied, discarded, cancelled, check pass rate, and median
        elapsed time. Counted when a job is applied, discarded, or cancelled."""
        return {"executors": ledger.summarize(ledger.read(store.root))}

    return server
