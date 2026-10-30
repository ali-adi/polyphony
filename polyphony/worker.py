"""The detached process that runs one delegated job.

Started as `python -m polyphony.worker <job_dir>` by polyphony.jobs.launch.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from polyphony import agy
from polyphony.jobs import (
    CODE, REPORT, REPORT_FILE, JobDisowned, JobNotFound, JobStore, claim, collect_report,
    notify, prompt, report_fingerprint, run_check, save_running, scrub_env, snapshot,
)


def run(job_dir: Path, attempt: int | None = None) -> None:
    """Run the job's `attempt`. None means its current one (tests, or a launch from
    before attempts were passed).

    Every save goes through save_running, so once the job is cancelled under
    this worker it writes nothing more and stops (JobDisowned). Raised from
    on_start, that also kills the executor that just started.
    """
    job_dir = Path(job_dir)
    store = JobStore(job_dir.parent.parent)
    try:
        if attempt is None:
            attempt = store.load(job_dir.name).attempt
        job = claim(store, job_dir.name, attempt)
    except JobNotFound:
        return  # cancelled, and so deleted, before it started
    if job is None:
        return  # cancelled before it started, or revised and owned by a newer worker

    def started(pgid: int) -> None:
        job.executor_pgid = pgid
        save_running(store, job)

    output = store.output_path(job.id)
    try:
        if job.mode == REPORT:  # so a REPORT.md already there is not taken for this attempt's
            job.report_before = report_fingerprint(job)
            save_running(store, job)
        result = agy.run(
            prompt(job), job.workdir, job.model, output, job.timeout_seconds, on_start=started,
            env=scrub_env(os.environ, job.env_scrub) if job.env_scrub else None,
        )
        # Its group is gone; a recorded id could be reused by the OS and hit by cancel.
        job.executor_pgid = None
        save_running(store, job)
        if result.error:
            with output.open("a") as f:
                f.write(f"\n\n--- error ---\n{result.error}")
        snapshot(job)
        job.exit_code = result.exit_code
        job.error = result.error
        if result.success and job.mode == CODE and job.check_command:
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
    except JobDisowned:
        return  # cancelled under it: the record is the canceller's now
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
        try:
            save_running(store, job)
            notify(job)
        except JobDisowned:
            pass


def main(argv: list[str]) -> None:
    # Double-fork: the parent that launch() waits on exits at once, so this
    # worker is reparented to init and can never be a zombie of the server.
    if os.fork() > 0:
        os._exit(0)
    run(Path(argv[1]), attempt=int(argv[2]) if len(argv) > 2 else None)


if __name__ == "__main__":
    main(sys.argv)
