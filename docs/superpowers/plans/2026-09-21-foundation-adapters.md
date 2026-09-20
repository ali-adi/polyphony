# Polyphony Foundation (Adapters) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all three executor adapters demonstrably work against their real CLI binaries, with correct permission modes, so every later phase builds on verified behavior instead of assumed behavior.

**Architecture:** Replace the `read_only: bool` knob with an explicit `Mode` enum (`REVIEW` / `CODE`) defined once in `executors/base.py`. Each adapter maps that mode onto its own CLI's native permission flags, so the CLI enforces permissions instead of Polyphony bypassing them with `--dangerously-skip-permissions` and re-implementing a weaker check in Python. Add a `smoke` pytest marker for tests that spawn the real binaries; these are excluded from the default run because they consume subscription quota.

**Tech Stack:** Python 3.11+, pytest 9.1.1 (venv), pydantic 2, `subprocess`. External binaries: `claude`, `agy`, `cursor-agent`.

**Spec:** `docs/superpowers/specs/2026-09-21-polyphony-redesign-design.md` (§3 "Executors & the quota ledger")

## Global Constraints

- Python `>=3.11`. Dependencies limited to `click>=8.1.0`, `pydantic>=2.0.0`, `pyyaml>=6.0.0`; dev adds `pytest>=8.0.0`. **Do not add new dependencies.**
- **Never write AI attribution into a commit** — no `Co-Authored-By`, no "Generated with". A repo hook (`projects/medicoder/hooks/block-ai-attribution.sh`) blocks these and the commit will fail.
- **Never run** `git push`, `git merge`, `git reset --hard`, or `git clean`. Work on the current branch (`redesign-spec`) only.
- Existing tests must keep passing. Baseline is **219 passed**; verify with `.venv/bin/python -m pytest -q`.
- Smoke tests spawn real CLIs and consume real subscription quota. They must be **excluded from the default pytest run** and only run explicitly via `-m smoke`.
- Verified CLI facts (checked against installed binaries 2026-09-21) — treat as ground truth:
  - `claude`: `--permission-mode` accepts `acceptEdits|auto|bypassPermissions|manual|dontAsk|plan`; `--permission-prompts` accepts `host|none`; also has `-p`, `--output-format`, `--model`, `--resume`, `--system-prompt`, `--tools`, `--agents`.
  - `agy`: `--mode` accepts `accept-edits|plan`; also has `-p`, `--output-format`, `--model`, `--effort` (`low|medium|high`), `--json-schema`, `--conversation`, `--add-dir`, `--sandbox`.
  - `cursor-agent`: binary is named **`cursor-agent`** (not `cursor`), invoked as `cursor-agent -p`; `--mode` accepts `plan|ask`; also has `-f/--force`, `--sandbox enabled|disabled`, `--output-format`, `--model`, `--resume`, `--continue`.

---

## File Structure

| File | Responsibility |
|---|---|
| `executors/base.py` (modify) | Add `Mode` enum + `resolve_mode()` back-compat bridge. Existing `ExecutorResult` and change-detection helpers untouched. |
| `executors/claude_executor.py` (modify) | Map `Mode` → `--permission-mode` / `--permission-prompts`. Drop `--dangerously-skip-permissions`. |
| `executors/agy_executor.py` (modify) | Map `Mode` → `--mode` + `--sandbox`. Drop `--dangerously-skip-permissions`. |
| `executors/cursor_executor.py` (modify) | Fix binary discovery + invocation form. Map `Mode` → `--mode plan` / `-f --sandbox enabled`. |
| `tests/smoke/conftest.py` (create) | `scratch_repo` fixture — a real one-commit git repo in `tmp_path`. |
| `tests/smoke/test_adapter_smoke.py` (create) | One real-subprocess test per adapter. |
| `tests/test_executor_modes.py` (create) | Fast, no-subprocess tests asserting argv construction per mode. |
| `pyproject.toml` (modify) | Register `smoke` marker; deselect it by default. |

**Why `Mode` lives in `base.py`:** every adapter needs it and `base.py` is already the shared vocabulary module (`ExecutorResult`, `ExecutorStatus`). Adding a third shared type there follows the existing pattern rather than introducing a new module for one enum.

**Back-compat bridge:** `main.py` and `router.py` still pass `read_only=True/False` and are not rewritten until Plan 2. `resolve_mode()` accepts both so nothing breaks mid-refactor.

