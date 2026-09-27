"""The MCP tools, called in-process exactly as a client would call them."""

import json
import subprocess
import time

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from polyphony.executors import AgyExecutor, Mode
from polyphony.server import INSTRUCTIONS, build_server

TOOLS = {
    "executors", "delegate", "delegate_many", "status", "diff", "apply", "discard", "cancel",
    "jobs", "usage", "stats", "revise", "report",
}


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class Checks:
    """A stand-in for check_usage, so no test ever runs a real usage check."""

    def __init__(self, reports=None):
        self.reports, self.calls = reports or {}, []

    def __call__(self, names=None):
        names = list(names or self.reports)
        self.calls.append(names)
        unknown = [n for n in names if n not in self.reports]
        if unknown:
            raise ValueError(f"No usage check for {', '.join(unknown)}.")
        return [self.reports[n] for n in names]


@pytest.fixture
def server(store, tmp_path):
    return build_server(store=store, projects_dir=tmp_path / "no-projects", usage_check=Checks())


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

    srv = build_server(store=store, projects_dir=tmp_path / "none", executors={"agy": Missing},
                       usage_check=Checks())
    assert "not available" in refused(srv, "delegate", instruction="x", repo=str(repo), executor="agy")


def test_no_available_executor_is_refused(store, repo, tmp_path):
    class Missing(AgyExecutor):
        def is_available(self):
            return False

    srv = build_server(store=store, projects_dir=tmp_path / "none", executors={"agy": Missing},
                       usage_check=Checks())
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


def test_status_shows_output_while_running(server, repo, fake_agy, store, wait_for):
    fake_agy("echo step one done; sleep 30")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    wait_for(store, job_id, {"running"})
    deadline = time.monotonic() + 10
    status = call(server, "status", job_id=job_id)
    while "step one done" not in status.get("output_tail", "") and time.monotonic() < deadline:
        time.sleep(0.1)
        status = call(server, "status", job_id=job_id)
    try:
        assert status["state"] == "running"
        assert "step one done" in status["output_tail"]
        assert status["output_path"] == str(store.output_path(job_id))
        assert "files_changed" not in status, "only a finished job has a result"
    finally:
        call(server, "cancel", job_id=job_id)


def test_status_of_a_queued_job_has_no_output_yet(server, repo, store):
    from polyphony.config import ProjectConfig
    from polyphony.jobs import create_job
    job = create_job(store, ProjectConfig(name="d", path=repo), "x", "agy", "code")
    status = call(server, "status", job_id=job.id)
    assert status["state"] == "queued"
    assert "output_tail" not in status


def test_jobs_lists_recent_jobs(server, repo, fake_agy):
    fake_agy("true")
    job_id = call(server, "delegate", instruction="list me", repo=str(repo))["job_id"]
    listed = call(server, "jobs")["jobs"]
    assert listed[0]["job_id"] == job_id
    assert listed[0]["instruction"] == "list me"


def test_executors_reports_availability_in_pool_order(store, tmp_path):
    # Stubs, because a real cursor's availability check runs the binary.
    srv = build_server(store=store, projects_dir=tmp_path / "none", executors=STUBS,
                       usage_check=Checks())
    listed = call(srv, "executors")["executors"]
    assert [e["name"] for e in listed] == ["agy", "cursor", "claude"]
    assert all(e["available"] for e in listed)


def test_usage_tool(store, tmp_path, monkeypatch):
    from polyphony import usage
    monkeypatch.setattr(usage, "USAGE_CHECKS", {"agy": lambda: {"executor": "agy", "ok": True}})
    server = build_server(store=store, projects_dir=tmp_path / "none")  # the real check_usage
    assert call(server, "usage")["usage"] == [{"executor": "agy", "ok": True}]
    assert "gpt" in refused(server, "usage", executor="gpt")


