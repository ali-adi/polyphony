from __future__ import annotations

import json
import os
import select
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# 2026-10-30: two report jobs printed agy's final message, then ran on until cancelled.
DONE_GRACE_SECONDS = 10
STALL_SECONDS = 600
CPU_SAMPLE_SECONDS = 30
CPU_WORK_SECONDS = 1.0
TAIL_BYTES = 64 * 1024
MAX_TAIL_BYTES = 16 * 1024 * 1024


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

    final = result_of(events(output_path))
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
    cpu = _cpu_seconds(proc.pid)
    lines = _Lines(output)
    out_fd = os.open(output, os.O_EVTONLY)
    kq = None
    try:
        kq = select.kqueue()
        kq.control([select.kevent(out_fd, select.KQ_FILTER_VNODE,
                                  select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                                  select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND)], 0, 0)
        try:
            kq.control([select.kevent(proc.pid, select.KQ_FILTER_PROC,
                                      select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                                      select.KQ_NOTE_EXIT)], 0, 0)
        except ProcessLookupError:
            # macOS refuses the watch once the process has begun exiting
            proc.wait()
            return None
        while True:
            if proc.poll() is not None:
                return None
            now = time.monotonic()
            if now - start >= timeout_seconds:
                return "timeout"
            if lines.grew():
                last_progress = now
                if lines.result:
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
            next_due = min(start + timeout_seconds, cpu_at + CPU_SAMPLE_SECONDS,
                           last_progress + STALL_SECONDS)
            fired = kq.control(None, 8, max(0.0, next_due - time.monotonic()))
            if any(event.filter == select.KQ_FILTER_PROC for event in fired):
                proc.wait()
                return None
    finally:
        os.close(out_fd)
        if kq is not None:
            kq.close()


class _Lines:
    def __init__(self, path: Path):
        self.path, self.offset, self.partial, self.result = path, 0, b"", False

    def grew(self) -> bool:
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        if not data:
            return False
        self.offset += len(data)
        *done, self.partial = (self.partial + data).split(b"\n")
        closed = (self.partial,) if self.partial.rstrip().endswith(b"}") else ()
        self.result = self.result or any(map(_is_result, (*done, *closed)))
        return True


def _is_result(line: bytes) -> bool:
    if b'"result"' not in line:
        return False
    try:
        event = json.loads(line)
    except ValueError:
        return False
    return isinstance(event, dict) and event.get("event") == "result"


def _cpu_seconds(pgid: int) -> float:
    res = subprocess.run(["ps", "-o", "pgid=,time=", "-g", str(pgid)],
                         capture_output=True, text=True)
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
            size = f.seek(0, os.SEEK_END)
            want = TAIL_BYTES
            while True:
                f.seek(max(0, size - want))
                data = f.read()
                if want >= size or want >= MAX_TAIL_BYTES or b"\n" in data.rstrip(b"\n"):
                    break
                want *= 4
    except FileNotFoundError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    if len(lines) > 1 and size > want:
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


def result_of(stream: list[dict | str]) -> dict | None:
    for event in reversed(stream):
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
