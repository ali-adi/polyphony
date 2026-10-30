"""The MCP tools, called in-process exactly as a client would call them."""

import hashlib
import json
import subprocess
import time

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from polyphony.config import DEFAULT_MODELS
from polyphony.jobs import MAX_BRIEF_BYTES, MAX_PROMPT_BYTES
from polyphony.server import INSTRUCTIONS, build_server

TOOLS = {
    "delegate", "revise", "status", "diff", "apply", "discard", "cancel", "jobs", "usage",
    "stats", "report", "wait", "apply_many",
}


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class Checks:
    """A stand-in for agy_usage, so no test ever runs a real usage check."""

    def __init__(self, report=None):
        self.report, self.calls = report or {"ok": True, "limits": []}, 0

    def __call__(self):
        self.calls += 1
        return self.report


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
    assert started["model"] == DEFAULT_MODELS["code"]
    job_id = started["job_id"]
    assert _git("branch", "--list", "polyphony/*", cwd=repo) == ""
    assert len(_git("worktree", "list", cwd=repo).splitlines()) == 1

    status = finished(server, job_id)
    assert status["state"] == "succeeded", status
    assert status["files_changed"] == ["hello.py"]
    assert "wrote it" in status["recent"]

    assert "+print('hi')" in call(server, "diff", job_id=job_id)

    msg = call(server, "apply", job_id=job_id)
    assert "hello.py" in msg and "not committed" in msg
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "hello.py"
    assert _git("rev-list", "--count", "HEAD", cwd=repo) == commits_before

    assert not store.path(job_id).exists(), "a fully applied job is deleted"
    assert "No job" in refused(server, "status", job_id=job_id)
    assert "No job" in refused(server, "discard", job_id=job_id)


def test_discard_deletes_a_finished_job(server, repo, fake_agy, store):
    fake_agy("echo hi > new.txt")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"
    call(server, "discard", job_id=job_id)
    assert not store.path(job_id).exists()
    assert "No job" in refused(server, "status", job_id=job_id)
    assert _git("status", "--porcelain", cwd=repo) == ""


def test_delegate_resolves_a_subdirectory_to_the_repo_root(server, repo, fake_agy):
    fake_agy("true")
    (repo / "pkg").mkdir()
    started = call(server, "delegate", instruction="x", repo=str(repo / "pkg"))
    assert started["repo"] == str(repo.resolve())


def test_bad_mode_is_refused(server, repo):
    msg = refused(server, "delegate", instruction="x", repo=str(repo), mode="yolo")
    assert "code" in msg and "report" in msg
    assert "review" not in msg


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
    assert not store.path(job_id).exists(), "cancel deletes the job"
    assert "No job" in refused(server, "discard", job_id=job_id)
    assert "No job" in refused(server, "status", job_id=job_id)


def test_status_shows_output_while_running(server, repo, fake_agy, store, wait_for):
    fake_agy("echo hi > new.txt; echo step one done; sleep 30")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    wait_for(store, job_id, {"running"})
    deadline = time.monotonic() + 10
    status = call(server, "status", job_id=job_id)
    while ("step one done" not in status.get("recent", [])
           or "files_touched" not in status) and time.monotonic() < deadline:
        time.sleep(0.1)
        status = call(server, "status", job_id=job_id)
    try:
        assert status["state"] == "running"
        assert "step one done" in status["recent"]
        assert status["files_touched"] == ["new.txt"]
        assert status["output_path"] == str(store.output_path(job_id))
        assert "files_changed" not in status, "only a finished job has a result"
        assert "response" not in status
    finally:
        call(server, "cancel", job_id=job_id)


def test_status_shows_the_agents_events_and_final_response(server, repo, fake_agy):
    fake_agy("""cat <<'EOF'
{"event":"init"}
{"event":"step","step_update":{"state":"DONE","step_type":"TOOL_CALL","tool_name":"write_file","tool_info":{"parameters":{"file_path":"/w/hello.py"}}}}
{"event":"result","result":{"status":"SUCCESS","response":"all done"}}
EOF
echo hi > hello.py""")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    status = finished(server, job_id)
    assert status["state"] == "succeeded", status
    assert status["recent"] == ["DONE TOOL_CALL write_file hello.py"]
    assert status["response"] == "all done"
    assert "files_touched" not in status, "only a running job has pending changes"
    assert "executor" not in status and "output_tail" not in status