def test_status_reports_the_check(server, repo, fake_agy):
    fake_agy("echo hi > new.txt")
    job_id = call(server, "delegate", instruction="x", repo=str(repo),
                  check="echo checking; test -f new.txt")["job_id"]
    status = finished(server, job_id)
    assert status["state"] == "succeeded"
    assert status["check_command"] == "echo checking; test -f new.txt"
    assert status["check_passed"] is True and status["check_exit_code"] == 0
    assert "checking" in status["check_output_tail"]
    assert status["check_output_path"].endswith("check.txt")


def test_project_check_applies_and_delegate_overrides_it(store, repo, fake_agy, tmp_path):
    projects = tmp_path / "projects" / "demo"
    projects.mkdir(parents=True)
    (projects / "project.yaml").write_text(f"name: demo\npath: {repo}\ncheck: exit 4\n")
    srv = build_server(store=store, projects_dir=tmp_path / "projects", usage_check=Checks())
    fake_agy("true")

    from_project = call(srv, "delegate", instruction="x", repo=str(repo))["job_id"]
    status = finished(srv, from_project)
    assert status["check_command"] == "exit 4"
    assert status["check_passed"] is False and status["check_exit_code"] == 4
    assert status["state"] == "succeeded"

    overridden = call(srv, "delegate", instruction="x", repo=str(repo), check="true")["job_id"]
    assert finished(srv, overridden)["check_passed"] is True

    skipped = call(srv, "delegate", instruction="x", repo=str(repo), check="")["job_id"]
    assert "check_passed" not in finished(srv, skipped)


def test_a_check_in_review_mode_is_refused(server, repo):
    msg = refused(server, "delegate", instruction="x", repo=str(repo), mode="review",
                  check="pytest")
    assert "code" in msg


def test_stats_summarizes_recorded_outcomes(server, repo, fake_agy):
    fake_agy("echo hi > new.txt")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), check="true")["job_id"]
    finished(server, job_id)
    call(server, "apply", job_id=job_id)
    call(server, "discard", job_id=job_id)

    [agy] = call(server, "stats")["executors"]
    assert agy["executor"] == "agy"
    assert (agy["jobs"], agy["succeeded"], agy["applied"], agy["discarded"]) == (1, 1, 1, 0)
    assert agy["check_pass_rate"] == 1.0


def test_revise_runs_a_second_attempt_and_apply_takes_both(server, repo, fake_agy, store):
    fake_agy("if [ -f a.txt ]; then echo two > b.txt; echo second; else echo one > a.txt; fi")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["files_changed"] == ["a.txt"]

    revised = call(server, "revise", job_id=job_id, feedback="add b.txt too", timeout_minutes=5)
    assert revised["job_id"] == job_id
    assert revised["attempt"] == 2
    assert store.load(job_id).timeout_seconds == 300

    status = finished(server, job_id)
    assert status["state"] == "succeeded", status
    assert status["attempt"] == 2
    assert status["files_changed"] == ["a.txt", "b.txt"]
    assert "second" in status["output_tail"]

    call(server, "apply", job_id=job_id)
    assert _git("diff", "--cached", "--name-only", cwd=repo).splitlines() == ["a.txt", "b.txt"]
    assert "discard" in refused(server, "revise", job_id=job_id, feedback="more")


def test_revise_refusals(server, repo, fake_agy, store, wait_for):
    fake_agy("sleep 30")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    wait_for(store, job_id, {"running"})
    assert "running" in refused(server, "revise", job_id=job_id, feedback="more")
    call(server, "cancel", job_id=job_id)
    assert "feedback" in refused(server, "revise", job_id=job_id, feedback=" ")
    assert "positive" in refused(server, "revise", job_id=job_id, feedback="x", timeout_minutes=0)
    assert "No job" in refused(server, "revise", job_id="nope", feedback="x")


def test_revise_refuses_when_the_jobs_executor_is_gone(store, repo, tmp_path, fake_agy):
    fake_agy("true")
    srv = build_server(store=store, projects_dir=tmp_path / "none", usage_check=Checks())
    job_id = call(srv, "delegate", instruction="x", repo=str(repo))["job_id"]
    finished(srv, job_id)

    class Missing(AgyExecutor):
        def is_available(self):
            return False

    gone = build_server(store=store, projects_dir=tmp_path / "none", executors={"agy": Missing},
                        usage_check=Checks())
    assert "not available" in refused(gone, "revise", job_id=job_id, feedback="x")


