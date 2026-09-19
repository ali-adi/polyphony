# Project Context: medicoder

## High-Level Objective

Medicoder is an autonomous ICD-10 medical coding system that maps free-text clinical notes and diagnosis strings to standardized taxonomy codes (ICD-10-AM, ICD-10-PCS, ACHI) using hierarchical ranking and large language models.

## Architectural Components

- **Core Taxonomy Database**: Pre-built, versioned SQLite taxonomy snapshots located in `database/`. These tables are immutable references and must never be edited directly.
- **Pipeline Runner**: `medicoder/main.py` runs batch evaluation against clinical case sets. Configured via YAML in `configs/` (`smoke.yml`, `sample.yml`, `full.yml`).
- **Tuning Harness**: `scripts/tune_level.py` tunes prompt structures and level-by-level decision accuracy with strict run budgets.
- **Test Suite**: Standard unittest suite under `tests/`. Verified using `env/bin/python -m unittest discover -s tests -t .`.

## Key Technical Conventions

- **Python Runtime**: Python 3.11+ virtualenv located at `env/`.
- **Database Access**: Read-only SQLite queries (`sqlite3 -safe -readonly`).
- **Code Edits**: Minimal, focused surgical changes. Always run tests to verify green status before marking tasks complete.
- **Git Protocol**: Individual explicit file adds only (`git add <file>`). Never run `git add -A` or indiscriminate staging.

---

## Extracted README Reference

# Medicoder

Walks ICD-10-AM, ACHI, ICD-10-CM and ICD-10-PCS top-down with Gemini, one ranking call per level, then harvests every complete code it picked.

## Setup

```bash
python -m venv env
env/bin/pip install -r requirements.txt
echo "GEMINI_API_KEY=..." > .env
```

## Layout

```
configs/     config.yml, smoke.yml, systems/<system>.yml, prompts/<system>.yml
database/    taxonomy SQLite files (icd10am_achi/, icd10cm_pcs/, tosp.sqlite) and manuals/ (ICD-10-AM, ACHI PDFs)
datasets/    cases/ (tracked case set), smoke/ and tuning/ (local, gitignored)
medicoder/   config/, taxonomy/, ranking/, pipeline/, output/, cli.py
scripts/     maintenance scripts, not part of a run
tests/       mirrors medicoder/
results/     run output (gitignored)
```

## Config

- `configs/base.yml`: everything shared. The run configs say `extends: base.yml` and state only what they change.
- `configs/smoke.yml` (1 case), `configs/sample.yml` (30), `configs/full.yml` (118). See `configs/README.md`.
- `configs/tune-<system>.yml`: runs the full case set for one system only into its own results folder.
- `configs/systems/<system>.yml`: `companions` and one `model`/`thinking_level`/`top_x`/`min_x` row per level.
- `configs/prompts/<system>.yml`: one prompt per level.
- `keep_all_within_top_x`: when true, a level whose pool fits within `top_x` keeps every candidate without a model call.
- Every key is required; unknown keys, missing levels and unpriced models are refused.

## Run

```bash
python -m medicoder                                           # smoke by default: one case, costs ~nothing
python -m medicoder --config configs/sample.yml               # 30 cases, the experiment workhorse
python -m medicoder --config configs/full.yml                 # all 118 cases
python -m medicoder --config configs/full.yml --systems cm    # ...one system only
python -m medicoder --config configs/full.yml --cases datasets/tuning/cm/L1   # ...another case folder
python -m medicoder --level 4 --from results/run_<timestamp>  # rerun one level on an earlier run's picks
python -m medicoder --level 4 --from-gt                       # one level, ground truth as the picks above
python -m medicoder --resume results/run_<timestamp>          # reuse the finished cases of a run
python -m medicoder --predict                                 # run without ground truth (skips scoring)
```

- `--resume` needs the same config and flags as the run it resumes.
- Runs from before the package rewrite cannot be resumed.

## Output

`results/run_<timestamp>/`:

- `config.json`: settings snapshot, checked by `--resume`.
- `checkpoint.jsonl`: one line per finished case.
- `results.json`: per-case stages and per-system summary.
- `audit.json`: prompts, candidates and raw replies.
- `report.md`, `report.html`: readable reports; rebuild with `python -m medicoder.output.report <run_dir> [--out DIR]`.

Per level:

- `recall`: ground truth picked / all ground truth at that level.
- `level_recall`: ground truth picked / ground truth that was offered as a candidate at that level.
- `harvest`: the complete codes collected across the walk, scored against the full codes.

## Tests

```bash
env/bin/python -m unittest discover -s tests -t .
```

## Scripts

- **Tuning & Evaluation**:
  - `scripts/tune_level.py`: per-level tuning harness on case subsets.
  - `scripts/compare_runs.py`: compare results between two runs.
  - `scripts/trace_audit.py`: inspect the audit trail.
- **Notes Authoring**:
  - `scripts/am_achi_notes.py`, `cm_notes.py`, `pcs_notes.py`: export and check notes.
  - `scripts/generate_*_notes.py`: embed the authored YAML notes into the database.
- **Utilities**:
  - `scripts/lookup_*.py`: inspect the hierarchy for a given code.
  - `scripts/build_full_dataset.py`: compile the full dataset.

