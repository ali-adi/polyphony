"""agy.run against a fake agy: the result event ends a run, a stall is stopped, and
events read as a heartbeat. The fixture stream is a real agy run's output."""

import os
import threading
import time
from pathlib import Path

import pytest

from polyphony import agy

STREAM = Path(__file__).parent / "fixtures" / "agy-stream.ndjson"


def _gone(pid, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.1)
    return False


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(agy, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(agy, "DONE_GRACE_SECONDS", 0.5)


def _run(tmp_path, **kw):
    return agy.run("task", str(tmp_path), "gemini-3.8-flash-low", tmp_path / "out.ndjson", **kw)


def test_the_argv_runs_print_mode_with_edits_sandbox_model_and_stream(tmp_path):
    assert agy.argv("agy", "-p looks like a flag", "/w", "m") == [
        "agy", "-p=-p looks like a flag", "--mode", "accept-edits", "--sandbox",
        "--add-dir", "/w", "--model", "m", "--output-format", "stream-json"]


@pytest.mark.usefixtures("fast")
def test_the_result_event_ends_a_run_that_idles_after_it(tmp_path, fake_agy):
    fake_agy(f"cat {STREAM}; sleep 60 & echo $! > child.pid; wait")
    started = time.monotonic()
    res = _run(tmp_path)
    assert time.monotonic() - started < 10
    assert res.success and res.error is None
    assert agy.result_event(tmp_path / "out.ndjson")["response"] == "done\n"
    assert _gone(int((tmp_path / "child.pid").read_text())), "agy's children outlived it"


@pytest.mark.usefixtures("fast")
def test_a_result_that_did_not_succeed_fails_the_run(tmp_path, fake_agy):
    fake_agy("echo '{\"event\": \"result\", \"result\": {\"status\": \"ERROR\", "
             "\"finished_reason\": \"error\"}}'; echo quota >&2")
    res = _run(tmp_path)
    assert not res.success and "error" in res.error and "quota" in res.error


@pytest.mark.usefixtures("fast")
def test_a_run_with_no_output_or_cpu_is_stopped_as_stalled(tmp_path, fake_agy, monkeypatch):
    monkeypatch.setattr(agy, "STALL_SECONDS", 1)
    fake_agy("echo started; sleep 60")
    started = time.monotonic()
    res = _run(tmp_path)
    assert time.monotonic() - started < 10
    assert not res.success and res.exit_code == 124 and "Stalled" in res.error


@pytest.mark.usefixtures("fast")
def test_output_keeps_a_slow_run_from_counting_as_stalled(tmp_path, fake_agy, monkeypatch):
    monkeypatch.setattr(agy, "STALL_SECONDS", 1)
    fake_agy("for i in 1 2 3 4; do echo tick $i; sleep 0.5; done")
    assert _run(tmp_path).success


@pytest.mark.usefixtures("fast")
def test_a_timeout_kills_the_group_and_keeps_partial_output(tmp_path, fake_agy):
    fake_agy("echo waiting; sleep 60 & echo $! > child.pid; wait")
    res = _run(tmp_path, timeout_seconds=1)
    assert res.exit_code == 124 and "timed out" in res.error
    assert agy.events(tmp_path / "out.ndjson") == ["waiting"]
    assert _gone(int((tmp_path / "child.pid").read_text()))


def test_stderr_explains_a_failed_exit(tmp_path, fake_agy):
    fake_agy("echo partial; echo broke >&2; exit 3")
    res = _run(tmp_path)
    assert (res.success, res.exit_code, res.error) == (False, 3, "broke")


def test_output_is_on_disk_while_agy_runs(tmp_path, fake_agy):
    fake_agy("echo first; sleep 2; echo second")
    out = tmp_path / "out.ndjson"
    worker = threading.Thread(target=_run, args=(tmp_path,))
    worker.start()
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and "first" not in (out.read_text() if out.exists() else ""):
        time.sleep(0.05)
    assert "first" in out.read_text() and worker.is_alive()
    worker.join()


def test_on_start_gets_agys_process_group(tmp_path, fake_agy):
    fake_agy("echo $$")
    seen = []
    _run(tmp_path, on_start=seen.append)
    assert seen == [int(agy.events(tmp_path / "out.ndjson")[0])]


def test_a_missing_agy_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(agy, "binary", lambda: None)
    res = _run(tmp_path)
    assert res.exit_code == 127 and not (tmp_path / "out.ndjson").exists()


def test_the_real_stream_reads_as_a_heartbeat():
    lines = [agy.describe(e) for e in agy.events(STREAM)]
    assert "ACTIVE tool write_file hi.txt" in lines
    assert "DONE tool read_file hi.txt" in lines
    assert lines[0] == "init" and lines[-1] == "result"


def test_events_from_a_large_stream_skip_the_cut_first_line(tmp_path, monkeypatch):
    monkeypatch.setattr(agy, "TAIL_BYTES", 100)
    f = tmp_path / "out.ndjson"
    f.write_text('{"event": "init", "pad": "' + "x" * 200 + '"}\n{"event": "result", "result": {}}\n')
    assert agy.events(f) == [{"event": "result", "result": {}}]


@pytest.mark.parametrize("text, seconds", [
    ("0:01.50", 1.5), ("1:02:03", 3723.0), ("2-00:00:01", 172801.0), ("00:00:07", 7.0),
])
def test_ps_cpu_times_parse(text, seconds):
    assert agy._clock(text) == seconds
