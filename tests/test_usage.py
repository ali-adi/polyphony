import time

import pytest

from polyphony import agy
from polyphony.usage import UsageCache, agy_usage, gate, parse_agy_usage, quota_group

AGY_USAGE = (
    "Gemini Models\tWeekly Limit Remaining\t89%\t2026-10-01T02:17:05Z\n"
    "Gemini Models\tFive Hour Limit Remaining\t98%\t2026-09-26T14:00:59Z\n"
    "Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-10-03T10:41:07Z\n"
    "Gemini 4 Argon\tGemini 4 Argon Weekly Limit Remaining\t1%\t2026-10-28T11:41:53Z\n"
)


def _report(argon=1.0, flash=89.0):
    return {"ok": True, "limits": [
        {"models": "Gemini Models", "window": "Weekly Limit", "remaining_percent": flash,
         "resets_at": "2026-10-01T02:17:05Z"},
        {"models": "Gemini 4 Argon", "window": "Gemini 4 Argon Weekly Limit",
         "remaining_percent": argon, "resets_at": "2026-10-28T11:41:53Z"},
    ]}


def test_parse_agy_usage():
    rows = parse_agy_usage(AGY_USAGE + "some other line\n")
    assert len(rows) == 4
    assert rows[0] == {
        "models": "Gemini Models",
        "window": "Weekly Limit",
        "remaining_percent": 89.0,
        "resets_at": "2026-10-01T02:17:05Z",
    }
    assert rows[3]["window"] == "Gemini 4 Argon Weekly Limit"


def test_agy_usage_reads_the_usage_command(fake_agy, tmp_path):
    usage_file = tmp_path / "usage.txt"
    usage_file.write_text(AGY_USAGE)
    fake_agy(f'[ "$1" = -p=/usage ] && cat {usage_file}')
    result = agy_usage()
    assert result["ok"] is True, result
    assert len(result["limits"]) == 4


def test_agy_usage_reports_unreadable_output(fake_agy):
    fake_agy("echo 'something changed'")
    result = agy_usage()
    assert result["ok"] is False
    assert "something changed" in result["error"]


def test_agy_usage_when_not_installed(monkeypatch):
    monkeypatch.setattr(agy, "binary", lambda: None)
    assert agy_usage() == {"ok": False, "error": "agy is not installed."}


@pytest.mark.parametrize("model, group", [
    ("gemini-4-argon-high", "Gemini 4 Argon"),
    ("gemini-3.8-flash-low", "Gemini Models"),
    ("claude-sonnet-5-5-low", "Claude and GPT models"),
])
def test_each_model_draws_on_its_group(model, group):
    assert quota_group(model) == group


def test_the_gate_refuses_only_the_model_whose_group_is_low():
    reason = gate(_report(argon=1.0), "gemini-4-argon-high")
    assert "gemini-4-argon-high" in reason and "1% left" in reason
    assert "2026-10-28T11:41:53Z" in reason
    assert gate(_report(argon=1.0), "gemini-3.8-flash-low") is None


@pytest.mark.parametrize("left, refused", [(5.0, True), (5.5, False), (0.0, True)])
def test_the_gate_holds_at_five_percent(left, refused):
    assert (gate(_report(flash=left), "gemini-3.8-flash-low") is not None) == refused


def test_cache_reuses_a_fresh_report_across_instances(tmp_path):
    calls = []

    def check():
        calls.append(1)
        return _report()

    assert UsageCache(tmp_path, check=check).report() == _report()
    assert UsageCache(tmp_path, check=check).report() == _report()
    assert len(calls) == 1


def test_cache_checks_again_once_the_ttl_passes(tmp_path):
    calls = []
    cache = UsageCache(tmp_path, check=lambda: calls.append(1) or _report(), ttl=0)
    cache.report()
    time.sleep(0.01)
    cache.report()
    assert len(calls) == 2


def test_cache_stores_a_failed_check_too(tmp_path):
    failed = {"ok": False, "error": "timed out"}
    UsageCache(tmp_path, check=lambda: failed).refresh()
    assert UsageCache(tmp_path, check=lambda: pytest.fail("checked again")).report() == failed


@pytest.mark.parametrize("content", ["{not json", '{"cursor": {}}', "[]"])
def test_cache_survives_a_corrupt_or_old_file(tmp_path, content):
    (tmp_path / "usage-cache.json").write_text(content)
    assert UsageCache(tmp_path, check=_report).report() == _report()
