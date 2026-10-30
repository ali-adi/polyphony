from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

POLL_SECONDS = 1
# 2026-10-30: two report jobs printed agy's final message, then ran on until cancelled.
DONE_GRACE_SECONDS = 10
STALL_SECONDS = 600
CPU_SAMPLE_SECONDS = 30
CPU_WORK_SECONDS = 1.0
TAIL_BYTES = 64 * 1024


@dataclass
class Result:
    success: bool
    error: str | None = None
    exit_code: int = 0


def binary() -> str | None:
    found = shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")
    return found if Path(found).exists() else None


def argv(exe: str, prompt: str, cwd: str, model: str | None) -> list[str]:
    return [exe, f"-p={prompt}", "--mode", "accept-edits", "--sandbox", "--add-dir", cwd,
            *(["--model", model] if model else []), "--output-format", "stream-json"]


def run(
    prompt: str,
    cwd: str,
    model: str | None,
    output_path: Path,
    timeout_seconds: int = 1800,
    on_start: Callable[[int], None] | None = None,
    env: dict[str, str] | None = None,
) -> Result:
    exe = binary()
    if exe is None:
        return Result(False, "agy is not installed.", 127)
    with open(output_path, "w+b") as out, tempfile.TemporaryFile() as err:
        try:
            with subprocess.Popen(
                argv(exe, prompt, cwd, model), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True,
            ) as proc:
                try:
                    if on_start:
                        on_start(proc.pid)
                    ended = _watch(proc, Path(output_path), timeout_seconds)
                finally:
                    _kill_group(proc.pid)
        except (OSError, subprocess.SubprocessError) as e:
            return Result(False, str(e), 1)
        err.seek(0)
        stderr = err.read().decode(errors="replace").strip()

    final = result_event(output_path)
    if ended == "timeout":
        return Result(False, f"agy timed out after {timeout_seconds}s.", 124)
    if ended == "stalled":
        return Result(False, f"Stalled: no output and no CPU use for {STALL_SECONDS}s; "
                             "agy was stopped and its partial work kept.", 124)
    if final is not None and final.get("status") != "SUCCESS":
        reason = final.get("finished_reason") or final.get("status")
        return Result(False, f"agy ended the turn with {reason}. {stderr}".strip(),
                      proc.returncode or 1)
    if ended is None and proc.returncode != 0:
        return Result(False, stderr or f"agy exited {proc.returncode}.", proc.returncode)
    return Result(True)


def _watch(proc: subprocess.Popen, output: Path, timeout_seconds: int) -> str | None:
    start = last_progress = cpu_at = time.monotonic()
    size, cpu = -1, _cpu_seconds(proc.pid)
    while True:
        try:
            proc.wait(timeout=POLL_SECONDS)
            return None
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        if now - start >= timeout_seconds:
            return "timeout"
        grown = output.stat().st_size
        if grown != size:
            size, last_progress = grown, now
            if result_event(output) is not None:
                try:
                    proc.wait(timeout=DONE_GRACE_SECONDS)
                    return None
                except subprocess.TimeoutExpired:
                    return "done"
        if now - cpu_at >= CPU_SAMPLE_SECONDS:
            sample = _cpu_seconds(proc.pid)
            if sample - cpu >= CPU_WORK_SECONDS:
                last_progress = now
            cpu, cpu_at = sample, now
        if now - last_progress >= STALL_SECONDS:
            return "stalled"


def _cpu_seconds(pgid: int) -> float:
    res = subprocess.run(["ps", "-A", "-o", "pgid=,time="], capture_output=True, text=True)
    total = 0.0
    for line in res.stdout.splitlines():
        group, _, used = line.strip().partition(" ")
        if group == str(pgid):
            total += _clock(used.strip())
    return total


def _clock(text: str) -> float:
    days, _, rest = text.rpartition("-")
    seconds = 0.0
    for part in rest.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds + int(days or 0) * 86400


def events(path: Path) -> list[dict | str]:
    try:
        with open(path, "rb") as f:
            f.seek(max(0, f.seek(0, os.SEEK_END) - TAIL_BYTES))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    if len(lines) > 1 and os.path.getsize(path) > TAIL_BYTES:
        lines = lines[1:]
    parsed: list[dict | str] = []
    for line in filter(str.strip, lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parsed.append(line)
            continue
        parsed.append(event if isinstance(event, dict) else line)
    return parsed


def result_event(path: Path) -> dict | None:
    for event in reversed(events(path)):
        if isinstance(event, dict) and event.get("event") == "result":
            return event.get("result") or {}
    return None


def describe(event: dict | str) -> str:
    if isinstance(event, str):
        return event[:300]
    step = event.get("step_update") or {}
    if not step:
        return str(event.get("event"))
    params = (step.get("tool_info") or {}).get("parameters") or {}
    path = next((v for k, v in params.items() if "path" in k.lower() or "file" in k.lower()), None)
    parts = [step.get("state"), step.get("step_type"), step.get("tool_name"),
             Path(path).name if isinstance(path, str) else None]
    return " ".join(str(p) for p in parts if p)


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass  # already gone, or (macOS) still being reaped
