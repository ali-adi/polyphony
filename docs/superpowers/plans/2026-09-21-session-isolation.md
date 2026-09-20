# Polyphony Session (Isolation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every task an isolated, fully-provisioned git worktree outside the target repository, with an irreversible-action block and a hand-back that leaves the user in control of what lands.

**Architecture:** A `Workspace` owns one task's blast radius: create a worktree at `~/.polyphony/worktrees/<project>/<task-id>/` off a fresh branch, materialize the gitignored paths the project declares, and hand back a squash-merge command rather than merging anything itself. `git push` is refused at the subprocess layer. This single boundary is what lets Plan 4 delete `policy.py`, `rollback.py`, the approval flow, the temp-checkpoint commits, and most of `safety.py`.

**Tech Stack:** Python 3.11+, pytest 9.1.1 (venv), pydantic 2, `subprocess`, git worktrees, APFS copy-on-write (`cp -Rc`).

**Spec:** `docs/superpowers/specs/2026-09-21-polyphony-redesign-design.md` (§1 "Session — isolation")

**Evidence:** `docs/superpowers/plans/2026-09-21-provisioning-spike.md` — the provisioning design in this plan is verified, not assumed.

## Global Constraints

- Python `>=3.11`. Dependencies limited to `click>=8.1.0`, `pydantic>=2.0.0`, `pyyaml>=6.0.0`; dev adds `pytest>=8.0.0`. **Do not add new dependencies.**
- **Never write AI attribution into a commit** — no `Co-Authored-By`, no "Generated with". A repo hook blocks these and the commit will fail.
- **Never run** `git push`, `git merge`, `git reset --hard`, or `git clean`. Work on the current branch (`redesign-spec`) only.
- Baseline is **242 passed, 3 deselected**; verify with `.venv/bin/python -m pytest -q`.
- **Every test in this plan operates on a scratch repo in `tmp_path`.** No task here touches the user's real repositories. Task 7 is the sole exception and carries its own gate.
- Commit with an explicit pathspec (`git commit -m "..." -- <files>`), never the bare index.
- Verified platform facts (spike, 2026-09-21) — treat as ground truth:
  - `cp -Rc` (APFS copy-on-write) clones a 73M virtualenv in **0.71s** and consumes no additional disk until written.
  - A cloned virtualenv is self-contained: `sys.prefix` and `sys.executable` resolve to the clone, because `pyvenv.cfg` travels with it.
  - A fresh worktree contains **only tracked files**. medicoder's `env/` is gitignored, so its test command cannot start without provisioning.

---

## File Structure

| File | Responsibility |
|---|---|
| `orchestrator/workspace.py` (create) | `Workspace` — worktree lifecycle, provisioning, hand-back. The whole isolation boundary in one module. |
| `orchestrator/guard.py` (create) | `run_git()` — the only sanctioned way to spawn git; refuses `push`. |
| `tests/test_workspace.py` (create) | Worktree create/remove/provision against scratch repos. |
| `tests/test_guard.py` (create) | Push refusal, including evasion attempts. |
| `orchestrator/cli.py` (modify) | `polyphony workspace` command group. |

**Why one `Workspace` module:** worktree creation, provisioning, and teardown always change together — a new provisioning mode affects create and teardown alike. Splitting them across files would scatter one lifecycle. `guard.py` is separate because it is a process-spawn policy that other modules will also need.

---

## Task 1: Refuse `git push` at the subprocess layer

**Files:**
- Create: `orchestrator/guard.py`
- Test: `tests/test_guard.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `orchestrator.guard.ForbiddenGitCommand(Exception)`
  - `orchestrator.guard.run_git(args: list[str], cwd: str, timeout: int = 30) -> subprocess.CompletedProcess` — raises `ForbiddenGitCommand` before spawning anything if `args` resolve to a push.

Every later task spawns git through `run_git`, never `subprocess.run(["git", ...])` directly.

**Context.** `push` is the one git operation with irreversible public consequence. The spec requires blocking it structurally rather than by pattern-matching an agent's natural-language instruction, which is defeatable. Note `git` accepts flags before the subcommand (`git -C /path push`, `git --no-pager push`), and some take a value (`-C <path>`, `-c <cfg>`), so the subcommand must be located by skipping flags, not by reading `args[0]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_guard.py`:

```python
"""The subprocess-level git guard."""

