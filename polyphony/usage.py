"""How much quota agy has left, as its /usage slash command prints it in
print mode: tab-separated rows, one per model group and window. agy
authenticates its own request; Polyphony never touches its credentials.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from polyphony import agy

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")
QUOTA_FLOOR_PERCENT = 5
USAGE_TTL_SECONDS = 300


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


def agy_usage(timeout: int = 60) -> dict:
    exe = agy.binary()
    if exe is None:
        return {"ok": False, "error": "agy is not installed."}
    try:
        with tempfile.TemporaryDirectory() as cwd:
            out = subprocess.run(
                [exe, "-p=/usage", "--mode", "plan"], cwd=cwd, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"agy timed out after {timeout}s."}
    except OSError as e:
        return {"ok": False, "error": str(e)}
    limits = parse_agy_usage(out.stdout)
    if not limits:
        shown = (out.stdout + out.stderr).strip()[:500]
        return {"ok": False, "error": f"Could not read agy's /usage output: {shown}"}
    return {"ok": True, "limits": limits}


def quota_group(model: str) -> str:
    # ponytail: agy names groups, not models; a new family needs a line here.
    if model.startswith("gemini-4-argon"):
        return "Gemini 4 Argon"
    if model.startswith("gemini"):
        return "Gemini Models"
    return "Claude and GPT models"


def gate(report: dict, model: str) -> str | None:
    low = [row for row in report["limits"]
           if row["models"] == quota_group(model)
           and row["remaining_percent"] <= QUOTA_FLOOR_PERCENT]
    if not low:
        return None
    windows = "; ".join(f"{r['window']} {r['remaining_percent']:.0f}% left, resets {r['resets_at']}"
                        for r in low)
    return f"{model} is at or below {QUOTA_FLOOR_PERCENT}% quota ({windows})."


class UsageCache:

    def __init__(
        self,
        root: Path,
        check: Callable[[], dict] = agy_usage,
        ttl: float = USAGE_TTL_SECONDS,
    ):
        self.file = Path(root) / "usage-cache.json"
        self.check = check
        self.ttl = ttl

    def cached(self) -> dict | None:
        try:
            data = json.loads(self.file.read_text())
        except (OSError, ValueError):
            return None
        entry = data.get("agy") if isinstance(data, dict) else None
        return entry if isinstance(entry, dict) and "checked_at" in entry else None

    def refresh(self) -> dict:
        report = self.check()
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_name(f"{self.file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"agy": {"checked_at": time.time(), "report": report}}, indent=2))
        os.replace(tmp, self.file)
        return report

    def report(self) -> dict:
        entry = self.cached()
        if entry and time.time() - entry["checked_at"] < self.ttl:
            return entry["report"]
        return self.refresh()


def format_usage(report: dict) -> str:
    if not report["ok"]:
        return f"ERROR  {report['error']}"
    return "\n".join(
        f"{row['models']:<24} {row['window']:<28} {row['remaining_percent']:>5.0f}% left   "
        f"resets {row['resets_at']}"
        for row in report["limits"]
    )
