"""The outcome ledger: one JSON line per job that was applied, discarded, or cancelled.

It lives at ~/.polyphony/ledger.jsonl, beside jobs/ rather than in it, so a
job's outcome outlives discard. That record is what the pool order should
eventually be judged on: which executor's work actually got applied.

A job normally gets one line. The exception is a cancelled job that is then
revised: its later outcome is appended too, and only a job's last line counts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyphony.jobs import Job

OUTCOMES = ("applied", "discarded", "cancelled")


def path(root: Path) -> Path:
    return Path(root) / "ledger.jsonl"


def record(root: Path, job: Job, outcome: str, via: str | None = None) -> None:
    """Append one outcome. A single short write in append mode, so concurrent
    servers don't interleave their lines. `via` names what recorded it when
    that was not the caller's own tool, such as "gc"."""
    end = job.finished_at or time.time()
    entry = {
        "job_id": job.id,
        "project": job.project,
        "executor": job.executor,
        "model": job.model,
        "mode": job.mode,
        "state": job.state,
        "outcome": outcome,
        "elapsed_seconds": round(end - (job.started_at or job.created_at), 1),
        "files_changed": len(job.files_changed),
        "files_applied": len(job.applied_paths),
        "attempts": job.attempt,
        "check_passed": job.check_passed,
        "created_at": job.created_at,
        "recorded_at": time.time(),
    }
    if via:
        entry["via"] = via
    f = path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as out:
        out.write(json.dumps(entry) + "\n")


def read(root: Path) -> list[dict]:
    """Each job's last recorded outcome, oldest first. A torn line from a
    crash mid-write is skipped rather than making the whole ledger unreadable."""
    f = path(root)
    if not f.exists():
        return []
    latest: dict[str, dict] = {}
    for line in f.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        latest.pop(entry.get("job_id"), None)  # re-insert, so order follows the last line
        latest[entry.get("job_id")] = entry
    return list(latest.values())


def _stats(entries: list[dict]) -> dict:
    checked = [e["check_passed"] for e in entries if e.get("check_passed") is not None]
    elapsed = [e["elapsed_seconds"] for e in entries if e.get("elapsed_seconds") is not None]
    return {
        "jobs": len(entries),
        "succeeded": sum(e.get("state") == "succeeded" for e in entries),
        "revised": sum(e.get("attempts", 1) > 1 for e in entries),
        **{o: sum(e.get("outcome") == o for e in entries) for o in OUTCOMES},
        "checks": len(checked),
        "check_pass_rate": round(sum(checked) / len(checked), 3) if checked else None,
        "median_elapsed_seconds": median(elapsed) if elapsed else None,
    }


def summarize(entries: list[dict]) -> list[dict]:
    """Per executor, then per model within it, in order of first appearance."""
    by_executor: dict[str, list[dict]] = {}
    for e in entries:
        by_executor.setdefault(e.get("executor"), []).append(e)
    summary = []
    for executor, group in by_executor.items():
        by_model: dict[str | None, list[dict]] = {}
        for e in group:
            by_model.setdefault(e.get("model"), []).append(e)
        summary.append({
            "executor": executor,
            **_stats(group),
            "models": [{"model": m, **_stats(g)} for m, g in by_model.items()],
        })
    return summary


def format_summary(summary: list[dict]) -> str:
    if not summary:
        return "No outcomes recorded."

    def line(label: str, s: dict) -> str:
        rate = "-" if s["check_pass_rate"] is None else f"{s['check_pass_rate']:.0%}"
        med = "-" if s["median_elapsed_seconds"] is None else f"{s['median_elapsed_seconds']:.0f}s"
        return (f"{label:<24} {s['jobs']} jobs, {s['succeeded']} succeeded, "
                f"{s['revised']} revised, {s['applied']} applied, {s['discarded']} discarded, "
                f"{s['cancelled']} cancelled; checks passed {rate} of {s['checks']}; "
                f"median {med}")

    lines = []
    for s in summary:
        lines.append(line(s["executor"], s))
        if len(s["models"]) > 1 or s["models"][0]["model"] is not None:
            lines += [line(f"  {m['model'] or '(default)'}", m) for m in s["models"]]
    return "\n".join(lines)
