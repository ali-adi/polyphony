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