# --- Choosing an executor: quota, concurrency caps, and fan-out. ---


class Always(AgyExecutor):
    def is_available(self):
        return True


POOL = {"agy": Always, "cursor": Always, "claude": Always}

AGY_OUT = {"executor": "agy", "ok": True, "credits": 0, "limits": [
    {"models": "Gemini Models", "window": "Weekly Limit", "remaining_percent": 0.0,
     "resets_at": "2026-10-01T02:17:05Z"},
]}
CURSOR_OUT = {"executor": "cursor", "ok": True, "plan": "Team", "resets": "Oct 21", "categories": [
    {"name": "Included", "parent": None, "current": "100% used", "used_percent": 100.0},
    {"name": "On-Demand", "parent": None, "current": "Disabled", "used_percent": None},
]}


@pytest.fixture
def no_launch(monkeypatch):
    """Record jobs without starting a worker, which would run the real CLI
    named by the job. A queued job holds a slot like a running one."""
    from polyphony import jobs
    monkeypatch.setattr(jobs, "launch", lambda store, job: None)


def _server(store, tmp_path, checks=None, executors=POOL, **kw):
    return build_server(store=store, projects_dir=tmp_path / "projects",
                        executors=executors, usage_check=checks or Checks(), **kw)


def _project(tmp_path, repo, **data):
    f = tmp_path / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"name": "demo", "path": str(repo), **data}))


@pytest.mark.usefixtures("no_launch")
def test_delegate_skips_an_executor_out_of_quota(store, repo, tmp_path):
    srv = _server(store, tmp_path, Checks({"agy": AGY_OUT}))
    started = call(srv, "delegate", instruction="x", repo=str(repo))
    assert started["executor"] == "cursor"
    [skip] = started["skipped"]
    assert skip["executor"] == "agy" and "2026-10-01T02:17:05Z" in skip["reason"]


@pytest.mark.usefixtures("no_launch")
def test_a_named_executor_is_never_skipped_for_quota(store, repo, tmp_path):
    checks = Checks({"agy": AGY_OUT})
    srv = _server(store, tmp_path, checks)
    started = call(srv, "delegate", instruction="x", repo=str(repo), executor="agy")
    assert started["executor"] == "agy"
    assert started["skipped"] == []
    assert checks.calls == []


@pytest.mark.usefixtures("no_launch")
def test_a_broken_usage_check_does_not_block_delegation(store, repo, tmp_path):
    srv = _server(store, tmp_path, Checks({"agy": {"executor": "agy", "ok": False, "error": "?"}}))
    started = call(srv, "delegate", instruction="x", repo=str(repo))
    assert started["executor"] == "agy" and started["skipped"] == []


@pytest.mark.usefixtures("no_launch")
def test_every_executor_out_of_quota_is_refused_with_reset_times(store, repo, tmp_path):
    srv = _server(store, tmp_path, Checks({"agy": AGY_OUT, "cursor": CURSOR_OUT}),
                  executors={"agy": Always, "cursor": Always})
    msg = refused(srv, "delegate", instruction="x", repo=str(repo))
    assert "agy" in msg and "2026-10-01T02:17:05Z" in msg
    assert "cursor" in msg and "Oct 21" in msg
    assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_usage_reports_are_cached_across_delegates_and_servers(store, repo, tmp_path):
    checks = Checks({"agy": {"executor": "agy", "ok": True, "credits": 0, "limits": []}})
    call(_server(store, tmp_path, checks), "delegate", instruction="x", repo=str(repo))
    call(_server(store, tmp_path, checks), "delegate", instruction="y", repo=str(repo))
    assert checks.calls == [["agy"]]
    assert (store.root / "usage-cache.json").exists()


@pytest.mark.usefixtures("no_launch")
def test_usage_is_checked_again_after_the_ttl(store, repo, tmp_path):
    checks = Checks({"agy": {"executor": "agy", "ok": True, "credits": 0, "limits": []}})
    srv = _server(store, tmp_path, checks, usage_ttl=0)
    call(srv, "delegate", instruction="x", repo=str(repo))
    call(srv, "delegate", instruction="y", repo=str(repo))
    assert checks.calls == [["agy"], ["agy"]]


