"""Reading remaining quota from agy's and cursor-agent's own reports."""

import time

import pytest

from polyphony import usage
from polyphony.usage import (
    agy_usage,
    check_usage,
    cursor_usage,
    parse_agy_credits,
    parse_agy_usage,
    parse_cursor_usage,
)

AGY_USAGE = (
    "Gemini Models\tWeekly Limit Remaining\t89%\t2026-10-01T02:17:05Z\n"
    "Gemini Models\tFive Hour Limit Remaining\t98%\t2026-09-26T14:00:59Z\n"
    "Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-10-03T10:41:07Z\n"
    "Claude and GPT models\tFive Hour Limit Remaining\t100%\t2026-09-26T15:41:07Z\n"
)
AGY_CREDITS = "Remaining credits\t0\nUpgrade\thttps://antigravity.google/g1-upgrade\n"

CURSOR_SCREEN = """\
  Cursor Agent
  v2026.09.26-dd393fe
  Tip: Use /plan to iterate on an implementation plan before code changes.
────────────────────────────────────────────────────────────────────────────────
 Usage • Team                                                                                           Resets Oct 21
 Monthly plan and on-demand usage
 Category        Current             Usage
 Included        40% used            ████████████████████████████████░░░░░░░░░░░░
   Auto          48% used            ██████████████████████████████████████░░░░░░
   API           1% used             █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 On-Demand       Disabled            ————————————————————————————————————————————
 On-demand usage is off
 View in dashboard: cursor.com/dashboard?tab=usage
 Esc to close
"""


def test_parse_agy_usage():
    rows = parse_agy_usage(AGY_USAGE + "some other line\n")
    assert len(rows) == 4
    assert rows[0] == {
        "models": "Gemini Models",
        "window": "Weekly Limit",
        "remaining_percent": 89.0,
        "resets_at": "2026-10-01T02:17:05Z",
    }
    assert rows[3]["window"] == "Five Hour Limit"


def test_parse_agy_credits():
    assert parse_agy_credits(AGY_CREDITS) == 0
    assert parse_agy_credits("nothing here") is None


def test_parse_cursor_usage():
    parsed = parse_cursor_usage(CURSOR_SCREEN)
    assert parsed["plan"] == "Team"
    assert parsed["resets"] == "Oct 21"
    assert parsed["categories"] == [
        {"name": "Included", "parent": None, "current": "40% used", "used_percent": 40.0},
        {"name": "Auto", "parent": "Included", "current": "48% used", "used_percent": 48.0},
        {"name": "API", "parent": "Included", "current": "1% used", "used_percent": 1.0},
        {"name": "On-Demand", "parent": None, "current": "Disabled", "used_percent": None},
    ]


def test_parse_cursor_usage_without_the_panel():
    assert parse_cursor_usage("  Cursor Agent\n  Loading usage data...\n") is None


def test_agy_usage_reads_both_commands(fake_agy, tmp_path):
    usage_file = tmp_path / "usage.txt"
    usage_file.write_text(AGY_USAGE)
    credits_file = tmp_path / "credits.txt"
    credits_file.write_text(AGY_CREDITS)
    fake_agy(
        'case "$1" in\n'
        f"  -p=/usage) cat {usage_file} ;;\n"
        f"  -p=/credits) cat {credits_file} ;;\n"
        "esac"
    )
    result = agy_usage()
    assert result["ok"] is True, result
    assert len(result["limits"]) == 4
    assert result["credits"] == 0


def test_agy_usage_reports_unreadable_output(fake_agy):
    fake_agy("echo 'something changed'")
    result = agy_usage()
    assert result["ok"] is False
    assert "something changed" in result["error"]


def test_agy_usage_when_not_installed(tmp_path):
    result = agy_usage(binary=str(tmp_path / "missing"))
    assert result == {"executor": "agy", "ok": False, "error": "agy is not installed."}


@pytest.fixture
def fake_cursor(tmp_path):
    """A stand-in cursor-agent that behaves like the real TUI, just simpler."""
    def make(panel=True, ready=True):
        script = tmp_path / "cursor-agent"
        body = ["#!/bin/sh"]
        if ready:
            body.append("echo 'Plan (shift+tab to cycle)'")
        body.append("read line")
        if panel:
            screen = tmp_path / "screen.txt"
            screen.write_text(CURSOR_SCREEN)
            body.append(f'[ "$line" = "/usage" ] && cat {screen}')
        body.append("sleep 30")
        script.write_text("\n".join(body) + "\n")
        script.chmod(0o755)
        return str(script)
    return make


def test_cursor_usage_drives_the_interactive_panel(fake_cursor):
    result = cursor_usage(binary=fake_cursor(), timeout=20)
    assert result["ok"] is True, result
    assert result["plan"] == "Team"
    assert result["categories"][0]["used_percent"] == 40.0


def test_cursor_usage_times_out_cleanly(fake_cursor):
    start = time.monotonic()
    result = cursor_usage(binary=fake_cursor(ready=False), timeout=3)
    assert result["ok"] is False
    assert "timed out" in result["error"]
    assert time.monotonic() - start < 10


def test_cursor_usage_reports_a_missing_panel(fake_cursor):
    result = cursor_usage(binary=fake_cursor(panel=False), timeout=4)
    assert result["ok"] is False
    assert "screen" in result


def test_cursor_usage_when_not_installed(tmp_path):
    result = cursor_usage(binary=str(tmp_path / "missing"))
    assert result == {"executor": "cursor", "ok": False, "error": "cursor-agent is not installed."}


