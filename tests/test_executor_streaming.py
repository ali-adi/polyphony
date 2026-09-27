"""BaseExecutor.execute: output reaches disk as it arrives, and a timeout kills everything."""

import os
import threading
import time

import pytest

from polyphony.executors import BaseExecutor
from polyphony.executors.base import Mode


class Shell(BaseExecutor):
    """Runs the instruction as a shell script."""

    name = "shell"

    def find_binary(self):
        return "/bin/sh"

    def build_argv(self, instruction, mode, cwd, model=None):
        return ["/bin/sh", "-c", instruction]


def _gone(pid, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass  # macOS answers EPERM briefly while the process is reaped
        time.sleep(0.1)
    return False


def test_output_is_on_disk_before_the_executor_exits(tmp_path):
    out = tmp_path / "output.txt"
    results = []
    t = threading.Thread(
        target=lambda: results.append(
            Shell().execute("echo first; sleep 3; echo second", str(tmp_path), Mode.CODE,
                            output_path=out)
        )
    )
    t.start()
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline and not (out.exists() and "first" in out.read_text()):
        time.sleep(0.05)
    assert "first" in out.read_text()
    assert t.is_alive(), "the executor should still be running"
    t.join()
    [res] = results
    assert res.success
    assert "first" in res.output and "second" in res.output
    assert out.read_text() == "first\nsecond\n"


def test_output_without_a_path_is_still_returned(tmp_path):
    res = Shell().execute("echo hello", str(tmp_path), Mode.CODE)
    assert res.success and res.output == "hello"


def test_stderr_stays_out_of_the_output_file_but_explains_a_failure(tmp_path):
    out = tmp_path / "output.txt"
    res = Shell().execute("echo partial; echo broke >&2; exit 3", str(tmp_path), Mode.CODE,
                          output_path=out)
    assert res.exit_code == 3 and not res.success
    assert res.output == "partial"
    assert res.error == "broke"
    assert out.read_text() == "partial\n"


def test_soft_failure_is_detected_in_stderr_too(tmp_path):
    class Picky(Shell):
        def detect_failure(self, output):
            return "quota" if "OUT_OF_QUOTA" in output else None

    res = Picky().execute("echo fine; echo OUT_OF_QUOTA >&2", str(tmp_path), Mode.CODE)
    assert res.exit_code == 0 and not res.success
    assert res.error == "quota"


def test_stdin_still_reaches_the_executor(tmp_path):
    class Piped(Shell):
        def build_argv(self, instruction, mode, cwd, model=None):
            return ["/bin/cat"]

        def stdin(self, instruction):
            return instruction

    res = Piped().execute("from stdin", str(tmp_path), Mode.CODE)
    assert res.output == "from stdin"


def test_timeout_kills_the_executors_children_too(tmp_path):
    out = tmp_path / "output.txt"
    started = time.monotonic()
    res = Shell().execute(
        "sleep 60 & echo $! > child.pid; echo waiting; wait",
        str(tmp_path), Mode.CODE, timeout_seconds=1, output_path=out,
    )
    assert time.monotonic() - started < 10
    assert res.exit_code == 124 and not res.success
    assert "timed out" in res.error
    assert res.output == "waiting", "partial output survives a timeout"
    child = int((tmp_path / "child.pid").read_text())
    assert _gone(child), "the executor's child outlived the timeout"


def test_on_start_receives_the_executors_process_group(tmp_path):
    seen = []
    res = Shell().execute("echo $$", str(tmp_path), Mode.CODE, on_start=seen.append)
    assert seen == [int(res.output)], "the executor leads its own process group"


def test_unavailable_executor_writes_nothing(tmp_path):
    class Missing(Shell):
        def find_binary(self):
            return None

    out = tmp_path / "output.txt"
    res = Missing().execute("echo hi", str(tmp_path), Mode.CODE, output_path=out)
    assert res.exit_code == 127
    assert not out.exists()


@pytest.mark.parametrize("script", ["exit 0", "exit 5"])
def test_empty_output_is_empty(tmp_path, script):
    res = Shell().execute(script, str(tmp_path), Mode.CODE, output_path=tmp_path / "o.txt")
    assert res.output == ""