@pytest.mark.usefixtures("no_launch")
def test_usage_tool_refreshes_the_cache_that_delegate_reads(store, repo, tmp_path):
    checks = Checks({"agy": AGY_OUT, "cursor": CURSOR_OUT})
    srv = _server(store, tmp_path, checks)
    assert [r["executor"] for r in call(srv, "usage")["usage"]] == ["agy", "cursor"]
    started = call(srv, "delegate", instruction="x", repo=str(repo))
    assert started["executor"] == "claude"
    assert checks.calls[0] == ["agy", "cursor"]
    assert all(c == ["claude"] for c in checks.calls[1:])  # claude has no check to cache


def test_executors_shows_cached_quota_without_checking(store, tmp_path):
    checks = Checks({"agy": AGY_OUT, "cursor": {"executor": "cursor", "ok": False, "error": "no"}})
    srv = _server(store, tmp_path, checks)
    before = call(srv, "executors")["executors"]
    assert all("quota" not in e for e in before)
    assert checks.calls == []

    call(srv, "usage")
    listed = {e["name"]: e for e in call(srv, "executors")["executors"]}
    assert "2026-10-01T02:17:05Z" in listed["agy"]["quota"]["out_of_quota"]
    assert listed["cursor"]["quota"]["out_of_quota"] is None
    assert listed["cursor"]["quota"]["error"] == "no"
    assert "quota" not in listed["claude"]
    assert listed["agy"]["active_jobs"] == 0 and listed["agy"]["max_parallel"] is None
    assert len(checks.calls) == 1


@pytest.mark.usefixtures("no_launch")
def test_an_executor_at_its_cap_is_skipped_when_unnamed(store, repo, tmp_path):
    _project(tmp_path, repo, max_parallel={"agy": 3})
    srv = _server(store, tmp_path)
    for _ in range(3):
        assert call(srv, "delegate", instruction="x", repo=str(repo))["executor"] == "agy"
    started = call(srv, "delegate", instruction="x", repo=str(repo))
    assert started["executor"] == "cursor"
    assert started["skipped"][0]["executor"] == "agy"
    assert "3" in started["skipped"][0]["reason"]


@pytest.mark.usefixtures("no_launch")
def test_a_named_executor_at_its_cap_is_refused(store, repo, tmp_path):
    _project(tmp_path, repo, max_parallel={"agy": 1})
    srv = _server(store, tmp_path)
    call(srv, "delegate", instruction="x", repo=str(repo), executor="agy")
    msg = refused(srv, "delegate", instruction="x", repo=str(repo), executor="agy")
    assert "1 active" in msg
    assert len(store.all()) == 1


