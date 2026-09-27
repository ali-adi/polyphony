"""apply_many: several jobs pre-checked together, then applied in order, or none."""

import json
import subprocess

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from polyphony import ledger
from polyphony.config import ProjectConfig
from polyphony.executors import BaseExecutor
from polyphony.jobs import JobError, JobNotFound, apply, apply_many, create_job
from polyphony.server import build_server
from polyphony.worker import run

LINES = "".join(f"line {i}\n" for i in range(1, 31))


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class ShellExecutor(BaseExecutor):
    """Runs the instruction as a shell script, so a test decides what 'the agent' does."""

    name = "shell"

    def find_binary(self):
        return "/bin/sh"

    def build_argv(self, instruction, mode, cwd, model=None):
        return ["/bin/sh", "-c", instruction]


def _done(store, repo, script):
    job = create_job(store, project=ProjectConfig(name="demo", path=repo),
                     instruction=script, executor="shell", mode="code")
    run(store.path(job.id), executors={"shell": ShellExecutor})
    job = store.load(job.id)
    assert job.state == "succeeded", job.error
    return job


@pytest.fixture
def lines(repo):
    """A committed 30-line file, so two jobs can edit it far enough apart."""
    (repo / "lines.txt").write_text(LINES)
    _git("add", "lines.txt", cwd=repo)
    _git("commit", "-q", "-m", "lines", cwd=repo)
    return repo / "lines.txt"


def _state(repo):
    """Everything apply could change: HEAD, the index, and the working tree."""
    return (
        _git("rev-parse", "HEAD", cwd=repo),
        _git("ls-files", "-s", cwd=repo),
        _git("status", "--porcelain", "--untracked-files=all", cwd=repo),
        {p.name: p.read_text() for p in repo.iterdir() if p.is_file()},
    )


def test_disjoint_jobs_apply_together(store, repo):
    a = _done(store, repo, "echo a > a.txt")
    b = _done(store, repo, "echo 'x = 2' > app.py")
    result = apply_many(store, [a.id, b.id])
    assert result == {"applied": [a.id, b.id], "not_applied": [], "overlaps": {},
                      "unstaged": [], "dry_run": False, "error": None}
    assert _git("diff", "--cached", "--name-only", cwd=repo).split() == ["a.txt", "app.py"]
    assert (repo / "app.py").read_text() == "x = 2\n"
    assert store.load(a.id).applied_paths == ["a.txt"]
    assert {e["job_id"]: e["outcome"] for e in ledger.read(store.root)} == {
        a.id: "applied", b.id: "applied"}


def test_compatible_edits_to_one_file_both_apply_and_are_reported(store, repo, lines):
    a = _done(store, repo, "sed -i.bak 's/^line 2$/line two/' lines.txt && rm lines.txt.bak")
    b = _done(store, repo, "sed -i.bak 's/^line 28$/line 28!/' lines.txt && rm lines.txt.bak")
    result = apply_many(store, [a.id, b.id])
    assert result["error"] is None
    assert result["applied"] == [a.id, b.id]
    assert result["overlaps"] == {"lines.txt": [a.id, b.id]}
    text = lines.read_text()
    assert "line two\n" in text and "line 28!\n" in text
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "lines.txt"


def test_conflicting_jobs_apply_none_and_name_the_second(store, repo):
    a = _done(store, repo, "echo 'x = 2' > app.py")
    b = _done(store, repo, "echo 'x = 3' > app.py")
    c = _done(store, repo, "echo c > c.txt")
    before = _state(repo)
    result = apply_many(store, [a.id, b.id, c.id])
    assert result["applied"] == []
    assert result["not_applied"] == [a.id, b.id, c.id]
    assert result["overlaps"] == {"app.py": [a.id, b.id]}
    assert result["error"].startswith(f"Job {b.id} does not apply cleanly on top of job(s) {a.id}")
    assert "app.py" in result["error"]
    assert _state(repo) == before
    assert all(not store.load(j.id).applied for j in (a, b, c))
    assert ledger.read(store.root) == []


