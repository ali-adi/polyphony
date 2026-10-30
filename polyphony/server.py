from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from polyphony import agy, jobs, ledger
from polyphony.config import DEFAULT_MODELS, ConfigError, ProjectConfig, find_project
from polyphony.guard import run_git
from polyphony.jobs import ACTIVE, Job, JobError, JobNotFound, JobStore, active_count
from polyphony.usage import USAGE_TTL_SECONDS, UsageCache, agy_usage, gate
from polyphony.workspace import WorkspaceError

# MCP clients time a tool call out at about 120 s.
MAX_WAIT_SECONDS = 100
RECENT_EVENTS = 8
FILES_SHOWN = 50
CHECK_TAIL_CHARS = 4000
INSTRUCTION_TAIL_CHARS = 200
# communicate(timeout=) overflows at about 35,791 minutes; a day is far below.
MAX_TIMEOUT_MINUTES = 24 * 60
WITHHELD_NOTE = (
    "These secret-looking files were kept out of the job's copy. If the task needs "
    "one, list it under allow_secrets in the project config and delegate again."
)
INSTRUCTIONS = (
    "Polyphony runs a task with Antigravity (agy, Gemini models) in a private "
    "copy of the repository; nothing touches the repository until you apply. "
    "Use it for a non-Claude view (a report-mode audit or judge seat) and for "
    "well-specified mechanical code changes; keep work that needs your own "
    "judgment. Loop: delegate, status with wait_seconds, diff, then apply, "
    "revise with feedback, or discard; read a report-mode result with report. "
    "apply stages the changes without committing. With more than one job "
    "running, call the wait tool on all of them instead of status on each."
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


def _check_timeout(timeout_minutes: int) -> None:
    if timeout_minutes <= 0:
        raise ValueError("timeout_minutes must be positive.")
    if timeout_minutes > MAX_TIMEOUT_MINUTES:
        raise ValueError(
            f"timeout_minutes must be at most {MAX_TIMEOUT_MINUTES} (24 hours), "
            f"not {timeout_minutes}.")


def _check_args(mode: str, timeout_minutes: int, check: str | None) -> None:
    if mode not in jobs.MODES:
        raise ValueError(f"mode must be one of {', '.join(jobs.MODES)}, not {mode!r}.")
    _check_timeout(timeout_minutes)
    if check and mode != "code":
        raise ValueError(
            f"check runs only in code mode; {mode} mode changes no code to check.")


def _checked_brief(
    instruction: str, brief_path: str | None, repo: str, mode: str
) -> tuple[Path, str] | None:
    base = Path(repo).expanduser().resolve()
    brief = jobs.read_brief(brief_path, base) if brief_path else None
    if brief is None and not instruction.strip():
        raise ValueError("Give the task as instruction, brief_path, or both.")
    jobs.check_prompt(jobs.task_text(jobs.with_brief(instruction, brief and brief[1]), mode))
    return brief


def _model(model: str | None, what: str = "model") -> str | None:
    if model is None:
        return None
    if not model.strip():
        raise ValueError(f"{what} is blank; name a model, or leave it out for the project's.")
    return model.strip()


def _check_ready(store: JobStore, project: ProjectConfig) -> None:
    if agy.binary() is None:
        raise ValueError("agy is not installed.")
    running, cap = active_count(store), project.max_parallel
    if cap is not None and running >= cap:
        raise ValueError(
            f"{running} job(s) are active, the limit of {cap}. Wait for one to finish.")


def _tail(path: Path, chars: int) -> str:
    try:
        with path.open("rb") as f:
            f.seek(max(0, f.seek(0, os.SEEK_END) - chars * 4))
            return f.read(chars * 4).decode("utf-8", errors="replace")[-chars:]
    except FileNotFoundError:
        return ""


def _activity(store: JobStore, job: Job) -> dict:
    stream = agy.events(store.output_path(job.id))
    recent: list[str] = []
    for event in stream:
        if isinstance(event, dict) and event.get("event") in ("init", "result"):
            continue
        line = agy.describe(event)
        if not recent or recent[-1] != line:
            recent.append(line)
    info: dict = {"recent": recent[-RECENT_EVENTS:]}
    final = agy.result_event(store.output_path(job.id))
    if final is not None:
        info["response"] = final.get("response")
    if job.state == "running" and Path(job.workdir).is_dir():
        info["files_touched"] = jobs.pending_changes(job)[:FILES_SHOWN]
    return info


def _summary(store: JobStore, job: Job) -> dict:
    end = job.finished_at or time.time()
    info = {
        "job_id": job.id,
        "state": job.state,
        "model": job.model,
        "mode": job.mode,
        "attempt": job.attempt,
        "repo": job.repo,
        "workdir": job.workdir,
        "elapsed_seconds": round(end - (job.started_at or job.created_at), 1),
        "instruction_chars": len(job.instruction),
        "instruction_sha256": hashlib.sha256(job.instruction.encode()).hexdigest(),
        "instruction_tail": job.instruction[-INSTRUCTION_TAIL_CHARS:],
    }
    if job.withheld:
        info.update(withheld=job.withheld, withheld_note=WITHHELD_NOTE)
    if job.brief_path:
        info["brief_path"] = job.brief_path
    if job.state == "queued":
        return info
    info.update(_activity(store, job), output_path=str(store.output_path(job.id)))
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
            check_output_tail=_tail(check, CHECK_TAIL_CHARS),
            check_output_path=str(check),
        )
    if job.mode == jobs.REPORT and job.state not in ACTIVE:
        report = Path(job.report_path) if job.report_path else None
        chars = job.report_chars
        if chars is None:
            chars = report.stat().st_size if report and report.is_file() else 0
        info.update(
            report_path=job.report_path,
            report_chars=chars if report and report.is_file() else 0,
            stray_changes=job.stray_changes,
        )
        if job.report_truncated:
            info["report_truncated"] = (
                f"REPORT.md was over {jobs.REPORT_MAX_BYTES} bytes; only the first "
                f"{jobs.REPORT_MAX_BYTES} were kept.")
    return info