@pytest.mark.usefixtures("no_launch")
def test_the_cap_counts_jobs_from_every_project(store, repo, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _git("init", "-q", "-b", "main", cwd=other)
    _git("-c", "user.email=t@e", "-c", "user.name=T", "commit", "-q", "--allow-empty",
         "-m", "init", cwd=other)
    _project(tmp_path, repo, max_parallel={"agy": 1})
    srv = _server(store, tmp_path)
    call(srv, "delegate", instruction="x", repo=str(other), executor="agy")
    assert "1 active" in refused(srv, "delegate", instruction="x", repo=str(repo), executor="agy")


@pytest.mark.usefixtures("no_launch")
def test_a_dead_worker_does_not_hold_a_slot(store, repo, tmp_path):
    _project(tmp_path, repo, max_parallel={"agy": 1})
    srv = _server(store, tmp_path)
    job_id = call(srv, "delegate", instruction="x", repo=str(repo), executor="agy")["job_id"]
    p = subprocess.Popen(["true"])
    p.wait()
    job = store.load(job_id)
    job.state, job.pid = "running", p.pid
    store.save(job)
    assert call(srv, "delegate", instruction="x", repo=str(repo), executor="agy")["executor"] == "agy"


@pytest.mark.usefixtures("no_launch")
def test_delegate_many_starts_one_job_per_executor(store, repo, tmp_path):
    checks = Checks({"agy": AGY_OUT})
    srv = _server(store, tmp_path, checks)
    started = call(srv, "delegate_many", instruction="same brief", repo=str(repo),
                   executors=["cursor", "agy"], mode="review")
    assert [j["executor"] for j in started["jobs"]] == ["cursor", "agy"]
    assert len({j["job_id"] for j in started["jobs"]}) == 2
    assert {store.load(j["job_id"]).instruction for j in started["jobs"]} == {"same brief"}
    assert all(j["mode"] == "review" for j in started["jobs"])
    assert checks.calls == []


@pytest.mark.parametrize("names, expected", [
    ([], "at least one"),
    (["agy", "agy"], "more than once"),
    (["agy", "gpt"], "gpt"),
])
@pytest.mark.usefixtures("no_launch")
def test_delegate_many_refuses_bad_executor_lists(store, repo, tmp_path, names, expected):
    srv = _server(store, tmp_path)
    assert expected in refused(srv, "delegate_many", instruction="x", repo=str(repo), executors=names)
    assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_delegate_many_starts_nothing_if_any_executor_cannot_run(store, repo, tmp_path):
    class Missing(AgyExecutor):
        def is_available(self):
            return False

    _project(tmp_path, repo, max_parallel={"agy": 1})
    srv = _server(store, tmp_path, executors={"agy": Always, "cursor": Missing})
    assert "not available" in refused(srv, "delegate_many", instruction="x", repo=str(repo),
                                      executors=["agy", "cursor"])
    assert store.all() == []
    call(srv, "delegate", instruction="x", repo=str(repo), executor="agy")
    srv = _server(store, tmp_path, executors={"agy": Always, "cursor": Always})
    assert "1 active" in refused(srv, "delegate_many", instruction="x", repo=str(repo),
                                 executors=["cursor", "agy"])
    assert len(store.all()) == 1


def test_delegate_many_starts_nothing_if_a_later_copy_fails(store, repo, tmp_path, monkeypatch):
    from polyphony import jobs
    from polyphony.workspace import WorkspaceError

    launched, real_create = [], jobs.create_job

    def create(*a, **kw):
        if kw["executor"] == "agy":
            raise WorkspaceError("disk full")
        return real_create(*a, **kw)

    monkeypatch.setattr(jobs, "create_job", create)
    monkeypatch.setattr(jobs, "launch", lambda store, job: launched.append(job.id))
    srv = _server(store, tmp_path)
    assert "disk full" in refused(srv, "delegate_many", instruction="x", repo=str(repo),
                                  executors=["cursor", "agy"])
    assert launched == []
    assert store.all() == []
    assert not any(store.dir.iterdir())


def test_delegate_many_says_it_spends_quota_on_each(server):
    tools = {t.name: t for t in anyio.run(server.list_tools)}
    assert "quota" in tools["delegate_many"].description


def test_partial_apply_names_what_was_staged_and_what_was_left_out(server, repo, fake_agy):
    fake_agy("echo good > good.py; echo bad > bad.py")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"

    msg = call(server, "apply", job_id=job_id, paths=["good.py"])
    assert "Staged 1 file(s)" in msg and "good.py" in msg
    assert "Left out" in msg and "bad.py" in msg
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "good.py"
    assert not (repo / "bad.py").exists()

    assert "already applied" in refused(server, "apply", job_id=job_id, paths=["good.py"])
    assert "Left out" not in call(server, "apply", job_id=job_id)
    assert (repo / "bad.py").exists()


def test_apply_refuses_paths_the_job_did_not_change(server, repo, fake_agy):
    fake_agy("echo good > good.py")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"
    assert "typo.py" in refused(server, "apply", job_id=job_id, paths=["typo.py"])
    assert _git("status", "--porcelain", cwd=repo) == ""


class _Stub(AgyExecutor):
    """Never probes a real binary: executors() checks availability."""

    def is_available(self):
        return True


STUBS = {"agy": _Stub, "cursor": _Stub, "claude": _Stub}


def test_repo_file_sets_the_pool(store, repo):
    (repo / ".polyphony.yaml").write_text("pool: [cursor, agy]\nmodels: {agy: m1}\n")
    srv = build_server(store=store, executors=STUBS, usage_check=Checks())
    listed = call(srv, "executors", repo=str(repo))["executors"]
    assert [e["name"] for e in listed] == ["cursor", "agy"]
    assert listed[1]["model"] == "m1"


def test_project_files_are_read_from_the_stores_home(store, repo):
    f = store.root / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True)
    f.write_text(f"name: demo\npath: {repo}\npool: [claude]\n")
    srv = build_server(store=store, executors=STUBS, usage_check=Checks())
    assert [e["name"] for e in call(srv, "executors", repo=str(repo))["executors"]] == ["claude"]