---

## Task 1: Smoke test infrastructure

**Files:**
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/conftest.py`
- Modify: `pyproject.toml` (the `[tool.pytest.ini_options]` block, currently the last block in the file)

**Interfaces:**
- Consumes: nothing.
- Produces: pytest fixture `scratch_repo` → `pathlib.Path` pointing at a real git repo with one commit and a file `hello.py`. Pytest marker `smoke`, deselected by default.

- [ ] **Step 1: Create the smoke test package**

Create `tests/smoke/__init__.py` as an empty file:

```python
```

(Yes — zero bytes. It exists only to make `tests/smoke` a package.)

- [ ] **Step 2: Write the scratch repo fixture**

Create `tests/smoke/conftest.py`:

```python
"""Fixtures for smoke tests that spawn real executor CLI binaries."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    """A real git repo with one commit, safe for an agent to modify."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    (repo / "hello.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c", "user.name=polyphony-test",
            "-c", "user.email=test@localhost",
            "commit", "-q", "-m", "init",
        ],
        cwd=repo,
        check=True,
    )
    return repo
```

- [ ] **Step 3: Register the smoke marker and deselect it by default**

In `pyproject.toml`, replace the entire `[tool.pytest.ini_options]` block with:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
norecursedirs = ["medicoder", "migration", ".venv", "env"]
markers = [
    "smoke: spawns real CLI binaries and consumes subscription quota (deselected by default; run with -m smoke)",
]
addopts = "-m 'not smoke'"
```

- [ ] **Step 4: Verify the fixture works and smoke is deselected**

The self-check must live in a real test file. pytest only collects test
functions from files matching `test_*.py` / `*_test.py`; it loads
`conftest.py` for fixtures but never scans it for tests, so a marked
function placed there would silently never run.

Create a temporary file `tests/smoke/test_selfcheck.py`:

```python
import pytest


@pytest.mark.smoke
def test_scratch_repo_is_a_real_git_repo(scratch_repo):
    assert (scratch_repo / "hello.py").exists()
    assert (scratch_repo / ".git").exists()
```

Run: `.venv/bin/python -m pytest tests/smoke -q`
Expected: `1 deselected` — proving `addopts = -m 'not smoke'` excludes it.

Run: `.venv/bin/python -m pytest tests/smoke -q -m smoke`
Expected: `1 passed` — proving the fixture builds a real repo **and** that a
command-line `-m` overrides the one in `addopts`.

Now delete the file:

```bash
rm tests/smoke/test_selfcheck.py
```

It has served its purpose; Task 6 adds the permanent smoke tests that use
this fixture.

- [ ] **Step 5: Verify the existing suite still passes**

Run: `.venv/bin/python -m pytest -q`
Expected: `219 passed`

- [ ] **Step 6: Commit**

```bash
git add tests/smoke/__init__.py tests/smoke/conftest.py pyproject.toml
git commit -m "test: add smoke test infrastructure with quota-consuming marker"
```

---

## Task 2: Mode enum and back-compat bridge

**Files:**
- Modify: `executors/base.py` (append after the `ExecutorStatus` enum, around line 90)
- Test: `tests/test_executor_modes.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `executors.base.Mode` — a `str, Enum` with members `REVIEW = "review"` and `CODE = "code"`.
  - `executors.base.resolve_mode(mode: Mode | str | None, read_only: bool = False) -> Mode` — returns `Mode.REVIEW` when `mode` is `REVIEW`/`"review"` **or** when `mode` is `None` and `read_only` is `True`; returns `Mode.CODE` otherwise. Raises `ValueError` on an unrecognized string.

Tasks 3, 4 and 5 all call `resolve_mode(kwargs.get("mode"), read_only)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_executor_modes.py`:

```python
"""Mode resolution and per-adapter argv construction."""

import pytest

from executors.base import Mode, resolve_mode


def test_explicit_mode_wins_over_read_only():
    assert resolve_mode(Mode.CODE, read_only=True) is Mode.CODE
    assert resolve_mode(Mode.REVIEW, read_only=False) is Mode.REVIEW


def test_string_modes_accepted():
    assert resolve_mode("review") is Mode.REVIEW
    assert resolve_mode("code") is Mode.CODE


def test_read_only_bridges_to_review_when_mode_absent():
    assert resolve_mode(None, read_only=True) is Mode.REVIEW