def test_a_job_that_no_longer_fits_the_repository_is_named(store, repo):
    a = _done(store, repo, "echo a > a.txt")
    b = _done(store, repo, "echo 'x = 2' > app.py")
    (repo / "app.py").write_text("x = 3\n")
    _git("commit", "-q", "-am", "meanwhile", cwd=repo)
    before = _state(repo)
    result = apply_many(store, [a.id, b.id])
    assert result["error"].startswith(f"Job {b.id} does not apply cleanly on top of job(s) {a.id}")
    assert _state(repo) == before


def test_dry_run_reports_and_changes_nothing(store, repo, lines):
    a = _done(store, repo, "sed -i.bak 's/^line 2$/line two/' lines.txt && rm lines.txt.bak")
    b = _done(store, repo, "sed -i.bak 's/^line 28$/line 28!/' lines.txt && rm lines.txt.bak")
    objects = sorted(p.name for p in (repo / ".git" / "objects").rglob("*"))
    before = _state(repo)
    result = apply_many(store, [a.id, b.id], dry_run=True)
    assert result == {"applied": [], "not_applied": [a.id, b.id],
                      "overlaps": {"lines.txt": [a.id, b.id]}, "unstaged": [],
                      "dry_run": True, "error": None}
    assert _state(repo) == before
    # The pre-check writes its blobs elsewhere, not into the repository.
    assert sorted(p.name for p in (repo / ".git" / "objects").rglob("*")) == objects
    assert not store.load(a.id).applied and store.load(a.id).outcome is None
    assert [p.name for p in store.root.iterdir() if p.name.startswith("apply-many")] == []
    assert apply_many(store, [a.id, b.id])["applied"] == [a.id, b.id]


def test_a_job_over_unstaged_edits_is_reported_and_lands_unstaged(store, repo, lines):
    a = _done(store, repo, "echo a > a.txt")
    b = _done(store, repo, "sed -i.bak 's/^line 28$/line 28!/' lines.txt && rm lines.txt.bak")
    lines.write_text(LINES.replace("line 2\n", "line 2 (mine)\n"))
    assert apply_many(store, [a.id, b.id], dry_run=True)["unstaged"] == [b.id]
    result = apply_many(store, [a.id, b.id])
    assert result["applied"] == [a.id, b.id]
    assert result["unstaged"] == [b.id]
    assert store.load(b.id).applied_unstaged and not store.load(a.id).applied_unstaged
    assert _git("diff", "--cached", "--name-only", cwd=repo) == "a.txt"
    assert "line 2 (mine)\n" in lines.read_text() and "line 28!\n" in lines.read_text()


def test_a_job_after_an_unstaged_one_on_the_same_file_is_unstaged_too(store, repo, lines):
    lines.write_text(LINES.replace("line 2\n", "line 2 (mine)\n"))
    a = _done(store, repo, "sed -i.bak 's/^line 15$/line 15!/' lines.txt && rm lines.txt.bak")
    b = _done(store, repo, "sed -i.bak 's/^line 28$/line 28!/' lines.txt && rm lines.txt.bak")
    assert apply_many(store, [a.id, b.id], dry_run=True)["unstaged"] == [a.id, b.id]
    assert apply_many(store, [a.id, b.id])["unstaged"] == [a.id, b.id]


def test_a_new_file_over_an_untracked_one_is_refused(store, repo):
    a = _done(store, repo, "echo theirs > new.txt")
    (repo / "new.txt").write_text("mine\n")
    result = apply_many(store, [a.id])
    assert result["error"].startswith(f"Job {a.id} does not apply cleanly to the repository")
    assert (repo / "new.txt").read_text() == "mine\n"


def test_a_failure_after_the_pre_check_stops_and_says_what_landed(store, repo, monkeypatch):
    import polyphony.jobs as jobs
    a = _done(store, repo, "echo a > a.txt")
    b = _done(store, repo, "echo b > b.txt")
    c = _done(store, repo, "echo c > c.txt")

    def apply_then_meddle(store, job_id, paths=None):
        if job_id == b.id:
            (repo / "b.txt").write_text("someone else\n")
        return apply(store, job_id, paths)

    monkeypatch.setattr(jobs, "apply", apply_then_meddle)
    result = apply_many(store, [a.id, b.id, c.id])
    assert result["applied"] == [a.id]
    assert result["not_applied"] == [b.id, c.id]
    assert result["error"].startswith(f"Stopped at job {b.id}")
    assert not (repo / "c.txt").exists()