def test_status_of_a_queued_job_has_no_output_yet(server, repo, store):
    from polyphony.config import ProjectConfig
    from polyphony.jobs import create_job
    job = create_job(store, ProjectConfig(name="d", path=repo), "x", "code")
    status = call(server, "status", job_id=job.id)
    assert status["state"] == "queued"
    assert "recent" not in status and "output_path" not in status


def test_jobs_lists_recent_jobs(server, repo, fake_agy):
    fake_agy("true")
    job_id = call(server, "delegate", instruction="list me", repo=str(repo))["job_id"]
    listed = call(server, "jobs")["jobs"]
    assert listed[0]["job_id"] == job_id
    assert listed[0]["instruction"] == "list me"
    assert listed[0]["model"] == DEFAULT_MODELS["code"] and listed[0]["mode"] == "code"
    assert "executor" not in listed[0]


def test_usage_tool_reports_what_agy_prints(store, tmp_path, fake_agy):
    fake_agy("printf 'Gemini Models\\tWeekly Limit Remaining\\t50%%\\tOct 1\\n'")
    server = build_server(store=store, projects_dir=tmp_path / "none")  # the real agy_usage
    assert call(server, "usage") == {"usage": {"ok": True, "limits": [
        {"models": "Gemini Models", "window": "Weekly Limit", "remaining_percent": 50.0,
         "resets_at": "Oct 1"},
    ]}}


def test_usage_tool_reports_a_failed_check(server, store, tmp_path):
    srv = build_server(store=store, projects_dir=tmp_path / "none",
                       usage_check=Checks({"ok": False, "error": "no"}))
    assert call(srv, "usage") == {"usage": {"ok": False, "error": "no"}}


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


def test_stats_summarizes_recorded_outcomes(server, repo, fake_agy):
    fake_agy("echo hi > new.txt")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), check="true")["job_id"]
    finished(server, job_id)
    call(server, "apply", job_id=job_id)
    assert "No job" in refused(server, "discard", job_id=job_id)

    [agy] = call(server, "stats")["executors"]
    assert agy["executor"] == "agy"
    assert (agy["jobs"], agy["succeeded"], agy["applied"], agy["discarded"]) == (1, 1, 1, 0)
    assert agy["check_pass_rate"] == 1.0


def test_stats_counts_a_discard_and_a_cancel(server, repo, fake_agy, store, wait_for):
    fake_agy("echo hi > new.txt")
    discarded = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    finished(server, discarded)
    call(server, "discard", job_id=discarded)

    fake_agy("sleep 30")
    cancelled = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    wait_for(store, cancelled, {"running"})
    call(server, "cancel", job_id=cancelled)

    [agy] = call(server, "stats")["executors"]
    assert (agy["jobs"], agy["discarded"], agy["cancelled"]) == (2, 1, 1)


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
    assert "second" in status["recent"]

    call(server, "apply", job_id=job_id)
    assert _git("diff", "--cached", "--name-only", cwd=repo).splitlines() == ["a.txt", "b.txt"]
    assert "No job" in refused(server, "revise", job_id=job_id, feedback="more")


def test_revise_refusals(server, repo, fake_agy, store, wait_for):
    fake_agy("sleep 30")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    wait_for(store, job_id, {"running"})
    assert "running" in refused(server, "revise", job_id=job_id, feedback="more")
    call(server, "cancel", job_id=job_id)
    assert "No job" in refused(server, "revise", job_id=job_id, feedback="more")

    fake_agy("true")
    done = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    finished(server, done)
    assert "feedback" in refused(server, "revise", job_id=done, feedback=" ")
    assert "positive" in refused(server, "revise", job_id=done, feedback="x", timeout_minutes=0)
    assert store.load(done).attempt == 1
    assert "No job" in refused(server, "revise", job_id="nope", feedback="x")


# --- Quota, the concurrency cap, and the project's model. ---

ARGON = "gemini-4-argon-high"
RESET = "2026-10-01T02:17:05Z"


def _limits(group, remaining):
    return {"ok": True, "limits": [
        {"models": group, "window": f"{group} Weekly Limit", "remaining_percent": remaining,
         "resets_at": RESET},
    ]}


ARGON_LOW = _limits("Gemini 4 Argon", 1.0)


@pytest.fixture
def no_launch(monkeypatch):
    """Record jobs without starting a worker, which would run the real CLI
    named by the job. A queued job holds a slot like a running one."""
    from polyphony import jobs
    monkeypatch.setattr(jobs, "launch", lambda store, job: None)


def _server(store, tmp_path, checks=None, **kw):
    return build_server(store=store, projects_dir=tmp_path / "projects",
                        usage_check=checks or Checks(), **kw)


