"""The MCP tools, called in-process exactly as a client would call them."""

import json
import subprocess

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from polyphony.executors import AgyExecutor
from polyphony.server import INSTRUCTIONS, build_server

TOOLS = {"executors", "delegate", "status", "diff", "apply", "discard", "cancel", "jobs", "usage"}


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def server(store, tmp_path):
    return build_server(store=store, projects_dir=tmp_path / "no-projects")


def call(server, tool, **args):
    result = anyio.run(server.call_tool, tool, args)
    text = result.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def refused(server, tool, **args) -> str:
    """Call a tool that must fail with a readable, anticipated error (not a crash)."""
    with pytest.raises(ToolError) as e:
        call(server, tool, **args)
    assert e.type is ToolError, f"crashed instead of refusing: {e.value!r}"
    return str(e.value)


def finished(server, job_id):
    return call(server, "status", job_id=job_id, wait_seconds=30)


def test_tools_and_text_are_client_neutral(server):
    tools = anyio.run(server.list_tools)
    assert {t.name for t in tools} == TOOLS
    for text in [INSTRUCTIONS, *(t.description or "" for t in tools)]:
        assert "Claude Code" not in text


def test_delegate_status_diff_apply_discard(server, repo, fake_agy, store):
    fake_agy("printf \"print('hi')\\n\" > hello.py; echo wrote it")
    commits_before = _git("rev-list", "--count", "HEAD", cwd=repo)

    started = call(server, "delegate", instruction="add hello.py", repo=str(repo))
    assert started["executor"] == "agy"
    job_id = started["job_id"]
    assert _git("branch", "--list", "polyphony/*", cwd=repo) == ""
    assert len(_git("worktree", "list", cwd=repo).splitlines()) == 1

    status = finished(server, job_id)
    assert status["state"] == "succeeded", status
    assert status["files_changed"] == ["hello.py"]
    assert "wrote it" in status["output_tail"]

    assert "+print('hi')" in call(server, "diff", job_id=job_id)

    msg = call(server, "apply", job_id=job_id)
    assert "hello.py" in msg and "not committed" in msg
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "hello.py"
    assert _git("rev-list", "--count", "HEAD", cwd=repo) == commits_before

    call(server, "discard", job_id=job_id)
    assert not store.path(job_id).exists()
    assert "No job" in refused(server, "status", job_id=job_id)


def test_delegate_resolves_a_subdirectory_to_the_repo_root(server, repo, fake_agy):
    fake_agy("true")
    (repo / "pkg").mkdir()
    started = call(server, "delegate", instruction="x", repo=str(repo / "pkg"))
    assert started["repo"] == str(repo.resolve())


def test_explicit_unavailable_executor_is_refused(store, repo, tmp_path):
    class Missing(AgyExecutor):
        def is_available(self):
            return False

    srv = build_server(store=store, projects_dir=tmp_path / "none", executors={"agy": Missing})
    assert "not available" in refused(srv, "delegate", instruction="x", repo=str(repo), executor="agy")


def test_no_available_executor_is_refused(store, repo, tmp_path):
    class Missing(AgyExecutor):
        def is_available(self):
            return False

    srv = build_server(store=store, projects_dir=tmp_path / "none", executors={"agy": Missing})
    assert "No executor" in refused(srv, "delegate", instruction="x", repo=str(repo))


def test_unknown_executor_is_refused(server, repo):
    assert "gpt" in refused(server, "delegate", instruction="x", repo=str(repo), executor="gpt")


def test_bad_mode_is_refused(server, repo):
    msg = refused(server, "delegate", instruction="x", repo=str(repo), mode="yolo")
    assert "code" in msg and "review" in msg


def test_non_repository_is_refused(server, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert "git repository" in refused(server, "delegate", instruction="x", repo=str(plain))


def test_failed_job_cannot_be_applied(server, repo, fake_agy):
    fake_agy("echo half > half.txt; exit 1")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "failed"
    assert "failed" in refused(server, "apply", job_id=job_id)


def test_conflicting_apply_changes_nothing(server, repo, fake_agy):
    fake_agy("echo 'x = 2' > app.py")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"
    (repo / "app.py").write_text("x = 3\n")
    _git("commit", "-q", "-am", "meanwhile", cwd=repo)

    assert "does not apply" in refused(server, "apply", job_id=job_id)
    assert _git("status", "--porcelain", cwd=repo) == ""
    assert (repo / "app.py").read_text() == "x = 3\n"


def test_apply_over_uncommitted_edits_keeps_them(server, repo, fake_agy):
    fake_agy("echo 'x = 2' > app.py")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"
    (repo / "app.py").write_text("x = 99\n")

    refused(server, "apply", job_id=job_id)
    assert (repo / "app.py").read_text() == "x = 99\n"


def test_status_without_wait_returns_while_running_then_cancel(server, repo, fake_agy, store, wait_for):
    fake_agy("sleep 30")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    wait_for(store, job_id, {"running"})
    assert call(server, "status", job_id=job_id)["state"] == "running"
    assert "cancel" in refused(server, "discard", job_id=job_id)
    assert call(server, "cancel", job_id=job_id)["state"] == "cancelled"
    call(server, "discard", job_id=job_id)


def test_jobs_lists_recent_jobs(server, repo, fake_agy):
    fake_agy("true")
    job_id = call(server, "delegate", instruction="list me", repo=str(repo))["job_id"]
    listed = call(server, "jobs")["jobs"]
    assert listed[0]["job_id"] == job_id
    assert listed[0]["instruction"] == "list me"


def test_executors_reports_availability_in_pool_order(server):
    names = [e["name"] for e in call(server, "executors")["executors"]]
    assert names == ["agy", "cursor", "claude"]


def test_usage_tool(server, monkeypatch):
    from polyphony import usage
    monkeypatch.setattr(usage, "USAGE_CHECKS", {"agy": lambda: {"executor": "agy", "ok": True}})
    assert call(server, "usage")["usage"] == [{"executor": "agy", "ok": True}]
    assert "gpt" in refused(server, "usage", executor="gpt")
