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
from polyphony.jobs import JobStore, snapshot


def run(job_dir: Path, executors: dict[str, type[BaseExecutor]] = EXECUTORS) -> None:
    job_dir = Path(job_dir)
    store = JobStore(job_dir.parent.parent)
    job = store.load(job_dir.name)
    if job.state != "queued":
        return  # cancelled before it started

    job.state = "running"
    job.pid = os.getpid()
    job.pgid = os.getpgid(0)
    job.started_at = time.time()
    store.save(job)

    output = store.output_path(job.id)
    try:
        result = executors[job.executor]().execute(
            job.instruction, job.workdir, Mode(job.mode), job.model, job.timeout_seconds
        )
        text = result.output
        if result.error:
            text += f"\n\n--- error ---\n{result.error}"
        output.write_text(text)
        snapshot(job)
        job.exit_code = result.exit_code
        job.error = result.error
        job.state = "succeeded" if result.success else "failed"
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
    run(Path(argv[1]))


if __name__ == "__main__":
    main(sys.argv)
