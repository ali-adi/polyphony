"""How much quota the cheaper executors have left, as each CLI reports it.

Neither CLI documents a machine-readable usage command. agy prints its
/usage and /credits slash commands in print mode, as tab-separated rows.
cursor-agent shows /usage only in its interactive UI, so it runs in a
pseudo-terminal and the rendered screen is parsed. Each CLI authenticates
its own request; Polyphony never touches their credentials.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import select
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyte

from polyphony.executors import AgyExecutor, CursorExecutor

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")


def parse_agy_usage(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) != 4:
            continue
        group, window, remaining, resets = parts
        m = _PERCENT.fullmatch(remaining)
        if not m:
            continue
        rows.append({
            "models": group,
            "window": window.removesuffix(" Remaining"),
            "remaining_percent": float(m.group(1)),
            "resets_at": resets,
        })
    return rows


def parse_agy_credits(text: str) -> int | None:
    m = re.search(r"^Remaining credits\t(\d+)\s*$", text, re.MULTILINE)
    return int(m.group(1)) if m else None


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as cwd:
        return subprocess.run(
            argv, cwd=cwd, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout,
        )


def agy_usage(binary: str | None = None, timeout: int = 60) -> dict:
    ex = AgyExecutor(binary)
    if not ex.is_available():
        return {"executor": "agy", "ok": False, "error": "agy is not installed."}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            usage_run = pool.submit(_run, [ex.binary_path, "-p=/usage", "--mode", "plan"], timeout)
            credits_run = pool.submit(_run, [ex.binary_path, "-p=/credits", "--mode", "plan"], timeout)
            usage_out, credits_out = usage_run.result(), credits_run.result()
    except subprocess.TimeoutExpired:
        return {"executor": "agy", "ok": False, "error": f"agy timed out after {timeout}s."}
    except OSError as e:
        return {"executor": "agy", "ok": False, "error": str(e)}

    limits = parse_agy_usage(usage_out.stdout)
    if not limits:
        shown = (usage_out.stdout + usage_out.stderr).strip()[:500]
        return {"executor": "agy", "ok": False, "error": f"Could not read agy's /usage output: {shown}"}
    return {
        "executor": "agy",
        "ok": True,
        "limits": limits,
        "credits": parse_agy_credits(credits_out.stdout),
    }


_ROW = re.compile(r"^(?P<indent> *)(?P<name>\S(?:.*?\S)?)\s{2,}(?P<current>\S(?:.*?\S)?)\s{2,}[█░—-]")
_HEADER = re.compile(r"Usage\s*•\s*(?P<plan>\S(?:.*?\S)?)\s{2,}Resets\s+(?P<resets>\S(?:.*?\S)?)\s*$")


def parse_cursor_usage(screen: str) -> dict | None:
    lines = screen.splitlines()
    header = next((m for m in map(_HEADER.search, lines) if m), None)
    start = next((i for i, l in enumerate(lines) if "Category" in l and "Current" in l), None)
    if header is None or start is None:
        return None

    categories: list[dict] = []
    base_indent = None
    parent = None
    for line in lines[start + 1:]:
        m = _ROW.match(line)
        if not m:
            break
        indent = len(m.group("indent"))
        if base_indent is None:
            base_indent = indent
        is_child = indent > base_indent
        if not is_child:
            parent = m.group("name")
        used = re.match(r"(\d+(?:\.\d+)?)% used", m.group("current"))
        categories.append({
            "name": m.group("name"),
            "parent": parent if is_child else None,
            "current": m.group("current"),
            "used_percent": float(used.group(1)) if used else None,
        })
    if not categories:
        return None
    return {"plan": header.group("plan"), "resets": header.group("resets"), "categories": categories}


class _ScreenTimeout(Exception):
    pass


def read_cursor_screen(argv: list[str], timeout: int = 45, cols: int = 120, rows: int = 50) -> str:
    """Open cursor-agent's /usage panel in a pseudo-terminal and return the screen.

    Raises _ScreenTimeout (carrying the last screen) if the UI never becomes
    ready or the panel never finishes loading within `timeout` seconds.
    """
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    deadline = time.monotonic() + timeout

    def text() -> str:
        return "\n".join(line.rstrip() for line in screen.display)

    def pump(until=None, seconds=None) -> bool:
        """Feed output to the emulator until `until(screen)` holds while the
        output is idle, or for `seconds`. False if the deadline passes."""
        stop = time.monotonic() + seconds if seconds is not None else deadline
        while time.monotonic() < min(stop, deadline):
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    data = b""
                if not data:
                    return until is None or until(text())
                stream.feed(data)
            elif until is not None and until(text()):
                return True
        return seconds is not None and time.monotonic() < deadline

    with tempfile.TemporaryDirectory() as cwd:
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, stdin=slave, stdout=slave, stderr=slave,
                env={**os.environ, "TERM": "xterm-256color"},
                start_new_session=True, close_fds=True,
            )
        except OSError:
            os.close(master)
            raise
        finally:
            os.close(slave)
        try:
            if not pump(until=lambda t: "shift+tab" in t):
                raise _ScreenTimeout(text())
            os.write(master, b"/usage")
            pump(seconds=1)
            os.write(master, b"\r")
            if not pump(until=lambda t: "Esc to close" in t and "Loading usage data" not in t):
                raise _ScreenTimeout(text())
            return text()
        finally:
            # Close our end first. With the real cursor-agent on macOS,
            # waiting while the master was still open never returned (no
            # stand-in process reproduced it; the smoke test guards it).
            os.close(master)
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    pass  # already exiting: macOS answers EPERM while a group is reaped
                try:
                    proc.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    continue


def cursor_usage(binary: str | None = None, timeout: int = 45) -> dict:
    ex = CursorExecutor(binary)
    if not ex.binary_path or not Path(ex.binary_path).exists():
        return {"executor": "cursor", "ok": False, "error": "cursor-agent is not installed."}
    argv = [ex.binary_path]
    if ex._uses_agent_subcommand():
        argv.append("agent")
    argv += ["--mode", "plan", "--trust"]
    try:
        screen = read_cursor_screen(argv, timeout=timeout)
    except _ScreenTimeout as e:
        return {
            "executor": "cursor",
            "ok": False,
            "error": f"cursor-agent's /usage panel timed out after {timeout}s.",
            "screen": str(e)[-2000:],
        }
    except OSError as e:
        return {"executor": "cursor", "ok": False, "error": str(e)}
    parsed = parse_cursor_usage(screen)
    if parsed is None:
        return {
            "executor": "cursor",
            "ok": False,
            "error": "Could not read cursor-agent's /usage panel.",
            "screen": screen[-2000:],
        }
    return {"executor": "cursor", "ok": True, **parsed}


USAGE_CHECKS = {"agy": agy_usage, "cursor": cursor_usage}


def check_usage(names: list[str] | None = None) -> list[dict]:
    """Run the named checks at once (all by default), in the order given."""
    checks = USAGE_CHECKS
    names = list(names) if names else list(checks)
    unknown = [n for n in names if n not in checks]
    if unknown:
        raise ValueError(
            f"No usage check for {', '.join(unknown)}; available: {', '.join(checks)}."
        )
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        return list(pool.map(lambda n: checks[n](), names))


def _agy_out(report: dict) -> str | None:
    """agy is out only when every model group has a window at 0%: which
    group a job's model draws on isn't known here, so any group left means
    it may still run. A group frees up when all its empty windows reset."""
    empty: dict[str, list[str]] = {}
    for row in report["limits"]:
        empty.setdefault(row["models"], [])
        if row["remaining_percent"] <= 0:
            empty[row["models"]].append(row["resets_at"])
    if not empty or not all(empty.values()):
        return None
    return f"out of quota in every model group; resets {min(max(r) for r in empty.values())}"


def _cursor_out(report: dict) -> str | None:
    """cursor is out when every top-level category is used up or disabled,
    so enabled on-demand usage (shown as an amount, not a percent) keeps it in."""
    top = [c for c in report["categories"] if c["parent"] is None]
    used_up = [c for c in top if c["used_percent"] is not None and c["used_percent"] >= 100]
    if not used_up or any(c not in used_up and c["current"] != "Disabled" for c in top):
        return None
    return f"{report['plan']} plan usage is used up and on-demand is off; resets {report['resets']}"


_OUT = {"agy": _agy_out, "cursor": _cursor_out}


def out_of_quota(report: dict | None) -> str | None:
    """Why this report says its executor can't run now, with the reset time.
    None when the report is missing, failed, or not understood: a broken
    check must never stop delegation."""
    if not report or not report.get("ok") or report.get("executor") not in _OUT:
        return None
    return _OUT[report["executor"]](report)


USAGE_TTL_SECONDS = 300


class UsageCache:
    """Usage reports kept in <home>/usage-cache.json, shared by every server
    using that home. A check takes seconds (cursor-agent runs in a
    pseudo-terminal), too slow to repeat on every delegate."""

    def __init__(
        self,
        root: Path,
        check: Callable[[list[str] | None], list[dict]] = check_usage,
        ttl: float = USAGE_TTL_SECONDS,
    ):
        self.file = Path(root) / "usage-cache.json"
        self.check = check
        self.ttl = ttl

    def _read(self) -> dict:
        try:
            data = json.loads(self.file.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def cached(self, name: str) -> dict | None:
        """The last stored {"checked_at", "report"} for name, however old. Never checks."""
        return self._read().get(name)

    def refresh(self, names: list[str] | None = None) -> list[dict]:
        """Check now and store the results, failures included, so a broken
        check costs its timeout once per TTL rather than on every delegate."""
        reports = self.check(names)
        data = self._read()  # re-read: another server may have stored other executors meanwhile
        now = time.time()
        for r in reports:
            data[r["executor"]] = {"checked_at": now, "report": r}
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_name(f"{self.file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, self.file)
        return reports

    def report(self, name: str) -> dict | None:
        """name's latest report, checking again if the stored one is older
        than the TTL. None when name has no usage check."""
        entry = self.cached(name)
        if entry and time.time() - entry["checked_at"] < self.ttl:
            return entry["report"]
        try:
            return self.refresh([name])[0]
        except ValueError:
            return None


def format_usage(results: list[dict]) -> str:
    lines = []
    for r in results:
        name = r["executor"]
        if not r["ok"]:
            lines.append(f"{name:<7} ERROR  {r['error']}")
            continue
        if name == "agy":
            for row in r["limits"]:
                lines.append(
                    f"{name:<7} {row['models']:<24} {row['window']:<16} "
                    f"{row['remaining_percent']:>5.0f}% left   resets {row['resets_at']}"
                )
            if r.get("credits") is not None:
                lines.append(f"{name:<7} credits: {r['credits']}")
        elif name == "cursor":
            lines.append(f"{name:<7} {r['plan']} plan, resets {r['resets']}")
            for c in r["categories"]:
                label = ("  " + c["name"]) if c["parent"] else c["name"]
                lines.append(f"{'':<7} {label:<16} {c['current']}")
    return "\n".join(lines)