def _project(tmp_path, repo, **data):
    f = tmp_path / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"name": "demo", "path": str(repo), **data}))


@pytest.mark.usefixtures("no_launch")
def test_a_model_out_of_quota_is_refused_with_its_reset_time(store, repo, tmp_path):
    srv = _server(store, tmp_path, Checks(ARGON_LOW))
    msg = refused(srv, "delegate", instruction="x", repo=str(repo), model=ARGON)
    assert ARGON in msg and "Gemini 4 Argon Weekly Limit" in msg and RESET in msg
    assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_a_model_in_another_group_is_allowed_while_argon_is_low(store, repo, tmp_path):
    srv = _server(store, tmp_path, Checks(ARGON_LOW))
    started = call(srv, "delegate", instruction="x", repo=str(repo))
    assert started["model"] == DEFAULT_MODELS["code"]
    assert "quota_unknown" not in started
    assert len(store.all()) == 1


@pytest.mark.parametrize("remaining, allowed", [(5.0, False), (5.1, True)])
@pytest.mark.usefixtures("no_launch")
def test_the_quota_floor_is_five_percent(store, repo, tmp_path, remaining, allowed):
    srv = _server(store, tmp_path, Checks(_limits("Gemini Models", remaining)))
    if allowed:
        call(srv, "delegate", instruction="x", repo=str(repo))
        assert len(store.all()) == 1
    else:
        assert RESET in refused(srv, "delegate", instruction="x", repo=str(repo))
        assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_a_broken_usage_check_lets_the_job_through(store, repo, tmp_path):
    srv = _server(store, tmp_path, Checks({"ok": False, "error": "agy is down"}))
    started = call(srv, "delegate", instruction="x", repo=str(repo), model=ARGON)
    assert started["quota_unknown"] == "agy is down"
    assert len(store.all()) == 1


@pytest.mark.usefixtures("no_launch")
def test_usage_reports_are_cached_across_delegates_and_servers(store, repo, tmp_path):
    checks = Checks()
    call(_server(store, tmp_path, checks), "delegate", instruction="x", repo=str(repo))
    call(_server(store, tmp_path, checks), "delegate", instruction="y", repo=str(repo))
    assert checks.calls == 1
    assert (store.root / "usage-cache.json").exists()


@pytest.mark.usefixtures("no_launch")
def test_usage_is_checked_again_after_the_ttl(store, repo, tmp_path):
    checks = Checks()
    srv = _server(store, tmp_path, checks, usage_ttl=0)
    call(srv, "delegate", instruction="x", repo=str(repo))
    call(srv, "delegate", instruction="y", repo=str(repo))
    assert checks.calls == 2


@pytest.mark.usefixtures("no_launch")
def test_usage_tool_refreshes_the_cache_that_delegate_reads(store, repo, tmp_path):
    checks = Checks(ARGON_LOW)
    srv = _server(store, tmp_path, checks)
    assert call(srv, "usage") == {"usage": ARGON_LOW}
    assert RESET in refused(srv, "delegate", instruction="x", repo=str(repo), model=ARGON)
    assert checks.calls == 1


@pytest.mark.usefixtures("no_launch")
def test_revise_is_gated_by_quota_too(store, repo, tmp_path):
    checks = Checks()
    srv = _server(store, tmp_path, checks, usage_ttl=0)
    job_id = call(srv, "delegate", instruction="x", repo=str(repo), model=ARGON)["job_id"]
    job = store.load(job_id)
    job.state = "succeeded"
    store.save(job)

    checks.report = ARGON_LOW
    msg = refused(srv, "revise", job_id=job_id, feedback="more")
    assert ARGON in msg and RESET in msg
    assert store.load(job_id).attempt == 1

    checks.report = {"ok": False, "error": "agy is down"}
    revised = call(srv, "revise", job_id=job_id, feedback="more")
    assert revised["attempt"] == 2 and revised["quota_unknown"] == "agy is down"


def test_agy_not_installed_is_refused(server, repo, store, fake_agy, monkeypatch):
    fake_agy("true")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    finished(server, job_id)

    monkeypatch.setattr("polyphony.agy.binary", lambda: None)
    assert "agy is not installed." in refused(server, "delegate", instruction="x", repo=str(repo))
    assert "agy is not installed." in refused(server, "revise", job_id=job_id, feedback="x")
    assert [j.id for j in store.all()] == [job_id]
    assert store.load(job_id).attempt == 1