WAIT_UNTIL = ("any", "all")


def _brief(store: JobStore, job: Job) -> dict:
    end = job.finished_at or time.time()
    info = {"job_id": job.id, "state": job.state,
            "elapsed_seconds": round(end - (job.started_at or job.created_at), 1)}
    if job.state == "running":
        activity = _activity(store, job)
        info.update(recent=activity["recent"][-3:], files_touched=activity.get("files_touched"))
    return info


def _reload(store: JobStore, job: Job) -> Job:
    try:
        return store.refresh(store.load(job.id))
    except JobNotFound:
        return replace(job, state="deleted")


def build_server(
    store: JobStore | None = None,
    projects_dir: Path | None = None,
    usage_check: Callable[[], dict] = agy_usage,
    usage_ttl: float = USAGE_TTL_SECONDS,
) -> MCPServer:
    store = store or JobStore()
    server = MCPServer(name="polyphony", instructions=INSTRUCTIONS)
    usage_cache = UsageCache(store.root, check=usage_check, ttl=usage_ttl)

    def project_for(root: Path) -> ProjectConfig:
        return (find_project(root, projects_dir, home=store.root)
                or ProjectConfig(name=root.name, path=root))

    def quota(model: str) -> dict:
        report = usage_cache.report()
        if not report.get("ok"):
            return {"quota_unknown": report.get("error")}
        reason = gate(report, model)
        if reason:
            raise ValueError(f"{reason} Name another model (such as {DEFAULT_MODELS['code']}), "
                             "or wait for the reset.")
        return {}

    @server.tool()
    def delegate(
        instruction: str = "",
        *,
        repo: str,
        mode: str = "code",
        timeout_minutes: int = 30,
        check: str | None = None,
        brief_path: str | None = None,
        model: str | None = None,
    ) -> dict:
        """Start an agy task in a private copy of repo (a directory inside a git
        repository); returns a job_id at once. Nothing reaches the repository
        until apply. Follow up with status or wait.

        instruction, brief_path: the task; give either or both. brief_path is
        a UTF-8 file of at most 100 KB (a relative path is from repo as given),
        read at once and appended after instruction and a blank line; use it
        for long briefs. Together they must stay under 120 KB. The result's
        instruction_chars and instruction_tail show the task arrived whole.
        mode: "code" (the agent edits files) or "report" (an audit; the agent
        writes findings to REPORT.md, read with report).
        check: shell command run in the copy once the agent succeeds, code mode
        only; overrides the repository's configured one; "" skips it.
        model: agy model id (gemini-4-argon-high, gemini-3.8-flash-low, ...);
        default is the repository's model for the mode. Refused when its quota
        is at 5% or less; the result carries quota_unknown when quota could
        not be read.
        timeout_minutes: default 30, at most 1440.

        Also refused when agy is not installed or the repository's limit of
        active jobs is reached."""
        with _anticipated():
            _check_args(mode, timeout_minutes, check)
            model = _model(model)
            root = _toplevel(repo)
            brief = _checked_brief(instruction, brief_path, repo, mode)
            project = project_for(root)
            model = model or project.models[mode]
            jobs.gc(store, jobs.AUTO_GC_SECONDS)
            unknown = quota(model)
            with store.lock():
                _check_ready(store, project)
                job = jobs.create_job(
                    store,
                    project=project,
                    instruction=instruction,
                    mode=mode,
                    model=model,
                    timeout_seconds=timeout_minutes * 60,
                    check=project.check if check is None else (check.strip() or None),
                    check_timeout_seconds=project.check_timeout_minutes * 60,
                    brief=brief,
                )
                jobs.launch(store, job)
            return {**_summary(store, store.refresh(store.load(job.id))), **unknown}

    @server.tool()
    def revise(job_id: str, feedback: str, timeout_minutes: int | None = None) -> dict:
        """Run a finished job's agent again in the same copy, on top of its
        changes, with feedback on what to fix. The agent gets the original
        instruction plus all feedback so far; the check runs again; diff and
        apply then cover every attempt together. timeout_minutes (at most
        1440) overrides the job's. Refused once any of the job has been
        applied, when the task with all feedback would pass 120 KB, or when
        the model's quota is at 5% or less. Follow up with status."""
        with _anticipated():
            if timeout_minutes is not None:
                _check_timeout(timeout_minutes)
            job = store.load(job_id)
            unknown = quota(job.model) if job.model else {}
            with store.lock():
                _check_ready(store, project_for(Path(job.repo)))
                job = jobs.revise(
                    store, job_id, feedback,
                    timeout_seconds=timeout_minutes * 60 if timeout_minutes else None,
                )
                jobs.launch(store, job)
            return {**_summary(store, store.refresh(store.load(job.id))), **unknown}

    @server.tool()
    def status(job_id: str, wait_seconds: int = 0) -> dict:
        """A job's state and latest agent events ("recent"); while running, the
        files touched so far; once finished, agy's final response, files
        changed and whether the check passed. wait_seconds (at most 100)
        blocks until the job finishes or time runs out, cheaper than polling.
        For more than one job, use wait."""
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
        paths limits it to those changed files; a later call without paths
        applies the rest. Files with unstaged edits are applied to the working
        tree and left unstaged. Refuses, changing nothing, if the changes
        don't apply cleanly to the repository as it is now or git cannot
        write it (a locked index, say; git's reason is given). The job is
        deleted once every file is applied."""
        with _anticipated():
            files, job = jobs.apply(store, job_id, paths)
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
        """Stop a queued or running job, kill its agent, and delete the job."""
        with _anticipated():
            return _summary(store, jobs.cancel(store, job_id))

    @server.tool(name="jobs")
    def list_jobs(limit: int = 20) -> dict:
        """Recent jobs, newest first; limit defaults to 20."""
        return {
            "jobs": [
                {
                    "job_id": j.id,
                    "state": store.refresh(j).state,
                    "model": j.model,
                    "mode": j.mode,
                    "project": j.project,
                    "created": datetime.fromtimestamp(j.created_at).isoformat(timespec="seconds"),
                    "instruction": j.instruction[:100],
                }
                for j in store.all()[:limit]
            ]
        }

    @server.tool()
    def usage() -> dict:
        """Quota agy has left per model group (Gemini Models, Gemini 4 Argon,
        ...): percentages and reset times. Takes several seconds; delegate
        reuses the result for a few minutes."""
        return {"usage": usage_cache.refresh()}

    @server.tool()
    def stats() -> dict:
        """How past jobs turned out per executor and model: jobs, succeeded,
        revised, applied, discarded, cancelled, check pass rate, median
        elapsed time. Counted when a job is applied, discarded or cancelled."""
        return {"executors": ledger.summarize(ledger.read(store.root))}

    @server.tool()
    def report(job_id: str, offset: int = 0, limit: int = jobs.REPORT_LIMIT) -> dict:
        """The report a finished report-mode job wrote: limit characters
        (default 20000) from offset. more is true while text stops short of
        total_chars; call again with offset + limit for the rest. Only a
        REPORT.md the job wrote or changed counts; a tracked one left as it
        was, or a symlink, fails the job with no report."""
        with _anticipated():
            return jobs.report(store, job_id, offset, limit)

    @server.tool()
    def wait(job_ids: list[str], until: str = "any", wait_seconds: int = 90) -> dict:
        """Block until any (until="any") or all (until="all") of job_ids have
        finished, or wait_seconds (default 90, at most 100) runs out: one call
        in place of status on each job. "done" says whether that happened;
        "finished" and "active" list ids by state; "jobs" gives each finished
        job in full, as status would, and each active one as job_id, state,
        elapsed_seconds and, while running, its last events and files touched.
        With "any", an already finished job counts, so pass only the ids you
        still wait on."""
        with _anticipated():
            if until not in WAIT_UNTIL:
                raise ValueError(f"until must be one of {', '.join(WAIT_UNTIL)}, not {until!r}.")
            if not job_ids:
                raise ValueError("Name at least one job.")
            repeated = sorted({i for i in job_ids if job_ids.count(i) > 1})
            if repeated:
                raise ValueError(f"Job(s) named more than once: {', '.join(repeated)}.")
            deadline = time.monotonic() + min(max(wait_seconds, 0), MAX_WAIT_SECONDS)
            listed = [store.refresh(store.load(i)) for i in job_ids]
            while True:
                listed = [_reload(store, j) for j in listed]
                finished = [j.id for j in listed if j.state not in ACTIVE]
                done = bool(finished) if until == "any" else len(finished) == len(listed)
                if done or time.monotonic() >= deadline:
                    break
                time.sleep(1)
            return {
                "done": done,
                "finished": finished,
                "active": [j.id for j in listed if j.state in ACTIVE],
                "jobs": [_summary(store, j) if j.state not in ACTIVE else _brief(store, j)
                         for j in listed],
            }

    @server.tool()
    def apply_many(
        job_ids: list[str], dry_run: bool = False, paths: dict[str, list[str]] | None = None,
    ) -> dict:
        """Stage several succeeded jobs in one repository, in the order given,
        without committing: all of them or, if any would not apply, none.
        Each patch is first checked on top of the earlier ones, so conflicts
        between jobs are found before anything changes; "error" names the job
        that did not apply and why. With "applied" empty nothing changed; if
        the repository changed while the jobs landed, the ones in "applied" are
        already staged. "overlaps" lists each file more than one job touched;
        "unstaged" the jobs left unstaged because they touch files with
        unstaged edits. dry_run only reports. paths maps a job id to the only
        files of that job to apply, as in apply; for a job already partly
        applied, use apply. Each job applied in full is deleted."""
        with _anticipated():
            return jobs.apply_many(store, job_ids, dry_run, paths)

    return server