def test_malformed_repo_file_is_refused_readably(store, repo):
    (repo / ".polyphony.yaml").write_text("pool: [agy\n")
    srv = build_server(store=store, executors=STUBS, usage_check=Checks())
    assert ".polyphony.yaml" in refused(srv, "executors", repo=str(repo))


class _ReviewOnly(_Stub):
    modes = (Mode.REVIEW,)


def test_executor_without_the_mode_is_refused_by_name(store, repo):
    srv = build_server(store=store, executors={"opencode": _ReviewOnly}, usage_check=Checks())
    msg = refused(srv, "delegate", instruction="x", repo=str(repo), executor="opencode")
    assert "opencode" in msg and "code" in msg


def test_pool_skips_an_executor_without_the_mode(store, repo, fake_agy):
    fake_agy("true")
    (repo / ".polyphony.yaml").write_text("pool: [opencode, agy]\n")
    srv = build_server(store=store, executors={"opencode": _ReviewOnly, "agy": AgyExecutor},
                       usage_check=Checks())
    assert call(srv, "delegate", instruction="x", repo=str(repo))["executor"] == "agy"


def test_executors_tool_lists_each_ones_modes(store, repo):
    (repo / ".polyphony.yaml").write_text("pool: [opencode, agy]\n")
    srv = build_server(store=store, executors={"opencode": _ReviewOnly, "agy": _Stub},
                       usage_check=Checks())
    listed = {e["name"]: e["modes"] for e in call(srv, "executors", repo=str(repo))["executors"]}
    assert listed == {"opencode": ["review"], "agy": ["review", "code"]}


# --- How the lanes' tools work together. ---


def test_a_revision_streams_into_a_fresh_output(server, repo, fake_agy, store, wait_for):
    fake_agy("if [ -f a.txt ]; then echo second attempt; sleep 30; "
             "else echo one > a.txt; echo first attempt; fi")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert "first attempt" in finished(server, job_id)["output_tail"]

    call(server, "revise", job_id=job_id, feedback="more")
    wait_for(store, job_id, {"running"})
    deadline = time.monotonic() + 10
    status = call(server, "status", job_id=job_id)
    while "second attempt" not in status.get("output_tail", "") and time.monotonic() < deadline:
        time.sleep(0.1)
        status = call(server, "status", job_id=job_id)
    try:
        assert status["state"] == "running" and status["attempt"] == 2
        assert "second attempt" in status["output_tail"]
        assert "first attempt" not in status["output_tail"]
        assert "first attempt" in (store.path(job_id) / "output-1.txt").read_text()
    finally:
        call(server, "cancel", job_id=job_id)