def test_check_usage_runs_the_named_checks(monkeypatch):
    monkeypatch.setattr(usage, "USAGE_CHECKS", {
        "agy": lambda: {"executor": "agy", "ok": True},
        "cursor": lambda: {"executor": "cursor", "ok": False, "error": "x"},
    })
    assert [r["executor"] for r in check_usage()] == ["agy", "cursor"]
    assert [r["executor"] for r in check_usage(["cursor"])] == ["cursor"]
    with pytest.raises(ValueError, match="gpt"):
        check_usage(["gpt"])



def test_cursor_usage_reports_a_binary_that_cannot_start(tmp_path):
    script = tmp_path / "cursor-agent"
    script.write_text("not executable\n")
    script.chmod(0o644)
    before = len(__import__("os").listdir("/dev/fd"))
    result = cursor_usage(binary=str(script), timeout=5)
    assert result["ok"] is False
    assert len(__import__("os").listdir("/dev/fd")) == before


# --- Reading "out of quota" from a report, and caching reports on disk. ---


def _agy_report(*rows):
    return {"executor": "agy", "ok": True, "credits": 0, "limits": [
        {"models": m, "window": w, "remaining_percent": p, "resets_at": r} for m, w, p, r in rows
    ]}


def _cursor_report(included, on_demand="Disabled"):
    return {"executor": "cursor", "ok": True, "plan": "Team", "resets": "Oct 21", "categories": [
        {"name": "Included", "parent": None, "current": f"{included}% used",
         "used_percent": float(included)},
        {"name": "Auto", "parent": "Included", "current": "100% used", "used_percent": 100.0},
        {"name": "On-Demand", "parent": None, "current": on_demand, "used_percent": None},
    ]}


def test_agy_is_out_of_quota_only_when_every_model_group_is():
    gemini_out = ("Gemini Models", "Weekly Limit", 0.0, "2026-10-01T02:17:05Z")
    gemini_5h_out = ("Gemini Models", "Five Hour Limit", 0.0, "2026-10-02T00:00:00Z")
    claude_ok = ("Claude and GPT models", "Weekly Limit", 40.0, "2026-10-03T10:41:07Z")
    claude_out = ("Claude and GPT models", "Five Hour Limit", 0.0, "2026-09-26T15:41:07Z")
    assert usage.out_of_quota(_agy_report(gemini_out, claude_ok)) is None
    reason = usage.out_of_quota(_agy_report(gemini_out, gemini_5h_out, claude_ok, claude_out))
    # Claude's group frees up first; Gemini's needs both of its windows to reset.
    assert "2026-09-26T15:41:07Z" in reason


def test_cursor_is_out_of_quota_when_included_is_used_up_and_on_demand_is_off():
    assert usage.out_of_quota(_cursor_report(40)) is None
    assert "Oct 21" in usage.out_of_quota(_cursor_report(100))
    assert usage.out_of_quota(_cursor_report(100, on_demand="$3 / $50")) is None


def test_a_failed_or_unknown_report_is_never_out_of_quota():
    assert usage.out_of_quota({"executor": "agy", "ok": False, "error": "x"}) is None
    assert usage.out_of_quota({"executor": "claude", "ok": True}) is None
    assert usage.out_of_quota(None) is None


class Checks:
    """A stand-in for check_usage that records what was asked."""

    def __init__(self, reports):
        self.reports, self.calls = reports, []

    def __call__(self, names=None):
        names = list(names or self.reports)
        self.calls.append(names)
        unknown = [n for n in names if n not in self.reports]
        if unknown:
            raise ValueError(f"No usage check for {', '.join(unknown)}")
        return [self.reports[n] for n in names]


def test_cache_reuses_a_fresh_report_across_instances(tmp_path):
    checks = Checks({"agy": {"executor": "agy", "ok": True, "limits": []}})
    first = usage.UsageCache(tmp_path, check=checks)
    assert first.report("agy")["ok"] is True
    assert usage.UsageCache(tmp_path, check=checks).report("agy")["ok"] is True
    assert checks.calls == [["agy"]]
    assert (tmp_path / "usage-cache.json").exists()


def test_cache_checks_again_once_the_ttl_passes(tmp_path):
    checks = Checks({"agy": {"executor": "agy", "ok": False, "error": "x"}})
    cache = usage.UsageCache(tmp_path, check=checks, ttl=0)
    cache.report("agy")
    cache.report("agy")
    assert checks.calls == [["agy"], ["agy"]]


def test_cache_refresh_and_cached_entries(tmp_path):
    checks = Checks({
        "agy": {"executor": "agy", "ok": True, "limits": []},
        "cursor": {"executor": "cursor", "ok": False, "error": "x"},
    })
    cache = usage.UsageCache(tmp_path, check=checks)
    assert cache.cached("agy") is None
    assert [r["executor"] for r in cache.refresh()] == ["agy", "cursor"]
    entry = cache.cached("cursor")
    assert entry["report"]["error"] == "x"
    assert entry["checked_at"] <= time.time()
    assert len(checks.calls) == 1


def test_cache_has_no_report_for_an_executor_without_a_check(tmp_path):
    cache = usage.UsageCache(tmp_path, check=Checks({}))
    assert cache.report("claude") is None


def test_cache_survives_a_corrupt_file(tmp_path):
    (tmp_path / "usage-cache.json").write_text("{not json")
    checks = Checks({"agy": {"executor": "agy", "ok": True, "limits": []}})
    assert usage.UsageCache(tmp_path, check=checks).report("agy")["ok"] is True
