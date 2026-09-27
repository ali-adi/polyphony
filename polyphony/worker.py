"""The detached process that runs one delegated job.

Started as `python -m polyphony.worker <job_dir>` by polyphony.jobs.launch.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from polyphony.executors import EXECUTORS, BaseExecutor, Mode
from polyphony.jobs import (
    REPORT, REPORT_FILE, JobStore, claim, collect_report, executor_mode, prompt, run_check,
    scrub_env, snapshot,
)


def run(
    job_dir: Path,
    executors: dict[str, type[BaseExecutor]] = EXECUTORS,
    attempt: int | None = None,
) -> None:
    """Run the job's `attempt`. None means its current one (tests, or a launch from
    before attempts were passed)."""
    job_dir = Path(job_dir)
    store = JobStore(job_dir.parent.parent)
    if attempt is None:
        attempt = store.load(job_dir.name).attempt
    job = claim(store, job_dir.name, attempt)
    if job is None:
        return  # cancelled before it started, or revised and owned by a newer worker

    def started(pgid: int) -> None:
        job.executor_pgid = pgid
        store.save(job)

    output = store.output_path(job.id)
    try:
        result = executors[job.executor]().execute(
            prompt(job), job.workdir, executor_mode(job.mode), job.model, job.timeout_seconds,
            output_path=output, on_start=started,
            env=scrub_env(os.environ, job.env_scrub) if job.env_scrub else None,
        )
        # Its group is gone; a recorded id could be reused by the OS and hit by cancel.
        job.executor_pgid = None
        store.save(job)
        if result.error:
            with output.open("a") as f:
                f.write(f"\n\n--- error ---\n{result.error}")
        snapshot(job)
        job.exit_code = result.exit_code
        job.error = result.error
        if result.success and job.mode == Mode.CODE and job.check_command:
            run_check(store, job)
        job.state = "succeeded" if result.success else "failed"
        if job.mode == REPORT:
            collect_report(store, job)
            if result.success and job.report_path is None:
                job.state = "failed"
                job.error = (
                    f"The executor finished but wrote no {REPORT_FILE} at the repository "
                    f"root, so there is no report. Its output is in {output}."
                )
    except Exception as e:
        # A Polyphony bug, not an executor failure. Record it so status shows
        # it, then re-raise so the traceback reaches worker.log.
        job.state = "failed"
        job.error = f"Polyphony worker error: {type(e).__name__}: {e}"
        with output.open("a") as f:
            f.write("\n--- worker traceback ---\n" + traceback.format_exc())
        raise
    finally:
        job.finished_at = time.time()
        store.save(job)


def main(argv: list[str]) -> None:
    # Double-fork: the parent that launch() waits on exits at once, so this
    # worker is reparented to init and can never be a zombie of the server.
    if os.fork() > 0:
        os._exit(0)
    run(Path(argv[1]), attempt=int(argv[2]) if len(argv) > 2 else None)


if __name__ == "__main__":
    main(sys.argv)