def test_renames_count_both_sides_as_touched(store, repo):
    a = _done(store, repo, "git mv app.py main.py")
    b = _done(store, repo, "echo 'x = 2' > app.py")
    result = apply_many(store, [a.id, b.id], dry_run=True)
    assert result["overlaps"] == {"app.py": [a.id, b.id]}
    assert result["error"].startswith(f"Job {b.id}")


@pytest.mark.parametrize("ids, match", [
    ([], "at least one"),
    (["x", "x"], "more than once: x"),
])
def test_bad_job_lists_are_refused(store, ids, match):
    with pytest.raises(ValueError, match=match):
        apply_many(store, ids)


def test_every_job_is_validated_before_anything_changes(store, repo, tmp_path):
    good = _done(store, repo, "echo a > a.txt")
    failed = create_job(store, project=ProjectConfig(name="demo", path=repo),
                        instruction="exit 1", executor="shell", mode="code")
    run(store.path(failed.id), executors={"shell": ShellExecutor})
    empty = _done(store, repo, "true")
    partial = _done(store, repo, "echo p > p.txt && echo q > q.txt")
    apply(store, partial.id, paths=["p.txt"])
    before = _state(repo)

    with pytest.raises(JobNotFound):
        apply_many(store, [good.id, "nope"])
    with pytest.raises(JobError, match=f"Job {failed.id} failed"):
        apply_many(store, [good.id, failed.id])
    with pytest.raises(JobError, match=f"Job {empty.id} changed nothing"):
        apply_many(store, [good.id, empty.id])
    with pytest.raises(JobError, match=f"Job {partial.id} is already partly applied.*Use apply"):
        apply_many(store, [good.id, partial.id])

    other = tmp_path / "other"
    other.mkdir()
    _git("init", "-q", "-b", "main", cwd=other)
    (other / "f").write_text("f\n")
    _git("add", "f", cwd=other)
    _git("-c", "user.name=T", "-c", "user.email=t@e", "commit", "-q", "-m", "i", cwd=other)
    elsewhere = _done(store, other, "echo o > o.txt")
    with pytest.raises(JobError, match="different repositories"):
        apply_many(store, [good.id, elsewhere.id])

    assert _state(repo) == before
    assert not store.load(good.id).applied



def test_a_report_job_is_refused_before_anything_changes(store, repo):
    """apply refuses a report job, so apply_many must refuse it up front rather
    than apply the jobs before it and stop there."""
    good = _done(store, repo, "echo a > a.txt")
    report = create_job(store, project=ProjectConfig(name="demo", path=repo),
                        instruction="echo findings > REPORT.md; exit 0", executor="shell",
                        mode="report")
    run(store.path(report.id), executors={"shell": ShellExecutor})
    assert store.load(report.id).state == "succeeded"
    before = _state(repo)
    with pytest.raises(JobError, match=f"Job {report.id} is a report job"):
        apply_many(store, [good.id, report.id])
    assert _state(repo) == before
    assert not store.load(good.id).applied

# --- The tool ---


def _call(server, tool, **args):
    result = anyio.run(server.call_tool, tool, args)
    return json.loads(result.content[0].text)


def test_the_tool_applies_a_fan_out_and_refuses_readably(store, repo, fake_agy, wait_for):
    server = build_server(store=store, projects_dir=repo.parent / "no-projects",
                          usage_check=lambda names=None: [])
    ids = []
    for name in ("one", "two"):
        fake_agy(f"echo {name} > {name}.txt")
        job_id = _call(server, "delegate", instruction="x", repo=str(repo),
                       executor="agy")["job_id"]
        wait_for(store, job_id, ("succeeded",))
        ids.append(job_id)

    report = _call(server, "apply_many", job_ids=ids, dry_run=True)
    assert report["dry_run"] and report["error"] is None and report["applied"] == []
    result = _call(server, "apply_many", job_ids=ids)
    assert result["applied"] == ids
    assert _git("diff", "--cached", "--name-only", cwd=repo).split() == ["one.txt", "two.txt"]

    with pytest.raises(ToolError, match=f"Job {ids[0]} is already applied") as e:
        _call(server, "apply_many", job_ids=ids)
    assert e.type is ToolError