def test_defaults_to_code():
    assert resolve_mode(None, read_only=False) is Mode.CODE


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        resolve_mode("yolo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: FAIL — `ImportError: cannot import name 'Mode' from 'executors.base'`

- [ ] **Step 3: Implement Mode and resolve_mode**

In `executors/base.py`, insert immediately after the `ExecutorStatus` class (which ends with `CANCELLED = "CANCELLED"`):

```python
class Mode(str, Enum):
    """How much authority an executor is granted for a single invocation.

    REVIEW maps onto each CLI's native read-only/plan mode: the agent may
    read and reason but may not edit. CODE maps onto each CLI's
    accept-edits mode: edits proceed without an interactive prompt.
    """
    REVIEW = "review"
    CODE = "code"


def resolve_mode(mode: "Mode | str | None" = None, read_only: bool = False) -> Mode:
    """Resolve an explicit mode, falling back to the legacy read_only flag.

    Callers not yet migrated off `read_only=` keep working: read_only=True
    becomes REVIEW. An explicit `mode` always wins.
    """
    if mode is not None:
        if isinstance(mode, Mode):
            return mode
        try:
            return Mode(str(mode).strip().lower())
        except ValueError:
            raise ValueError(
                f"Unknown executor mode {mode!r}; expected one of: "
                f"{', '.join(m.value for m in Mode)}"
            ) from None
    return Mode.REVIEW if read_only else Mode.CODE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: `5 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `224 passed`

- [ ] **Step 6: Commit**

```bash
git add executors/base.py tests/test_executor_modes.py
git commit -m "feat: add executor Mode enum with read_only back-compat bridge"
```

---

## Task 3: Claude adapter permission modes

**Files:**
- Modify: `executors/claude_executor.py:112-152` (the `cmd` list construction and the `if read_only:` branch inside `execute`)
- Test: `tests/test_executor_modes.py` (append)

**Interfaces:**
- Consumes: `executors.base.Mode`, `executors.base.resolve_mode`.
- Produces: `ClaudeExecutor.build_argv(instruction_mode: Mode, model=None, session_id=None, output_format="text", system_prompt=None, subagents=None) -> list[str]` — a pure function returning the full argv. `execute()` calls it. Extracting it is what makes argv testable without spawning a process.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_executor_modes.py`:

```python
from executors.claude_executor import ClaudeExecutor


def test_claude_review_mode_is_plan_and_never_bypasses():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(Mode.REVIEW)
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "--permission-prompts" in argv
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "--dangerously-skip-permissions" not in argv


def test_claude_code_mode_accepts_edits_and_never_bypasses():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(Mode.CODE)
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--dangerously-skip-permissions" not in argv


def test_claude_argv_includes_print_flag_and_model():
    argv = ClaudeExecutor(binary_path="/bin/echo").build_argv(Mode.CODE, model="claude-sonnet-5")
    assert "-p" in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: FAIL — `AttributeError: 'ClaudeExecutor' object has no attribute 'build_argv'`

- [ ] **Step 3: Extract build_argv and remove the bypass flag**

In `executors/claude_executor.py`, add this method to `ClaudeExecutor` (place it directly above `execute`):

```python
    _MODE_FLAGS = {
        Mode.REVIEW: "plan",
        Mode.CODE: "acceptEdits",
    }

    def build_argv(
        self,
        instruction_mode: Mode,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        output_format: str = "text",
        system_prompt: Optional[str] = None,
        subagents: Optional[Any] = None,
    ) -> List[str]:
        """Construct the full claude argv for one invocation.

        Permissions are enforced by the CLI itself via --permission-mode.
        --permission-prompts=none makes anything that would prompt fail
        closed instead of hanging a non-interactive run forever.
        """
        cmd = [
            self.binary_path,
            "-p",
            "--permission-mode", self._MODE_FLAGS[instruction_mode],
            "--permission-prompts", "none",
        ]

        if session_id:
            cmd.extend(["--resume", str(session_id)])
        if model:
            cmd.extend(["--model", str(model)])
        if output_format and output_format != "text":
            cmd.extend(["--output-format", output_format])
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt, "--system-prompt-snapshot", "on"])

        if subagents:
            agents_json = None
            if hasattr(subagents, "to_claude_agents_json"):
                agents_json = subagents.to_claude_agents_json()
            elif isinstance(subagents, dict):
                agents_json = json.dumps(subagents)
            elif isinstance(subagents, str):
                agents_json = subagents
            if agents_json:
                cmd.extend(["--agents", agents_json])

        return cmd
```

Add `Mode` and `resolve_mode` to the existing import from `executors.base` at the top of the file:

```python
from executors.base import (
    BaseExecutor,
    ExecutorResult,
    Mode,
    resolve_mode,
    _get_changed_files_via_git as _base_get_changed_files_via_git,
    _snapshot_file_states as _base_snapshot_file_states,
    detect_changed_files as _base_detect_changed_files,
)
```

Then in `execute`, replace everything from `cmd = [` through the `if read_only:` branch (currently lines 112–151) with:

```python
        cmd = self.build_argv(
            instruction_mode=resolve_mode(kwargs.get("mode"), read_only),
            model=model,
            session_id=kwargs.get("session_id"),
            output_format=output_format,
            system_prompt=system_prompt,
            subagents=subagents,
        )
```

Leave the `env` / `MAX_THINKING_TOKENS` block and the `subprocess.run` call below it exactly as they are.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: `8 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `227 passed`

If `tests/test_executors.py` fails asserting `--dangerously-skip-permissions` is present, that assertion encoded the old behavior — update it to assert `--permission-mode` instead, and say so in the commit body.

- [ ] **Step 6: Commit**

```bash
git add executors/claude_executor.py tests/test_executor_modes.py
git commit -m "feat: use claude native permission modes instead of bypassing checks"
```

---

## Task 4: agy adapter permission modes

**Files:**
- Modify: `executors/agy_executor.py:92-121` (the `cmd` list construction and the `elif read_only:` branch)
- Test: `tests/test_executor_modes.py` (append)

**Interfaces:**
- Consumes: `executors.base.Mode`, `executors.base.resolve_mode`.
- Produces: `AgyExecutor.build_argv(instruction_mode: Mode, cwd: str, model=None, effort=None, session_id=None, output_format="text", json_schema=None, agent=None) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_executor_modes.py`:

```python
from executors.agy_executor import AgyExecutor


def test_agy_review_mode_is_plan_and_sandboxed():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(Mode.REVIEW, cwd="/tmp")
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_agy_code_mode_accepts_edits_and_sandboxed():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(Mode.CODE, cwd="/tmp")
    assert argv[argv.index("--mode") + 1] == "accept-edits"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv


def test_agy_passes_workspace_and_effort():
    argv = AgyExecutor(binary_path="/bin/echo").build_argv(
        Mode.CODE, cwd="/tmp/work", effort="high"
    )
    assert argv[argv.index("--add-dir") + 1] == "/tmp/work"
    assert argv[argv.index("--effort") + 1] == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: FAIL — `AttributeError: 'AgyExecutor' object has no attribute 'build_argv'`

- [ ] **Step 3: Implement build_argv**

In `executors/agy_executor.py`, add `Mode` and `resolve_mode` to the existing `from executors.base import (...)` block, then add this method directly above `execute`:

```python
    _MODE_FLAGS = {
        Mode.REVIEW: "plan",
        Mode.CODE: "accept-edits",
    }

    def build_argv(
        self,
        instruction_mode: Mode,
        cwd: str,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        session_id: Optional[str] = None,
        output_format: str = "text",
        json_schema: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> List[str]:
        """Construct the full agy argv for one invocation.

        --sandbox enables terminal restrictions; agy enforces the edit
        policy itself via --mode, so no permission bypass is needed.
        """
        cmd = [
            self.binary_path,
            "-p",
            "--input-format", "text",
            "--mode", self._MODE_FLAGS[instruction_mode],
            "--sandbox",
            "--add-dir", cwd,
        ]

        if session_id:
            cmd.extend(["--conversation", str(session_id)])
        if output_format in ("text", "json", "stream-json"):
            cmd.extend(["--output-format", output_format])
        if json_schema:
            cmd.extend(["--json-schema", str(json_schema)])
        if agent:
            cmd.extend(["--agent", str(agent)])
        if model:
            cmd.extend(["--model", str(model)])
        if effort:
            cmd.extend(["--effort", str(effort)])

        return cmd
```

Then in `execute`, replace the `cmd = [...]` construction through the end of the `elif read_only:` branch with:

```python
        resolved_effort = effort
        if not resolved_effort and thinking_level is not None:
            from orchestrator.models_config import map_thinking_to_effort
            resolved_effort = map_thinking_to_effort(thinking_level)

        cmd = self.build_argv(
            instruction_mode=resolve_mode(kwargs.get("mode"), read_only),
            cwd=cwd,
            model=model,
            effort=resolved_effort,
            session_id=kwargs.get("session_id") or kwargs.get("conversation_id"),
            output_format=output_format,
            json_schema=kwargs.get("json_schema"),
            agent=kwargs.get("agent") or kwargs.get("subagent"),
        )
```

Delete the now-duplicated effort-resolution code further down in `execute` if present, so effort is computed exactly once.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: `11 passed`

- [ ] **Step 5: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `230 passed`

- [ ] **Step 6: Commit**

```bash
git add executors/agy_executor.py tests/test_executor_modes.py
git commit -m "feat: use agy native mode and sandbox instead of permission bypass"
```

---

## Task 5: Cursor adapter binary discovery and invocation

**Files:**
- Modify: `executors/cursor_executor.py:39-46` (`__init__` candidate paths), `:70-82` (`check_binary_health`), `:129` (the `cmd` construction in `execute`)
- Test: `tests/test_executor_modes.py` (append)

**Interfaces:**
- Consumes: `executors.base.Mode`, `executors.base.resolve_mode`.
- Produces: `CursorExecutor.build_argv(instruction_mode: Mode, model=None, session_id=None, output_format="text") -> list[str]`.

**Context — this is the bug that made Cursor unreachable.** The adapter searched for a binary named `cursor` and invoked it as `cursor agent -p`. The installed binary is `cursor-agent` at `~/.local/bin/cursor-agent` and is invoked as `cursor-agent -p`. `is_available()` has therefore always returned `False`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_executor_modes.py`:

```python
from executors.cursor_executor import CursorExecutor


def test_cursor_agent_binary_invokes_without_subcommand():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(Mode.CODE)
    assert argv[0] == "/usr/local/bin/cursor-agent"
    assert argv[1] == "-p"
    assert "agent" not in argv


def test_legacy_cursor_binary_keeps_agent_subcommand():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor").build_argv(Mode.CODE)
    assert argv[1] == "agent"
    assert argv[2] == "-p"


def test_cursor_review_mode_is_plan_and_never_forces():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(Mode.REVIEW)
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "-f" not in argv
    assert "--yolo" not in argv


def test_cursor_code_mode_forces_inside_sandbox():
    argv = CursorExecutor(binary_path="/usr/local/bin/cursor-agent").build_argv(Mode.CODE)
    assert "-f" in argv
    assert argv[argv.index("--sandbox") + 1] == "enabled"
    assert "--yolo" not in argv
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: FAIL — `AttributeError: 'CursorExecutor' object has no attribute 'build_argv'`

- [ ] **Step 3: Fix binary discovery**

In `executors/cursor_executor.py`, replace the `candidate_paths` list in `__init__` (lines 40–45) with:

```python
        candidate_paths = [
            binary_path,
            shutil.which("cursor-agent"),
            os.path.expanduser("~/.local/bin/cursor-agent"),
            shutil.which("cursor"),
            "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
            os.path.expanduser("~/.local/bin/cursor"),
        ]
```

`cursor-agent` is tried first so the modern binary wins when both exist.

- [ ] **Step 4: Implement build_argv**

Add `Mode` and `resolve_mode` to the existing `from executors.base import (...)` block, then add this method directly above `execute`:

```python
    def _uses_agent_subcommand(self) -> bool:
        """The legacy `cursor` binary needs an `agent` subcommand; `cursor-agent` does not."""
        return Path(self.binary_path).name != "cursor-agent"

    def build_argv(
        self,
        instruction_mode: Mode,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        output_format: str = "text",
    ) -> List[str]:
        """Construct the full cursor-agent argv for one invocation."""
        cmd = [self.binary_path]
        if self._uses_agent_subcommand():
            cmd.append("agent")
        cmd.append("-p")

        if instruction_mode is Mode.REVIEW:
            cmd.extend(["--mode", "plan"])
        else:
            cmd.extend(["-f", "--sandbox", "enabled"])

        if session_id:
            cmd.extend(["--resume", str(session_id)])
        if model:
            cmd.extend(["--model", str(model)])
        if output_format and output_format != "text":
            cmd.extend(["--output-format", output_format])

        return cmd
```

- [ ] **Step 5: Wire execute to build_argv**

In `execute`, replace `cmd = [self.binary_path, "agent", "-p"]` and the two `if model:` lines beneath it with:

```python
        cmd = self.build_argv(
            instruction_mode=resolve_mode(kwargs.get("mode"), read_only),
            model=model,
            session_id=kwargs.get("session_id"),
            output_format=kwargs.get("output_format", "text"),
        )
```

- [ ] **Step 6: Fix the health check for the new binary**

In `check_binary_health`, replace the `[self.binary_path, "agent", "--help"]` subprocess call with:

```python
            probe = [self.binary_path]
            if self._uses_agent_subcommand():
                probe.append("agent")
            probe.append("--help")
            res = subprocess.run(probe, capture_output=True, text=True, timeout=10)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_executor_modes.py -q`
Expected: `15 passed`

- [ ] **Step 8: Verify the adapter now sees the real binary**

Run:
```bash
.venv/bin/python -c "from executors.cursor_executor import CursorExecutor; e=CursorExecutor(); print(e.binary_path, e.is_available())"
```
Expected: a path ending in `cursor-agent`, followed by `True`. If it prints `None False`, the binary is not installed on this machine — record that in the commit body and continue.

- [ ] **Step 9: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `234 passed`

- [ ] **Step 10: Commit**

```bash
git add executors/cursor_executor.py tests/test_executor_modes.py
git commit -m "fix: detect cursor-agent binary and drop stale agent subcommand form"
```

---

## Task 6: Real-subprocess smoke tests

**Files:**
- Create: `tests/smoke/test_adapter_smoke.py`

**Interfaces:**
- Consumes: `scratch_repo` fixture (Task 1); `Mode` (Task 2); all three adapters (Tasks 3–5).
- Produces: nothing consumed downstream. This task's output is **evidence** — the first demonstration that any of this works.

**Why this task exists:** every flag in Tasks 3–5 is documented as correct, not demonstrated. These three tests are the first time Polyphony has ever actually invoked a coding-agent CLI and checked the result.

- [ ] **Step 1: Write the smoke tests**

Create `tests/smoke/test_adapter_smoke.py`:

```python
"""Real-subprocess smoke tests. These consume subscription quota.

Run explicitly:  pytest tests/smoke -m smoke -v
"""

from __future__ import annotations

import pytest

from executors.agy_executor import AgyExecutor
from executors.base import Mode
from executors.claude_executor import ClaudeExecutor
from executors.cursor_executor import CursorExecutor

SENTINEL = "POLYPHONY_OK"
PROMPT = f"Reply with exactly this one word and nothing else: {SENTINEL}"


def _assert_responded(res, executor_name: str):
    assert res.exit_code == 0, (
        f"{executor_name} exited {res.exit_code}\n"
        f"stdout: {res.output[:500]}\nstderr: {res.error}"
    )
    assert res.output.strip(), f"{executor_name} returned empty output"
    assert SENTINEL in res.output, (
        f"{executor_name} did not echo the sentinel.\nGot: {res.output[:500]}"
    )


@pytest.mark.smoke
def test_claude_adapter_responds(scratch_repo):
    ex = ClaudeExecutor()
    if not ex.is_available():
        pytest.skip("claude binary not installed")
    res = ex.execute(
        instruction=PROMPT,
        cwd=str(scratch_repo),
        mode=Mode.REVIEW,
        timeout_seconds=180,
    )
    _assert_responded(res, "claude")


@pytest.mark.smoke
def test_agy_adapter_responds(scratch_repo):
    ex = AgyExecutor()
    if not ex.is_available():
        pytest.skip("agy binary not installed")
    res = ex.execute(
        instruction=PROMPT,
        cwd=str(scratch_repo),
        mode=Mode.REVIEW,
        timeout_seconds=180,
    )
    _assert_responded(res, "agy")


@pytest.mark.smoke
def test_cursor_adapter_responds(scratch_repo):
    ex = CursorExecutor()
    if not ex.is_available():
        pytest.skip("cursor-agent binary not installed")
    res = ex.execute(
        instruction=PROMPT,
        cwd=str(scratch_repo),
        mode=Mode.REVIEW,
        timeout_seconds=180,
    )
    _assert_responded(res, "cursor")
```

- [ ] **Step 2: Confirm they are deselected by default**

Run: `.venv/bin/python -m pytest -q`
Expected: `234 passed` — the three smoke tests do not appear.

- [ ] **Step 3: Run the smoke tests for real**

Run: `.venv/bin/python -m pytest tests/smoke -m smoke -v`

Expected: 3 passed, or skips for binaries that are not installed.

**This step is allowed to fail, and a failure here is the single most valuable output of this plan.** If an adapter fails, capture the exact stderr and report it — do not patch around it. Likely findings, none of which you should pre-emptively "fix":

- `cursor-agent` may require the prompt as a positional argument rather than on stdin. The adapter currently pipes via `input=instruction`. If cursor fails with an empty or usage-style response, that is the answer to Open Question 1 in the spec.
- A CLI may reject `--sandbox` or `--permission-prompts` in combination with other flags.
- A CLI may need authentication that is not present.

- [ ] **Step 4: Record what actually happened**

Create `docs/superpowers/plans/2026-09-21-smoke-results.md` containing, for each of the three adapters: the exact argv used, the exit code, and the first 500 characters of stdout and stderr. Verbatim — no summarizing.

This file is the evidence base for Plans 2 and 3. Write it whether the tests passed or failed.

- [ ] **Step 5: Commit**

```bash
git add tests/smoke/test_adapter_smoke.py docs/superpowers/plans/2026-09-21-smoke-results.md
git commit -m "test: add real-subprocess smoke tests for all three executor adapters"
```

---

## Task 7: Refresh stale model identifiers

**Files:**
- Modify: `projects/medicoder/project.yaml:9-16` (the `models:` block)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by code. Configuration correctness only.

**Context:** the config pins `claude-3-7-sonnet-20250219`, superseded well over a year ago.

- [ ] **Step 1: Confirm which model ids the CLIs actually accept**

Run: `agy models 2>&1 | head -30`
Run: `cursor-agent --list-models 2>&1 | head -30`

For `claude`, the current family is Claude 5: `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5-1`, plus `claude-haiku-4-5-20251001`.

**Record the real output.** If a command fails or lists something unexpected, use what it actually reports rather than what this plan assumes.

- [ ] **Step 2: Update the config**

In `projects/medicoder/project.yaml`, replace the `models:` block with the values confirmed in Step 1. Using the expected defaults:

```yaml
models:
  lead:
    claude:
      model: "claude-opus-5"
      thinking_level: "high"
  executors:
    agy:
      model: "gemini-3.1-pro-high"
      thinking_level: "high"
```

Keep `gemini-3.1-pro-high` only if Step 1 confirmed `agy` still lists it; otherwise substitute what it reported.

- [ ] **Step 3: Verify the config still loads**

Run: `.venv/bin/python -c "from orchestrator.context import load_project_knowledge; from pathlib import Path; k=load_project_knowledge('medicoder', Path('.')); print(k['models'])"`
Expected: the dict prints with the new model ids and no exception.

- [ ] **Step 4: Verify nothing regressed**

Run: `.venv/bin/python -m pytest -q`
Expected: `234 passed`

- [ ] **Step 5: Commit**

```bash
git add projects/medicoder/project.yaml
git commit -m "chore: refresh stale model identifiers in medicoder config"
```

---

## Done criteria

- [ ] `.venv/bin/python -m pytest -q` → 234 passed, zero smoke tests selected
- [ ] `.venv/bin/python -m pytest tests/smoke -m smoke -v` → executed, results recorded verbatim in `2026-09-21-smoke-results.md`
- [ ] No occurrence of `--dangerously-skip-permissions` anywhere: `grep -rn "dangerously-skip" executors/` returns nothing
- [ ] `CursorExecutor().is_available()` → `True` on a machine with `cursor-agent` installed
- [ ] Seven commits on `redesign-spec`, none containing AI attribution

## What this plan deliberately does not do

- Does not touch `main.py`, `router.py`, or `cli.py` — those are rewritten in Plan 2, and changing them here would create conflicts.
- Does not remove `read_only` parameters. The bridge keeps existing callers working until Plan 2 migrates them.
- Does not implement the quota ledger. That needs the smoke-test evidence first.

## Hand-off to Plan 2

Plan 2 (Session & Loop) cannot be written until Task 6 reports. Specifically it needs to know: whether `cursor-agent` accepts stdin prompts, whether `--sandbox` is compatible with the other flags, and what a real failure from each CLI looks like on the wire.