@pytest.mark.usefixtures("no_launch")
def test_a_project_at_its_cap_refuses_a_delegate(store, repo, tmp_path):
    _project(tmp_path, repo, max_parallel=2)
    srv = _server(store, tmp_path)
    for _ in range(2):
        call(srv, "delegate", instruction="x", repo=str(repo))
    msg = refused(srv, "delegate", instruction="x", repo=str(repo))
    assert "active" in msg and "limit of 2" in msg
    assert len(store.all()) == 2


@pytest.mark.usefixtures("no_launch")
def test_the_cap_counts_jobs_from_every_project(store, repo, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _git("init", "-q", "-b", "main", cwd=other)
    _git("-c", "user.email=t@e", "-c", "user.name=T", "commit", "-q", "--allow-empty",
         "-m", "init", cwd=other)
    _project(tmp_path, repo, max_parallel=1)
    srv = _server(store, tmp_path)
    call(srv, "delegate", instruction="x", repo=str(other))
    assert "active" in refused(srv, "delegate", instruction="x", repo=str(repo))


@pytest.mark.usefixtures("no_launch")
def test_a_dead_worker_does_not_hold_a_slot(store, repo, tmp_path):
    _project(tmp_path, repo, max_parallel=1)
    srv = _server(store, tmp_path)
    job_id = call(srv, "delegate", instruction="x", repo=str(repo))["job_id"]
    p = subprocess.Popen(["true"])
    p.wait()
    job = store.load(job_id)
    job.state, job.pid = "running", p.pid
    store.save(job)
    call(srv, "delegate", instruction="x", repo=str(repo))
    assert len(store.all()) == 2


@pytest.mark.usefixtures("no_launch")
def test_revise_respects_the_cap(store, repo, tmp_path):
    (repo / ".polyphony.yaml").write_text("max_parallel: 1\n")
    srv = _server(store, tmp_path)
    job_id = call(srv, "delegate", instruction="x", repo=str(repo))["job_id"]
    job = store.load(job_id)
    job.state = "succeeded"
    store.save(job)
    call(srv, "delegate", instruction="y", repo=str(repo))
    assert "limit of 1" in refused(srv, "revise", job_id=job_id, feedback="more")
    assert store.load(job_id).attempt == 1


@pytest.mark.usefixtures("no_launch")
def test_no_job_limit_unless_the_project_sets_one(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    for _ in range(7):
        call(srv, "delegate", instruction="x", repo=str(repo))
    assert len(store.all()) == 7


@pytest.mark.usefixtures("no_launch")
def test_project_config_sets_the_model_per_mode(store, repo, tmp_path):
    _project(tmp_path, repo, models={"code": "gemini-3.8-flash-high", "report": ARGON})
    srv = _server(store, tmp_path)
    assert call(srv, "delegate", instruction="x", repo=str(repo))["model"] == "gemini-3.8-flash-high"
    assert call(srv, "delegate", instruction="x", repo=str(repo), mode="report")["model"] == ARGON
    assert call(srv, "delegate", instruction="x", repo=str(repo), mode="report",
                model="picked")["model"] == "picked"

    gated = _server(store, tmp_path, Checks(ARGON_LOW), usage_ttl=0)
    assert ARGON in refused(gated, "delegate", instruction="x", repo=str(repo), mode="report")
    call(gated, "delegate", instruction="x", repo=str(repo))


@pytest.mark.usefixtures("no_launch")
def test_a_repo_without_config_gets_the_default_models(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    assert call(srv, "delegate", instruction="x", repo=str(repo))["model"] == DEFAULT_MODELS["code"]
    assert call(srv, "delegate", instruction="x", repo=str(repo),
                mode="report")["model"] == DEFAULT_MODELS["report"]


def test_project_files_are_read_from_the_stores_home(store, repo, fake_agy):
    fake_agy("true")
    f = store.root / "projects" / "demo" / "project.yaml"
    f.parent.mkdir(parents=True)
    f.write_text(f"name: demo\npath: {repo}\nmodels: {{code: from-home}}\n")
    srv = build_server(store=store, usage_check=Checks())
    started = call(srv, "delegate", instruction="x", repo=str(repo))
    assert started["model"] == "from-home"
    finished(srv, started["job_id"])


@pytest.mark.parametrize("config", ["models: [code\n", "models: {agy: m1}\n"])
def test_malformed_repo_file_is_refused_readably(store, repo, config):
    (repo / ".polyphony.yaml").write_text(config)
    srv = build_server(store=store, usage_check=Checks())
    assert ".polyphony.yaml" in refused(srv, "delegate", instruction="x", repo=str(repo))
    assert store.all() == []

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


# --- How the lanes' tools work together. ---


def test_a_revision_streams_into_a_fresh_output(server, repo, fake_agy, store, wait_for):
    fake_agy("if [ -f a.txt ]; then echo second attempt; sleep 30; "
             "else echo one > a.txt; echo first attempt; fi")
    job_id = call(server, "delegate", instruction="x", repo=str(repo))["job_id"]
    assert "first attempt" in finished(server, job_id)["recent"]

    call(server, "revise", job_id=job_id, feedback="more")
    wait_for(store, job_id, {"running"})
    deadline = time.monotonic() + 10
    status = call(server, "status", job_id=job_id)
    while "second attempt" not in status.get("recent", []) and time.monotonic() < deadline:
        time.sleep(0.1)
        status = call(server, "status", job_id=job_id)
    try:
        assert status["state"] == "running" and status["attempt"] == 2
        assert "second attempt" in status["recent"]
        assert "first attempt" not in status["recent"]
        assert "first attempt" in (store.path(job_id) / "output-1.txt").read_text()
    finally:
        call(server, "cancel", job_id=job_id)


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


def test_status_lists_withheld_secrets(server, repo, fake_agy):
    fake_agy("true")
    (repo / ".env").write_text("API_KEY=real\n")
    started = call(server, "delegate", instruction="x", repo=str(repo))
    assert started["withheld"] == [".env"]
    assert "allow_secrets" in started["withheld_note"]
    status = finished(server, started["job_id"])
    assert status["withheld"] == [".env"]


def test_status_has_no_withheld_key_when_nothing_was(server, repo, fake_agy):
    fake_agy("true")
    status = finished(server, call(server, "delegate", instruction="x", repo=str(repo))["job_id"])
    assert "withheld" not in status


# --- Lane r2-brief: the task from a file, confirming it arrived whole, and a model per call. ---


def _record_prompt(fake_agy):
    """The fake agy keeps its prompt (given as -p=<text>) and its argv beside the copy."""
    fake_agy('for a in "$@"; do case "$a" in -p=*) printf "%s" "${a#-p=}" > ../prompt.txt;; '
             'esac; done; echo "$@" > ../argv.txt')


def test_delegate_with_a_brief_file_gives_the_executor_the_whole_task(
        server, repo, fake_agy, store, tmp_path):
    _record_prompt(fake_agy)
    brief = tmp_path / "brief.md"
    text = "# Brief\n\n" + "step\n" * 20_000 + "THE END"
    brief.write_text(text)

    started = call(server, "delegate", instruction="Do what the brief says.",
                   repo=str(repo), brief_path=str(brief))
    job_id = started["job_id"]
    full = "Do what the brief says.\n\n" + text
    assert started["brief_path"] == str(brief.resolve())
    assert started["instruction_chars"] == len(full)
    assert started["instruction_sha256"] == hashlib.sha256(full.encode()).hexdigest()
    assert started["instruction_tail"] == full[-200:]
    assert (store.path(job_id) / "brief.md").read_text() == text

    brief.write_text("edited after delegating")
    assert finished(server, job_id)["state"] == "succeeded"
    assert (store.path(job_id) / "prompt.txt").read_text() == full

    # A revision restates the brief as copied, not as the file reads now.
    call(server, "revise", job_id=job_id, feedback="again")
    status = finished(server, job_id)
    assert status["instruction_chars"] == len(full)  # feedback is not counted
    assert (store.path(job_id) / "prompt.txt").read_text().startswith(full + "\n\n---\n")


@pytest.mark.usefixtures("no_launch")
def test_a_brief_alone_is_the_task_and_a_relative_path_is_from_the_repo(store, repo, tmp_path):
    (repo / "docs").mkdir()
    (repo / "docs" / "brief.md").write_text("only the brief\n")
    srv = _server(store, tmp_path)
    started = call(srv, "delegate", repo=str(repo / "docs"), brief_path="brief.md")
    job = store.load(started["job_id"])
    assert job.instruction == "only the brief\n"
    assert job.brief_path == str((repo / "docs" / "brief.md").resolve())
    assert started["instruction_tail"] == "only the brief\n"


@pytest.mark.usefixtures("no_launch")
def test_status_reports_the_instruction_for_every_job(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    job_id = call(srv, "delegate", instruction="short task", repo=str(repo))["job_id"]
    status = call(srv, "status", job_id=job_id)
    assert status["instruction_chars"] == 10
    assert status["instruction_tail"] == "short task"
    assert status["instruction_sha256"] == hashlib.sha256(b"short task").hexdigest()
    assert "brief_path" not in status


@pytest.mark.parametrize("setup, expected", [
    (lambda f: None, "no such file"),
    (lambda f: f.mkdir(), "not a regular file"),
    (lambda f: f.write_bytes(b"x" * (MAX_BRIEF_BYTES + 1)), "limit"),
    (lambda f: f.write_bytes(b"caf\xe9"), "UTF-8"),
    (lambda f: f.write_text(" \n"), "empty"),
])
@pytest.mark.usefixtures("no_launch")
def test_a_bad_brief_is_refused_before_anything_is_copied(store, repo, tmp_path, setup, expected):
    brief = tmp_path / "brief.md"
    setup(brief)
    srv = _server(store, tmp_path)
    assert expected in refused(srv, "delegate", instruction="x", repo=str(repo),
                               brief_path=str(brief))
    assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_a_brief_at_the_limit_is_accepted(store, repo, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_bytes(b"x" * MAX_BRIEF_BYTES)
    started = call(_server(store, tmp_path), "delegate", repo=str(repo), brief_path=str(brief))
    assert started["instruction_chars"] == MAX_BRIEF_BYTES


@pytest.mark.usefixtures("no_launch")
def test_delegate_needs_an_instruction_or_a_brief(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    assert "brief_path" in refused(srv, "delegate", repo=str(repo))
    assert "brief_path" in refused(srv, "delegate", instruction="  ", brief_path="",
                                   repo=str(repo))
    assert store.all() == []


def test_delegate_model_overrides_the_projects_and_revise_keeps_it(server, repo, fake_agy, store):
    (repo / ".polyphony.yaml").write_text("models: {code: configured}\n")
    _record_prompt(fake_agy)
    started = call(server, "delegate", instruction="x", repo=str(repo), model=" picked ")
    job_id = started["job_id"]
    assert started["model"] == "picked"
    finished(server, job_id)
    assert "--model picked" in (store.path(job_id) / "argv.txt").read_text()

    call(server, "revise", job_id=job_id, feedback="again")
    assert finished(server, job_id)["model"] == "picked"
    assert "--model picked" in (store.path(job_id) / "argv.txt").read_text()

    default = call(server, "delegate", instruction="x", repo=str(repo))
    assert default["model"] == "configured"
    finished(server, default["job_id"])


def test_a_blank_model_is_refused(server, repo, store):
    assert "blank" in refused(server, "delegate", instruction="x", repo=str(repo), model="")
    assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_a_task_too_long_for_one_argument_is_refused(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    over = "x" * (MAX_PROMPT_BYTES + 1)
    assert "limit" in refused(srv, "delegate", instruction=over, repo=str(repo))
    # A brief under its own limit still counts toward the task's, with the instruction.
    brief = tmp_path / "brief.md"
    brief.write_bytes(b"b" * MAX_BRIEF_BYTES)
    long_lead = "i" * (MAX_PROMPT_BYTES - MAX_BRIEF_BYTES)
    assert "limit" in refused(srv, "delegate", instruction=long_lead, repo=str(repo),
                              brief_path=str(brief))
    # Bytes, not characters: what the kernel counts.
    assert "limit" in refused(srv, "delegate", repo=str(repo),
                              instruction="\u00e9" * (MAX_PROMPT_BYTES // 2 + 1))
    assert store.all() == []


@pytest.mark.usefixtures("no_launch")
def test_report_modes_request_counts_toward_the_limit(store, repo, tmp_path):
    from polyphony.jobs import REPORT_INSTRUCTION
    srv = _server(store, tmp_path)
    fits_in_code_mode = "x" * (MAX_PROMPT_BYTES - len(REPORT_INSTRUCTION))
    assert "limit" in refused(srv, "delegate", instruction=fits_in_code_mode, repo=str(repo),
                              mode="report")
    call(srv, "delegate", instruction=fits_in_code_mode, repo=str(repo))


def test_revise_is_refused_once_feedback_would_pass_the_limit(server, repo, fake_agy, store):
    fake_agy("true")
    job_id = call(server, "delegate", instruction="x" * (MAX_PROMPT_BYTES - 1000),
                  repo=str(repo))["job_id"]
    finished(server, job_id)
    assert "limit" in refused(server, "revise", job_id=job_id, feedback="f" * 2000)
    job = store.load(job_id)
    assert job.attempt == 1 and job.feedback == []  # nothing was queued
    call(server, "revise", job_id=job_id, feedback="short")


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
    assert "findings only on stdout" in status["recent"]
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



# wait lane

SLOW_OR_FAST = 'case "$*" in *SLOW*) sleep 30;; *) sleep 1; echo fast > fast.txt;; esac'


def _started(server, repo, *instructions):
    return [call(server, "delegate", instruction=i, repo=str(repo))["job_id"]
            for i in instructions]


def test_wait_any_returns_when_the_first_job_finishes(server, repo, fake_agy):
    fake_agy(SLOW_OR_FAST)
    slow, fast = _started(server, repo, "SLOW", "quick")
    try:
        began = time.monotonic()
        result = call(server, "wait", job_ids=[slow, fast], wait_seconds=20)
        assert time.monotonic() - began < 10
        assert result["done"] is True
        assert result["finished"] == [fast]
        assert result["active"] == [slow]
        assert [j["job_id"] for j in result["jobs"]] == [slow, fast], "keeps the caller's order"
        compact, full = result["jobs"]
        brief = {"job_id", "state", "elapsed_seconds"}
        assert set(compact) in (brief, brief | {"recent", "files_touched"})
        assert compact["state"] in ("queued", "running")
        assert full["state"] == "succeeded"
        assert full["files_changed"] == ["fast.txt"]
        assert "recent" in full and "output_path" in full
    finally:
        call(server, "cancel", job_id=slow)


def test_wait_shows_a_running_job_briefly(server, repo, fake_agy, store, wait_for):
    fake_agy("for i in 1 2 3 4 5; do echo step $i; done; echo hi > new.txt; sleep 30")
    (job_id,) = _started(server, repo, "x")
    try:
        wait_for(store, job_id, {"running"})
        deadline = time.monotonic() + 10
        [brief] = call(server, "wait", job_ids=[job_id], wait_seconds=0)["jobs"]
        while brief.get("recent") != ["step 3", "step 4", "step 5"] and time.monotonic() < deadline:
            time.sleep(0.1)
            [brief] = call(server, "wait", job_ids=[job_id], wait_seconds=0)["jobs"]
        assert set(brief) == {"job_id", "state", "elapsed_seconds", "recent", "files_touched"}
        assert brief["state"] == "running"
        assert brief["recent"] == ["step 3", "step 4", "step 5"]
        assert brief["files_touched"] == ["new.txt"]
    finally:
        call(server, "cancel", job_id=job_id)


def test_wait_all_waits_for_every_job(server, repo, fake_agy):
    fake_agy("sleep 1; echo done")
    first, second = _started(server, repo, "a", "b")
    result = call(server, "wait", job_ids=[first, second], until="all", wait_seconds=20)
    assert result["done"] is True
    assert result["finished"] == [first, second]
    assert result["active"] == []
    assert [j["state"] for j in result["jobs"]] == ["succeeded", "succeeded"]


def test_wait_times_out_with_done_false(server, repo, fake_agy):
    fake_agy(SLOW_OR_FAST)
    slow, fast = _started(server, repo, "SLOW", "quick")
    try:
        result = call(server, "wait", job_ids=[slow, fast], until="all", wait_seconds=3)
        assert result["done"] is False
        assert result["finished"] == [fast]
        assert result["active"] == [slow]
    finally:
        call(server, "cancel", job_id=slow)


def test_wait_any_returns_at_once_if_a_job_already_finished(server, repo, fake_agy):
    fake_agy(SLOW_OR_FAST)
    slow, fast = _started(server, repo, "SLOW", "quick")
    try:
        assert call(server, "wait", job_ids=[fast], wait_seconds=20)["done"] is True
        began = time.monotonic()
        result = call(server, "wait", job_ids=[slow, fast], wait_seconds=20)
        assert time.monotonic() - began < 2
        assert result["done"] is True and result["finished"] == [fast]
    finally:
        call(server, "cancel", job_id=slow)


def test_wait_without_waiting_reports_at_once(server, repo, fake_agy):
    fake_agy("sleep 30")
    (job_id,) = _started(server, repo, "x")
    try:
        result = call(server, "wait", job_ids=[job_id], wait_seconds=0)
        assert result == {"done": False, "finished": [], "active": [job_id],
                          "jobs": [result["jobs"][0]]}
        assert result["jobs"][0]["job_id"] == job_id
    finally:
        call(server, "cancel", job_id=job_id)


@pytest.mark.parametrize("args, expected", [
    ({"job_ids": []}, "at least one"),
    ({"job_ids": ["a", "a"]}, "more than once"),
    ({"job_ids": ["a"], "until": "some"}, "until"),
])
def test_wait_refuses_bad_arguments(server, args, expected):
    assert expected in refused(server, "wait", **args)


def test_wait_refuses_an_unknown_job_before_waiting(server, repo, fake_agy):
    fake_agy("sleep 30")
    (job_id,) = _started(server, repo, "x")
    try:
        began = time.monotonic()
        assert "No job" in refused(server, "wait", job_ids=[job_id, "nope"], wait_seconds=20)
        assert time.monotonic() - began < 2
    finally:
        call(server, "cancel", job_id=job_id)


def test_a_job_cancelled_elsewhere_during_a_wait_counts_as_finished(server, repo, fake_agy, store):
    import threading
    fake_agy("sleep 30")
    (job_id,) = _started(server, repo, "x")
    canceller = threading.Timer(1.5, lambda: call(server, "cancel", job_id=job_id))
    canceller.start()
    result = call(server, "wait", job_ids=[job_id], wait_seconds=20)
    canceller.join()
    assert result["done"] and result["finished"] == [job_id]
    assert result["jobs"][0]["state"] == "deleted"


def test_status_and_instructions_point_at_wait(server):
    tools = {t.name: t for t in anyio.run(server.list_tools)}
    assert "use wait" in tools["status"].description
    assert "call the wait tool" in INSTRUCTIONS


# --- Lane reportapi: argument edges, and status reading only files' ends. ---


@pytest.mark.usefixtures("no_launch")
def test_a_relative_brief_path_is_from_the_repo_directory_given(store, repo, tmp_path):
    (repo / "pkg").mkdir()
    (repo / "pkg" / "brief.md").write_text("the package's brief\n")
    (repo / "brief.md").write_text("the root's brief\n")
    srv = _server(store, tmp_path)
    started = call(srv, "delegate", repo=str(repo / "pkg"), brief_path="brief.md")
    assert store.load(started["job_id"]).instruction == "the package's brief\n"


@pytest.mark.usefixtures("no_launch")
def test_timeout_minutes_is_at_most_a_day(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    assert "at most 1440" in refused(srv, "delegate", instruction="x", repo=str(repo),
                                     timeout_minutes=50000)
    assert "at most 1440" in refused(srv, "revise", job_id="nope", feedback="x",
                                     timeout_minutes=50000)
    call(srv, "delegate", instruction="x", repo=str(repo), timeout_minutes=1440)


@pytest.mark.usefixtures("no_launch")
def test_a_nul_byte_in_the_task_is_refused_up_front(store, repo, tmp_path):
    srv = _server(store, tmp_path)
    assert "NUL" in refused(srv, "delegate", instruction="a\0b", repo=str(repo))
    (repo / "brief.md").write_text("a\0b\n")
    assert "NUL" in refused(srv, "delegate", repo=str(repo), brief_path="brief.md")
    assert store.all() == []


def test_status_reads_only_the_end_of_output_and_report(server, repo, fake_agy, monkeypatch):
    from pathlib import Path
    fake_agy("printf '# Audit\\n\\nall clear\\n' > REPORT.md; seq 1 20000")
    job_id = call(server, "delegate", instruction="x", repo=str(repo), mode="report")["job_id"]
    assert finished(server, job_id)["state"] == "succeeded"
    read_text = Path.read_text

    def whole_file(self, *a, **kw):
        assert self.name not in ("output.txt", "report.md", "check.txt"), f"read all of {self}"
        return read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", whole_file)
    status = call(server, "status", job_id=job_id)
    assert status["report_chars"] == len("# Audit\n\nall clear\n")
    assert status["recent"][-1] == "20000"
    assert len(status["recent"]) == 8
    assert "report_truncated" not in status


def test_delegate_deletes_jobs_left_unresolved_for_a_week(server, repo, fake_agy, store):
    from polyphony import ledger
    fake_agy("true")
    (old,) = _started(server, repo, "old")
    finished(server, old)
    job = store.load(old)
    job.finished_at = time.time() - 8 * 86400
    store.save(job)
    (recent,) = _started(server, repo, "recent")
    finished(server, recent)
    _started(server, repo, "new")
    assert not store.path(old).exists() and store.path(recent).exists()
    assert {e["job_id"]: e.get("via") for e in ledger.read(store.root)} == {old: "gc"}