@pytest.mark.usefixtures("no_launch")
def test_delegate_many_passes_the_check_through(store, repo, tmp_path):
    (repo / ".polyphony.yaml").write_text("check: make test\ncheck_timeout_minutes: 2\n")
    srv = _server(store, tmp_path)
    configured = call(srv, "delegate_many", instruction="x", repo=str(repo),
                      executors=["agy", "cursor"])["jobs"]
    overridden = call(srv, "delegate_many", instruction="x", repo=str(repo),
                      executors=["agy", "cursor"], check="true")["jobs"]
    skipped = call(srv, "delegate_many", instruction="x", repo=str(repo),
                   executors=["claude"], check="")["jobs"]
    load = store.load
    assert {load(j["job_id"]).check_command for j in configured} == {"make test"}
    assert {load(j["job_id"]).check_timeout_seconds for j in configured} == {120}
    assert {load(j["job_id"]).check_command for j in overridden} == {"true"}
    assert load(skipped[0]["job_id"]).check_command is None
    assert "code" in refused(srv, "delegate_many", instruction="x", repo=str(repo),
                             executors=["agy"], mode="review", check="pytest")


class _Codex(Always):
    pass


@pytest.mark.usefixtures("no_launch")
def test_opt_in_adapters_are_listed_and_capped_only_through_a_pool(store, repo, tmp_path):
    srv = _server(store, tmp_path, executors={**POOL, "codex": _Codex})
    assert "codex" not in [e["name"] for e in call(srv, "executors", repo=str(repo))["executors"]]

    (repo / ".polyphony.yaml").write_text("pool: [codex, agy]\nmax_parallel: {codex: 1}\n")
    listed = {e["name"]: e for e in call(srv, "executors", repo=str(repo))["executors"]}
    assert list(listed) == ["codex", "agy"]
    assert (listed["codex"]["active_jobs"], listed["codex"]["max_parallel"]) == (0, 1)
    assert listed["codex"]["modes"] == ["review", "code"]

    first = call(srv, "delegate", instruction="x", repo=str(repo))
    assert first["executor"] == "codex"
    second = call(srv, "delegate", instruction="x", repo=str(repo))
    assert second["executor"] == "agy"
    assert second["skipped"] == [{"executor": "codex", "reason": "at its limit of 1 active jobs"}]
    assert call(srv, "executors", repo=str(repo))["executors"][0]["active_jobs"] == 1


@pytest.mark.usefixtures("no_launch")
def test_revise_respects_the_executors_cap(store, repo, tmp_path):
    (repo / ".polyphony.yaml").write_text("max_parallel: {agy: 1}\n")
    srv = _server(store, tmp_path)
    job_id = call(srv, "delegate", instruction="x", repo=str(repo), executor="agy")["job_id"]
    job = store.load(job_id)
    job.state = "succeeded"
    store.save(job)
    call(srv, "delegate", instruction="y", repo=str(repo), executor="agy")
    assert "1 active" in refused(srv, "revise", job_id=job_id, feedback="more")
    assert store.load(job_id).attempt == 1


def test_revise_is_refused_after_a_partial_apply(server, repo, fake_agy):
    fake_agy("echo good > good.py; echo bad > bad.py")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"
    call(server, "apply", job_id=job_id, paths=["good.py"])
    assert "discard" in refused(server, "revise", job_id=job_id, feedback="fix bad.py")


def test_status_survives_check_output_that_is_not_utf8(server, repo, fake_agy):
    fake_agy("echo hi > new.txt")
    job_id = call(server, "delegate", instruction="x", repo=str(repo),
                  check="printf 'caf\\351\\n'")["job_id"]
    status = finished(server, job_id)
    assert status["check_passed"] is True
    assert "caf�" in status["check_output_tail"]


@pytest.mark.usefixtures("no_launch")
def test_no_job_limit_unless_the_project_sets_one(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    for _ in range(7):
        call(srv, "delegate", instruction="x", repo=str(repo), executor="cursor")
    assert len(store.all()) == 7


# --- Report mode: an audit whose findings are REPORT.md, read with report(). ---


def test_report_mode_delegate_status_report(server, repo, fake_agy, store):
    fake_agy("printf '# Audit\\n\\nall clear\\n' > REPORT.md; echo done")
    started = call(server, "delegate", instruction="audit errors", repo=str(repo), mode="report")
    assert started["mode"] == "report"
    status = finished(server, started["job_id"])
    assert status["state"] == "succeeded", status
    assert status["report_path"].endswith("report.md")
    assert status["report_chars"] == len("# Audit\n\nall clear\n")
    assert status["stray_changes"] == []

    page = call(server, "report", job_id=started["job_id"])
    assert page["text"] == "# Audit\n\nall clear\n" and page["more"] is False
    assert call(server, "report", job_id=started["job_id"], limit=3)["more"] is True
    assert "offset" in refused(server, "report", job_id=started["job_id"], offset=-1)
    assert "limit" in refused(server, "report", job_id=started["job_id"], limit=0)
    assert "report()" in refused(server, "apply", job_id=started["job_id"])
    assert _git("status", "--porcelain", cwd=repo) == ""


def test_report_mode_status_shows_stray_changes(server, repo, fake_agy):
    fake_agy("echo r > REPORT.md; echo y > app.py")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), mode="report")["job_id"]
    assert finished(server, job_id)["stray_changes"] == ["app.py"]