# --- applyrobust lane ---


def _tree(repo):
    """Every file under the repository outside .git, with its bytes."""
    return {str(p.relative_to(repo)): p.read_bytes()
            for p in sorted(repo.rglob("*")) if p.is_file() and ".git" not in p.parts}


def _dir_to_file(store, repo, wip):
    """A job that replaces directory d with a file, over an ignored d/cache.pyc
    that keeps the directory from going, so git apply fails part way through."""
    (repo / "d").mkdir()
    (repo / "d" / "a.txt").write_text("a\n")
    (repo / ".gitignore").write_text("env/\ndata/\n*.pyc\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "d", cwd=repo)
    if wip:
        (repo / "app.py").write_text("x = 1\n# precious unstaged work\n")
    (repo / "d" / "cache.pyc").write_text("ignored\n")
    return _done(store, repo, "rm -rf d && echo file > d && echo 'y = 2' >> app.py")


@pytest.mark.parametrize("wip", [True, False], ids=["unstaged", "staged"])
def test_a_failed_apply_puts_back_what_git_removed_before_failing(store, repo, wip):
    # git apply removes the files it rewrites before writing any. When writing
    # d fails, app.py (with wip, an unstaged edit that exists nowhere else) and
    # d/a.txt must not stay deleted.
    job = _dir_to_file(store, repo, wip)
    before, files = _state(repo), _tree(repo)
    with pytest.raises(JobError, match="nothing was changed"):
        apply(store, job.id)
    assert (_state(repo), _tree(repo)) == (before, files)
    assert not store.load(job.id).applied


def test_a_dry_run_in_a_split_index_repository_writes_nothing_to_git(store, repo):
    _git("config", "core.splitIndex", "true", cwd=repo)
    _git("config", "splitIndex.sharedIndexExpire", "now", cwd=repo)
    _git("update-index", "--split-index", cwd=repo)
    a = _done(store, repo, "echo 'x = 2' > app.py")
    b = _done(store, repo, "echo c > c.py")
    git_dir = repo / ".git"
    before = {str(p): p.read_bytes() for p in git_dir.rglob("*") if p.is_file()}
    result = apply_many(store, [a.id, b.id], dry_run=True)
    assert result["error"] is None
    after = {str(p): p.read_bytes() for p in git_dir.rglob("*") if p.is_file()}
    assert after == before
    _git("status", cwd=repo)  # the shared index the real one needs is still there


def test_a_directory_replaced_by_a_file_passes_the_pre_check(store, repo):
    (repo / "d").mkdir()
    (repo / "d" / "a.txt").write_text("a\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "d", cwd=repo)
    job = _done(store, repo, "rm -rf d && echo file > d")
    assert apply_many(store, [job.id], dry_run=True)["error"] is None
    result = apply_many(store, [job.id])
    assert result["error"] is None and result["unstaged"] == []
    assert (repo / "d").read_text() == "file\n"


def test_a_file_touched_but_unchanged_is_staged_as_the_dry_run_says(store, repo):
    import os
    job = _done(store, repo, "echo 'x = 2' > app.py")
    stat = (repo / "app.py").stat()
    os.utime(repo / "app.py", ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert apply_many(store, [job.id], dry_run=True)["unstaged"] == []
    result = apply_many(store, [job.id])
    assert result["unstaged"] == []
    assert _git("status", "--porcelain", cwd=repo) == "M  app.py"


def test_a_locked_index_is_reported_not_taken_for_unstaged_edits(store, repo):
    job = _done(store, repo, "echo new > new.txt")
    (repo / ".git" / "index.lock").write_text("")
    with pytest.raises(JobError, match="index.lock"):
        apply(store, job.id)
    (repo / ".git" / "index.lock").unlink()
    assert not (repo / "new.txt").exists()
    assert not store.load(job.id).applied


def test_a_moved_repository_is_a_readable_refusal(store, repo):
    a = _done(store, repo, "echo a > a.txt")
    repo.rename(repo.with_name("moved"))
    with pytest.raises(JobError, match="no longer exists"):
        apply(store, a.id)
    with pytest.raises(JobError, match="no longer exists"):
        apply_many(store, [a.id])