import subprocess

import pytest

from orchestrator.guard import ForbiddenGitCommand, run_git


def test_plain_push_is_refused(tmp_path):
    with pytest.raises(ForbiddenGitCommand):
        run_git(["push"], cwd=str(tmp_path))


def test_push_behind_global_flags_is_refused(tmp_path):
    for args in (
        ["--no-pager", "push"],
        ["-C", "/somewhere", "push"],
        ["-c", "user.name=x", "push", "origin", "main"],
        ["--git-dir", "/x/.git", "push"],
    ):
        with pytest.raises(ForbiddenGitCommand):
            run_git(args, cwd=str(tmp_path))


def test_push_is_refused_before_spawning(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: spawned.append(a))
    with pytest.raises(ForbiddenGitCommand):
        run_git(["push"], cwd=str(tmp_path))
    assert spawned == [], "guard must refuse before any process is created"


def test_ordinary_commands_pass_through(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    res = run_git(["status", "--porcelain"], cwd=str(tmp_path))
    assert res.returncode == 0


def test_words_containing_push_are_not_refused(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    # A branch named "pushover" is not a push.
    res = run_git(["branch", "--list", "pushover"], cwd=str(tmp_path))
    assert res.returncode == 0
```

The last test matters: a naive `"push" in args` substring check would refuse
legitimate commands.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.guard'`

- [ ] **Step 3: Implement the guard**

Create `orchestrator/guard.py`:

```python
"""The only sanctioned way to spawn git.

`push` is the one git operation with irreversible, outward-facing
consequence, so it is refused structurally — before a process exists —
rather than by inspecting an agent's instruction text, which is defeatable.
"""

from __future__ import annotations

import subprocess
from typing import List

# git flags that consume the following token as their value, so the
# subcommand cannot be the token immediately after them.
_FLAGS_WITH_VALUES = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix",
}

_FORBIDDEN_SUBCOMMANDS = {"push"}


class ForbiddenGitCommand(Exception):
    """Raised when a git invocation is refused by policy."""


def _subcommand(args: List[str]) -> str | None:
    """Find the git subcommand, skipping global flags and their values."""
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in _FLAGS_WITH_VALUES:
            i += 2
        elif tok.startswith("-"):
            i += 1
        else:
            return tok
    return None


def run_git(args: List[str], cwd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command, refusing forbidden subcommands before spawning."""
    sub = _subcommand(args)
    if sub in _FORBIDDEN_SUBCOMMANDS:
        raise ForbiddenGitCommand(
            f"Refused: 'git {sub}' is blocked by Polyphony. Publishing work is "
            f"the operator's decision, not the orchestrator's."
        )
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_guard.py -q`
Expected: `5 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `247 passed, 3 deselected`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: refuse git push at the subprocess layer

Locates the subcommand by skipping global flags and their values, so
'git -C /path push' and '--no-pager push' are caught, while a branch
named 'pushover' is not." -- orchestrator/guard.py tests/test_guard.py
```

---

## Task 2: Create and remove worktrees outside the repo

**Files:**
- Create: `orchestrator/workspace.py`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: `orchestrator.guard.run_git`.
- Produces:
  - `orchestrator.workspace.Workspace` — a dataclass with fields `task_id: str`, `project: str`, `repo: Path`, `path: Path`, `branch: str`.
  - `Workspace.create(project: str, task_id: str, repo: str | Path, root: Path | None = None) -> Workspace` (classmethod)
  - `Workspace.remove(delete_branch: bool = True) -> None`
  - `orchestrator.workspace.DEFAULT_ROOT` — `Path.home() / ".polyphony"`

**Context.** The old `orchestrator/worktrees.py:72` placed worktrees at
`repo_dir / ".polyphony" / "worktrees"` — **inside** the target repo. That
leaves untracked directories in the working tree, and an agent running
`git add -A` could commit an entire second copy of the repository into itself.
Worktrees must live outside the repo so the target's `git status` stays clean
at all times.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workspace.py`:

```python
"""Worktree lifecycle for task isolation."""

import subprocess
from pathlib import Path

import pytest

from orchestrator.workspace import Workspace


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one commit and a gitignored env/ directory."""
    r = tmp_path / "proj"
    (r / "src").mkdir(parents=True)
    (r / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (r / ".gitignore").write_text("env/\n", encoding="utf-8")
    (r / "env" / "bin").mkdir(parents=True)
    (r / "env" / "bin" / "marker").write_text("venv\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        cwd=r, check=True,
    )
    return r


def test_worktree_is_created_outside_the_repo(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    assert ws.path.exists()
    assert repo not in ws.path.parents, "worktree must not live inside the target repo"
    assert (ws.path / "src" / "app.py").exists()


def test_target_repo_stays_clean(repo, tmp_path):
    Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    res = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    )
    assert res.stdout.strip() == "", f"target repo dirtied: {res.stdout!r}"


def test_gitignored_paths_are_absent_before_provisioning(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    assert not (ws.path / "env").exists(), "a fresh worktree has only tracked files"


def test_branch_is_namespaced_by_task(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    assert ws.branch == "polyphony/task-abc"


def test_remove_leaves_no_trace(repo, tmp_path):
    ws = Workspace.create("proj", "task-abc", repo, root=tmp_path / "poly")
    ws.remove()
    assert not ws.path.exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "polyphony/task-abc"],
        cwd=repo, capture_output=True, text=True,
    )
    assert branches.stdout.strip() == "", "branch should be deleted on removal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.workspace'`

- [ ] **Step 3: Implement create and remove**

Create `orchestrator/workspace.py`:

```python
"""One task's isolated workspace: a provisioned git worktree outside the repo.

Worktrees deliberately live outside the target repository. Placing them
inside leaves untracked directories in the working tree, where an agent
running `git add -A` could commit a second copy of the repo into itself.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from orchestrator.guard import run_git

DEFAULT_ROOT = Path.home() / ".polyphony"


@dataclass
class Workspace:
    task_id: str
    project: str
    repo: Path
    path: Path
    branch: str

    @classmethod
    def create(
        cls,
        project: str,
        task_id: str,
        repo: str | Path,
        root: Path | None = None,
    ) -> "Workspace":
        repo_path = Path(repo).resolve()
        base = Path(root) if root is not None else DEFAULT_ROOT
        wt_path = base / "worktrees" / project / task_id
        branch = f"polyphony/{task_id}"

        wt_path.parent.mkdir(parents=True, exist_ok=True)

        res = run_git(["worktree", "add", "-b", branch, str(wt_path)], cwd=str(repo_path))
        if res.returncode != 0:
            raise RuntimeError(
                f"Could not create worktree for {task_id} at {wt_path}: {res.stderr.strip()}"
            )

        return cls(
            task_id=task_id,
            project=project,
            repo=repo_path,
            path=wt_path,
            branch=branch,
        )

    def remove(self, delete_branch: bool = True) -> None:
        """Remove the worktree and, by default, its branch — leaving no trace."""
        run_git(["worktree", "remove", "--force", str(self.path)], cwd=str(self.repo))
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        if delete_branch:
            run_git(["branch", "-D", self.branch], cwd=str(self.repo))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: `5 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `252 passed, 3 deselected`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: create task worktrees outside the target repository

The previous implementation placed worktrees inside the repo, leaving
untracked directories an agent's 'git add -A' could commit as a second
copy of the repository." -- orchestrator/workspace.py tests/test_workspace.py
```

---

## Task 3: Provision gitignored paths into the worktree

**Files:**
- Modify: `orchestrator/workspace.py`
- Test: `tests/test_workspace.py` (append)

**Interfaces:**
- Consumes: `Workspace` from Task 2.
- Produces:
  - `orchestrator.workspace.ProvisionError(Exception)`
  - `Workspace.provision(entries: list[dict]) -> list[str]` — each entry is `{"path": str, "mode": "clone" | "link"}`. Returns the provisioned paths. Raises `ProvisionError` on any failure.

**Context — verified, not assumed.** See `2026-09-21-provisioning-spike.md`.
A fresh worktree contains only tracked files, so a project's gitignored
virtualenv and datasets are absent and its test command cannot start.
`cp -Rc` (APFS copy-on-write) clones medicoder's 73M `env/` in 0.71s with no
real disk cost, and the clone is self-contained — `sys.prefix` resolves to the
clone because `pyvenv.cfg` travels with it.

**Provisioning failure is fatal.** The spike showed why: with `env/` cloned but
`datasets/smoke/` missing, 613 tests ran and one failed with
`FileNotFoundError: datasets/smoke/0.json` — a plausible-looking failure with
nothing to do with the agent's work. A partially-provisioned workspace sends
the lead reasoner chasing a phantom bug.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workspace.py`:

```python
from orchestrator.workspace import ProvisionError


def test_clone_mode_materializes_a_gitignored_path(repo, tmp_path):
    ws = Workspace.create("proj", "task-p1", repo, root=tmp_path / "poly")
    ws.provision([{"path": "env/", "mode": "clone"}])
    assert (ws.path / "env" / "bin" / "marker").exists()


def test_clone_is_a_copy_not_a_link(repo, tmp_path):
    ws = Workspace.create("proj", "task-p2", repo, root=tmp_path / "poly")
    ws.provision([{"path": "env/", "mode": "clone"}])
    marker = ws.path / "env" / "bin" / "marker"
    assert not marker.is_symlink()
    marker.write_text("changed in worktree\n", encoding="utf-8")
    original = repo / "env" / "bin" / "marker"
    assert original.read_text(encoding="utf-8") == "venv\n", (
        "a clone must not write through to the source"
    )


def test_link_mode_creates_a_symlink(repo, tmp_path):
    ws = Workspace.create("proj", "task-p3", repo, root=tmp_path / "poly")
    ws.provision([{"path": "env/", "mode": "link"}])
    assert (ws.path / "env").is_symlink()


def test_missing_source_path_is_fatal(repo, tmp_path):
    ws = Workspace.create("proj", "task-p4", repo, root=tmp_path / "poly")
    with pytest.raises(ProvisionError) as exc:
        ws.provision([{"path": "does_not_exist/", "mode": "clone"}])
    assert "does_not_exist" in str(exc.value)


def test_escaping_paths_are_refused(repo, tmp_path):
    ws = Workspace.create("proj", "task-p5", repo, root=tmp_path / "poly")
    for bad in ("../outside", "/etc"):
        with pytest.raises(ProvisionError):
            ws.provision([{"path": bad, "mode": "clone"}])
```

The clone-is-not-a-link test is the important one: it proves the isolation
boundary holds, which is the entire justification for deleting the rollback
and checkpoint machinery in Plan 4.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: FAIL — `ImportError: cannot import name 'ProvisionError'`

- [ ] **Step 3: Implement provisioning**

In `orchestrator/workspace.py`, add `subprocess` to the imports, then add this
exception beside `DEFAULT_ROOT`:

```python
class ProvisionError(Exception):
    """Raised when a workspace cannot be fully provisioned.

    Always fatal. A partially provisioned workspace produces test failures
    unrelated to the agent's work, which the orchestrator would then treat
    as real regressions.
    """
```

and add this method to `Workspace`:

```python
    def provision(self, entries: list[dict]) -> list[str]:
        """Materialize gitignored paths the project declares it needs.

        `clone` uses APFS copy-on-write: near-instant, no disk cost until
        written, and genuinely isolated. `link` symlinks instead — it is a
        hole in the isolation boundary, since writes reach the real path,
        and exists only for paths too large to clone.
        """
        provisioned: list[str] = []
        for entry in entries:
            rel = str(entry.get("path", "")).strip()
            mode = str(entry.get("mode", "clone")).strip()

            if not rel:
                raise ProvisionError("Provision entry is missing a 'path'.")
            if rel.startswith("/") or ".." in Path(rel).parts:
                raise ProvisionError(
                    f"Refusing to provision {rel!r}: paths must be relative to the repo root."
                )

            src = (self.repo / rel).resolve()
            dst = (self.path / rel).resolve()

            if not src.exists():
                raise ProvisionError(
                    f"Cannot provision {rel!r}: {src} does not exist in {self.repo}."
                )

            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                raise ProvisionError(f"Cannot provision {rel!r}: {dst} already exists.")

            if mode == "link":
                dst.symlink_to(src)
            elif mode == "clone":
                res = subprocess.run(
                    ["cp", "-Rc", str(src), str(dst)],
                    capture_output=True, text=True,
                )
                if res.returncode != 0:
                    # -c (clonefile) needs APFS; fall back to a plain recursive copy.
                    res = subprocess.run(
                        ["cp", "-R", str(src), str(dst)],
                        capture_output=True, text=True,
                    )
                    if res.returncode != 0:
                        raise ProvisionError(
                            f"Cannot provision {rel!r}: {res.stderr.strip()}"
                        )
            else:
                raise ProvisionError(
                    f"Unknown provision mode {mode!r} for {rel!r}; expected 'clone' or 'link'."
                )

            provisioned.append(rel)
        return provisioned
```

The `cp -Rc` → `cp -R` fallback matters: copy-on-write is an APFS feature, and
this must still work on other filesystems, just without the speed and disk
savings.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: `10 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `257 passed, 3 deselected`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: provision gitignored paths into task worktrees

A fresh worktree has only tracked files, so a project's virtualenv and
datasets are absent and its test command cannot start. Clone mode uses
APFS copy-on-write; failures are fatal because a partially provisioned
workspace produces failures unrelated to the agent's work." -- orchestrator/workspace.py tests/test_workspace.py
```

---

## Task 4: Hand results back without merging

**Files:**
- Modify: `orchestrator/workspace.py`
- Test: `tests/test_workspace.py` (append)

**Interfaces:**
- Consumes: `Workspace` from Tasks 2–3.
- Produces:
  - `Workspace.diff_stat() -> str` — `git diff --stat` of the worktree branch against its base.
  - `Workspace.changed_files() -> list[str]`
  - `Workspace.handoff() -> str` — the operator-facing block naming the review, keep, and discard commands.

**Context.** Polyphony never merges, commits to the user's branches, or pushes.
It hands back a **squash**-merge command, because a plain `git merge` writes
the branch name into the merge commit (`Merge branch 'polyphony/task-a3f9'`)
and any agent-authored commit messages or `Co-Authored-By` trailers inside the
branch would become public history. Squashing collapses the work into one
commit the operator authors, so their public history shows no trace of how it
was produced.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workspace.py`:

```python
def _commit_in(ws, name: str, body: str):
    (ws.path / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=ws.path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-q", "-m", "agent work"],
        cwd=ws.path, check=True,
    )


def test_changed_files_lists_agent_edits(repo, tmp_path):
    ws = Workspace.create("proj", "task-h1", repo, root=tmp_path / "poly")
    _commit_in(ws, "new.py", "y = 2\n")
    assert "new.py" in ws.changed_files()


def test_handoff_offers_squash_not_plain_merge(repo, tmp_path):
    ws = Workspace.create("proj", "task-h2", repo, root=tmp_path / "poly")
    _commit_in(ws, "new.py", "y = 2\n")
    text = ws.handoff()
    assert "merge --squash polyphony/task-h2" in text
    assert "git merge polyphony" not in text, "a plain merge would leak the branch name"


def test_handoff_names_review_and_discard(repo, tmp_path):
    ws = Workspace.create("proj", "task-h3", repo, root=tmp_path / "poly")
    _commit_in(ws, "new.py", "y = 2\n")
    text = ws.handoff()
    assert str(ws.path) in text
    assert "clean" in text


def test_handoff_does_not_modify_the_target_repo(repo, tmp_path):
    ws = Workspace.create("proj", "task-h4", repo, root=tmp_path / "poly")
    _commit_in(ws, "new.py", "y = 2\n")
    ws.handoff()
    res = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    )
    assert res.stdout.strip() == ""
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=repo, capture_output=True, text=True
    )
    assert "agent work" not in log.stdout, "handoff must not land anything"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: FAIL — `AttributeError: 'Workspace' object has no attribute 'changed_files'`

- [ ] **Step 3: Implement the hand-back**

Add to `Workspace` in `orchestrator/workspace.py`:

```python
    def _base_ref(self) -> str:
        """The commit this worktree branched from."""
        res = run_git(["merge-base", "HEAD", self.branch], cwd=str(self.repo))
        return res.stdout.strip() or "HEAD"

    def changed_files(self) -> list[str]:
        """Files the agent changed, relative to the branch point."""
        res = run_git(
            ["diff", "--name-only", f"{self._base_ref()}..{self.branch}"],
            cwd=str(self.repo),
        )
        return [line for line in res.stdout.splitlines() if line.strip()]

    def diff_stat(self) -> str:
        res = run_git(
            ["diff", "--stat", f"{self._base_ref()}..{self.branch}"],
            cwd=str(self.repo),
        )
        return res.stdout.rstrip()

    def handoff(self) -> str:
        """The operator-facing block. Polyphony never lands work itself.

        Squash is offered rather than a plain merge: a merge commit would
        record the branch name, and agent-authored commit messages inside
        the branch would enter public history.
        """
        files = self.changed_files()
        summary = ", ".join(files[:4]) + ("…" if len(files) > 4 else "") if files else "none"
        return (
            f"  changed   {summary}\n"
            f"\n"
            f"  review    git -C {self.repo} diff {self._base_ref()}..{self.branch}\n"
            f"  worktree  {self.path}\n"
            f"  keep      git -C {self.repo} merge --squash {self.branch} && git -C {self.repo} commit\n"
            f"  discard   polyphony workspace clean {self.task_id}\n"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: `14 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `261 passed, 3 deselected`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: hand results back as a squash-merge the operator runs

Polyphony never merges, commits to the user's branches, or pushes. A
plain merge would write the polyphony branch name into the merge commit
and carry agent-authored messages into public history; squashing gives
the operator one commit they author themselves." -- orchestrator/workspace.py tests/test_workspace.py
```

---

## Task 5: Prune orphaned worktrees on startup

**Files:**
- Modify: `orchestrator/workspace.py`
- Test: `tests/test_workspace.py` (append)

**Interfaces:**
- Consumes: `Workspace`.
- Produces: `orchestrator.workspace.prune(repo: str | Path) -> None` — module-level function clearing worktree records whose directories no longer exist.

**Context.** An interrupted run leaves a worktree registered in
`.git/worktrees/` whose directory may be gone. Git then refuses to reuse that
path. Pruning at startup keeps repeated runs working without operator
intervention.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_workspace.py`:

```python
from orchestrator.workspace import prune


def test_prune_clears_orphaned_worktree_records(repo, tmp_path):
    ws = Workspace.create("proj", "task-orphan", repo, root=tmp_path / "poly")
    shutil.rmtree(ws.path)  # simulate an interrupted run

    prune(repo)

    listed = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True
    )
    assert "task-orphan" not in listed.stdout


def test_prune_leaves_live_worktrees_alone(repo, tmp_path):
    ws = Workspace.create("proj", "task-live", repo, root=tmp_path / "poly")
    prune(repo)
    assert ws.path.exists()
```

Add `import shutil` to the test file's imports if it is not already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: FAIL — `ImportError: cannot import name 'prune'`

- [ ] **Step 3: Implement prune**

Add to `orchestrator/workspace.py`, at module level below the `Workspace` class:

```python
def prune(repo: str | Path) -> None:
    """Clear worktree records whose directories are gone.

    An interrupted run leaves a registration behind, and git then refuses
    to reuse that path. Pruning at startup keeps repeat runs working.
    """
    run_git(["worktree", "prune"], cwd=str(Path(repo).resolve()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace.py -q`
Expected: `16 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `263 passed, 3 deselected`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: prune orphaned worktree records on startup" -- orchestrator/workspace.py tests/test_workspace.py
```

---

## Task 6: `polyphony workspace` CLI

**Files:**
- Modify: `orchestrator/cli.py`
- Test: `tests/test_workspace_cli.py` (create)

**Interfaces:**
- Consumes: `Workspace`, `prune`.
- Produces: CLI group `workspace` with `create <project> <task-id>`, `list`, and `clean <task-id>`.

**Context.** This makes the isolation boundary usable before the loop rewrite
exists, so it can be exercised by hand against a real repo — which is how the
remaining uncertainty gets retired.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workspace_cli.py`:

```python
"""The workspace CLI group."""

import subprocess

import pytest
from click.testing import CliRunner

from orchestrator.cli import cli


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    (r / "app.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        cwd=r, check=True,
    )
    return r


def test_workspace_create_reports_the_path(repo, tmp_path):
    result = CliRunner().invoke(
        cli,
        ["workspace", "create", "proj", "task-cli1",
         "--repo", str(repo), "--root", str(tmp_path / "poly")],
    )
    assert result.exit_code == 0, result.output
    assert "task-cli1" in result.output


def test_workspace_clean_removes_it(repo, tmp_path):
    root = str(tmp_path / "poly")
    CliRunner().invoke(
        cli, ["workspace", "create", "proj", "task-cli2", "--repo", str(repo), "--root", root]
    )
    result = CliRunner().invoke(
        cli, ["workspace", "clean", "task-cli2", "--repo", str(repo), "--root", root]
    )
    assert result.exit_code == 0, result.output
    branches = subprocess.run(
        ["git", "branch", "--list", "polyphony/task-cli2"],
        cwd=repo, capture_output=True, text=True,
    )
    assert branches.stdout.strip() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workspace_cli.py -q`
Expected: FAIL — exit code 2, "No such command 'workspace'"

- [ ] **Step 3: Add the command group**

In `orchestrator/cli.py`, add this group. Place it immediately after the
existing `project` group so related commands stay together:

```python
@cli.group()
def workspace():
    """Create, list, and clean isolated task workspaces."""


@workspace.command("create")
@click.argument("project")
@click.argument("task_id")
@click.option("--repo", required=True, help="Path to the target repository.")
@click.option("--root", default=None, help="Where workspaces live (default: ~/.polyphony).")
def workspace_create(project, task_id, repo, root):
    """Create a provisioned worktree for a task."""
    from pathlib import Path as _Path
    from orchestrator.workspace import Workspace, prune

    prune(repo)
    ws = Workspace.create(project, task_id, repo, root=_Path(root) if root else None)
    click.echo(f"workspace {task_id}")
    click.echo(f"  path    {ws.path}")
    click.echo(f"  branch  {ws.branch}")


@workspace.command("list")
@click.option("--repo", required=True, help="Path to the target repository.")
def workspace_list(repo):
    """List worktrees registered for a repository."""
    from orchestrator.guard import run_git

    res = run_git(["worktree", "list"], cwd=repo)
    click.echo(res.stdout.rstrip() or "No worktrees.")


@workspace.command("clean")
@click.argument("task_id")
@click.option("--repo", required=True, help="Path to the target repository.")
@click.option("--root", default=None, help="Where workspaces live (default: ~/.polyphony).")
def workspace_clean(task_id, repo, root):
    """Remove a task's worktree and its branch."""
    from pathlib import Path as _Path
    from orchestrator.workspace import DEFAULT_ROOT, Workspace

    base = _Path(root) if root else DEFAULT_ROOT
    repo_path = _Path(repo).resolve()
    # Reconstruct the handle; project name is not needed to remove by path.
    matches = list((base / "worktrees").glob(f"*/{task_id}"))
    if not matches:
        raise click.ClickException(f"No workspace found for task {task_id}.")
    ws = Workspace(
        task_id=task_id,
        project=matches[0].parent.name,
        repo=repo_path,
        path=matches[0],
        branch=f"polyphony/{task_id}",
    )
    ws.remove()
    click.echo(f"Removed workspace {task_id} and branch {ws.branch}.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workspace_cli.py -q`
Expected: `2 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `265 passed, 3 deselected`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: add polyphony workspace create/list/clean" -- orchestrator/cli.py tests/test_workspace_cli.py
```

---

## Task 7: First real worktree against medicoder — OPERATOR GATED

> **DO NOT RUN THIS TASK WITHOUT EXPLICIT OPERATOR APPROVAL.**
> Every other task in this plan operates on scratch repos in `tmp_path`. This
> one creates a real git worktree and branch in the operator's working
> repository. The operator raised repository cleanliness as a specific
> concern, and the spec records that the first real worktree creation should
> be watched. **Stop and ask before executing this task.**

**Files:**
- Modify: `projects/medicoder/project.yaml` (add the `worktree.provision` block)

**Interfaces:**
- Consumes: everything above.
- Produces: no code. The deliverable is evidence that the isolation boundary works against a real project.

**What this proves, and what it costs.** The provisioning spike simulated a
worktree with `git archive` and got 615 passing tests. It did not create a real
worktree, because that writes a branch ref into the repo. This task closes
that last gap. Its footprint is one local branch (`polyphony/verify-1`) and one
directory under `~/.polyphony/`, both removed in Step 5. **Nothing reaches the
remote** — `git push` is refused by `orchestrator/guard.py`.

- [ ] **Step 1: Declare the provision list**

In `projects/medicoder/project.yaml`, add a top-level block (keep every
existing key unchanged):

```yaml
worktree:
  provision:
    - { path: env/,             mode: clone }
    - { path: datasets/smoke/,  mode: clone }
    - { path: datasets/tuning/, mode: clone }
```

These three are exactly what the spike proved necessary and sufficient.
`database/` needs no entry — it is tracked, so each worktree gets its own copy.
`results/` (3.9G) is deliberately excluded.

- [ ] **Step 2: Create and provision a real workspace**

```bash
.venv/bin/python -c "
from orchestrator.workspace import Workspace, prune
import yaml, pathlib
repo = '/Users/ali/root/Work/Medicoder/medicoder/medicoder'
cfg = yaml.safe_load(open('projects/medicoder/project.yaml'))
prune(repo)
ws = Workspace.create('medicoder', 'verify-1', repo)
print('worktree:', ws.path)
print('provisioned:', ws.provision(cfg['worktree']['provision']))
"
```

- [ ] **Step 3: Confirm the target repo is untouched**

```bash
git -C /Users/ali/root/Work/Medicoder/medicoder/medicoder status --porcelain
```

Expected: **empty output.** If anything is listed, STOP and report — the
isolation boundary has failed and nothing further should run.

- [ ] **Step 4: Run medicoder's real test suite inside the workspace**

```bash
cd ~/.polyphony/worktrees/medicoder/verify-1 && env/bin/python -m unittest discover -s tests -t .
```

Expected: `Ran 615 tests ... OK (skipped=4)` — matching the spike exactly.

- [ ] **Step 5: Remove it and confirm no trace**

```bash
.venv/bin/python -c "
from orchestrator.workspace import Workspace
from pathlib import Path
ws = Workspace('verify-1', 'medicoder',
               Path('/Users/ali/root/Work/Medicoder/medicoder/medicoder'),
               Path.home()/'.polyphony'/'worktrees'/'medicoder'/'verify-1',
               'polyphony/verify-1')
ws.remove()
"
git -C /Users/ali/root/Work/Medicoder/medicoder/medicoder branch --list 'polyphony/*'
git -C /Users/ali/root/Work/Medicoder/medicoder/medicoder status --porcelain
```

Expected: both commands print nothing.

- [ ] **Step 6: Commit the config only**

```bash
git commit -m "chore: declare medicoder worktree provisioning

Verified end to end against a real worktree: 615 tests pass inside the
provisioned workspace, the target repo stays clean throughout, and
removal leaves no branch or directory behind." -- projects/medicoder/project.yaml
```

---

## Done criteria

- [ ] `.venv/bin/python -m pytest -q` → 265 passed, 3 deselected
- [ ] `git push` cannot be spawned through `orchestrator.guard.run_git`, including behind `-C` and `--no-pager`
- [ ] A worktree never lands inside the target repository
- [ ] The target repository's `git status` is clean before, during, and after a workspace's life
- [ ] A cloned provisioned path does not write through to its source
- [ ] Hand-back offers `merge --squash`, never a plain merge
- [ ] All commits on `redesign-spec`, none containing AI attribution

## What this plan deliberately does not do

- Does not touch `main.py` or the decision loop — that is the next plan.
- Does not delete `worktrees.py`, `rollback.py`, `policy.py`, or `safety.py`.
  They are superseded by this boundary but stay until the loop stops calling
  them, so nothing breaks mid-refactor.
- Does not implement the quota ledger or the event stream.

## Hand-off to the next plan

The loop rewrite consumes `Workspace` as the thing it runs inside: the loop
receives a provisioned workspace and its cwd, rather than the user's checkout.
`handoff()` becomes part of the completion summary.
