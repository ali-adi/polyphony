# Polyphony

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What it is

Polyphony is a local-first orchestrator that drives the `claude`, `agy`, and
`cursor-agent` CLIs as subprocesses instead of calling metered APIs, so
existing subscriptions do the work.

## Status

> Under active redesign. Two of the three executor adapters had never
> successfully executed anything until 2026-09-21; they now pass real-binary
> smoke tests. The orchestration loop is being rebuilt. Treat anything not
> listed under "What works" as not implemented.

## What works

- Three executor adapters (`claude`, `agy`, `cursor-agent`) with `review`
  (read-only) and `code` (accept-edits) modes, each mapped onto the CLI's own
  permission flags. Verified by `pytest tests/smoke -m smoke`.
- Isolated task workspaces: a git worktree outside the target repo,
  provisioning of gitignored paths via copy-on-write, and a squash-merge
  hand-back. `polyphony workspace create|list|clean`.
- `git push` refused at the subprocess layer.
- `polyphony migrate` — ingests `.claude/`, `.cursor/`, `.agents/` config.
- `polyphony doctor` — environment diagnostics.

## What does not work yet

- The orchestration loop (`polyphony start`) is mid-rewrite and has never
  been run against a real task.
- `events`, `replay`, `explain`, and `export` have no event stream to read.
- `approve` and `reject` have no approval flow behind them.
- `benchmark` produces synthetic numbers and should not be used.

## Install and quick start

```bash
git clone https://github.com/ali-adi/polyphony.git
cd polyphony

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify the install and check the environment:

```bash
polyphony --version
polyphony doctor
```

Migrate an existing repo's `.claude/`, `.cursor/`, or `.agents/` config into
a Polyphony project (`--output` defaults to the current directory, so pass
one explicitly unless you're running this from inside a Polyphony root):

```bash
polyphony migrate /path/to/your-repo --name your-project --output /path/to/polyphony-root
```

Create, list, and clean an isolated task workspace (a git worktree outside
the target repo):

```bash
polyphony workspace create your-project task-1 --repo /path/to/your-repo
polyphony workspace list --repo /path/to/your-repo
polyphony workspace clean task-1 --repo /path/to/your-repo
```

Run the test suite:

```bash
.venv/bin/python -m pytest -q          # 275 passed, 3 deselected
.venv/bin/python -m pytest tests/smoke -m smoke -q   # 3 passed — real executor binaries
```

## Design docs

- `docs/superpowers/specs/` — the redesign spec.
- `docs/superpowers/plans/` — implementation plans, including this cleanup.

## License

Polyphony is licensed under the [MIT License](LICENSE).