def test_report_mode_without_a_report_fails_readably(server, repo, fake_agy):
    fake_agy("echo findings only on stdout")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), mode="report")["job_id"]
    status = finished(server, job_id)
    assert status["state"] == "failed"
    assert "REPORT.md" in status["error"]
    assert status["report_path"] is None and status["report_chars"] == 0
    assert "findings only on stdout" in status["output_tail"]
    assert "no report" in refused(server, "report", job_id=job_id)


def test_report_refuses_a_running_or_code_job(server, repo, fake_agy, store, wait_for):
    fake_agy("sleep 30")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), mode="report")["job_id"]
    wait_for(store, job_id, {"running"})
    try:
        assert "still running" in refused(server, "report", job_id=job_id)
        assert "report_path" not in call(server, "status", job_id=job_id)
    finally:
        call(server, "cancel", job_id=job_id)
    fake_agy("true")
    code = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    finished(server, code)
    assert "report_path" not in finished(server, code)
    assert "only a report job" in refused(server, "report", job_id=code)
    assert "No job" in refused(server, "report", job_id="nope")


def test_revising_a_report_job_writes_a_fresh_report(server, repo, fake_agy, store):
    fake_agy("if [ -f REPORT.md ]; then echo second > REPORT.md; "
             "else echo first > REPORT.md; fi")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), mode="report")["job_id"]
    finished(server, job_id)
    call(server, "revise", job_id=job_id, feedback="go deeper")
    status = finished(server, job_id)
    assert status["state"] == "succeeded" and status["attempt"] == 2
    assert call(server, "report", job_id=job_id)["text"] == "second\n"
    assert (store.path(job_id) / "report-1.md").read_text() == "first\n"


def test_a_check_in_report_mode_is_refused(server, repo):
    msg = refused(server, "delegate", instruction="x", repo=str(repo), mode="report",
                  check="pytest")
    assert "code" in msg and "report" in msg


def test_report_mode_needs_an_executor_with_a_code_mode(store, repo, fake_agy):
    srv = build_server(store=store, executors={"opencode": _ReviewOnly}, usage_check=Checks())
    msg = refused(srv, "delegate", instruction="x", repo=str(repo), executor="opencode",
                  mode="report")
    assert "opencode" in msg and "code" in msg
    msg = refused(srv, "delegate_many", instruction="x", repo=str(repo),
                  executors=["opencode"], mode="report")
    assert "opencode" in msg and "code" in msg

    fake_agy("echo r > REPORT.md")
    (repo / ".polyphony.yaml").write_text("pool: [opencode, agy]\n")
    srv = build_server(store=store, executors={"opencode": _ReviewOnly, "agy": AgyExecutor},
                       usage_check=Checks())
    started = call(srv, "delegate", instruction="x", repo=str(repo), mode="report")
    assert started["executor"] == "agy"
    assert started["skipped"] == [{"executor": "opencode", "reason": "has no code mode"}]
    finished(srv, started["job_id"])


@pytest.mark.usefixtures("no_launch")
def test_delegate_many_takes_report_mode(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    started = call(srv, "delegate_many", instruction="x", repo=str(repo),
                   executors=["agy", "cursor"], mode="report")["jobs"]
    assert [j["mode"] for j in started] == ["report", "report"]
