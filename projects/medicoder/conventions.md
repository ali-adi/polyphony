# Engineering & Authoring Conventions: medicoder

## 1. Code Style & Architecture
- **Language**: Python 3.11+ adhering to PEP 8 standards.
- **Type Annotations**: Mandatory type hints for public signatures and critical data models.
- **Docstrings & Comments**: Preserved at all times. Do not strip or alter unrelated comments during edits.
- **Edits**: Minimal, surgical modifications. Fix the implementation code rather than altering tests, unless the test specification itself is explicitly proven obsolete.

## 2. Testing & Quality Discipline
- **Virtual Environment**: All commands, scripts, and tests must be executed using `env/bin/python`.
- **Green Suite Guarantee**: Keep the unit tests passing at all times. Always run `env/bin/python -m unittest discover -s tests -t .` after any code, notes, or prompt modification.
- **Zero Broken Changes**: Never declare a task or PR complete if tests are failing.

## 3. Taxonomy Notes Authoring Rules
- **Note Format**: `<prose>. Includes: term; term; term.`
- **Formatting Constraints**: Single-line only, no pipe characters (`|`), at most one `Includes:` section per entry.
- **Prose Content**: State what the code/row covers and where its near neighbors sit in the hierarchy.
- **Case Contamination Ban**: Nothing in a note or prompt may come directly from evaluation cases. No verbatim phrases or code lists lifted from case misses. Notes draw strictly from taxonomy manuals and domain knowledge.

## 4. Database Interaction Conventions
- **Read-Only SQLite**: Database access is strictly read-only (`sqlite3 -safe -readonly`).
- **Immutable Snapshots**: Never edit anything under `database/` manually. The automated notes generator scripts (`scripts/generate_*_notes.py`) are the sole authorized writers.

## 5. Git Discipline & Safety
- **Explicit File Staging**: Only stage explicit file paths (`git add <path>`). Indiscriminate staging (`git add -A`, `git add .`, `git add -u`, `git commit -a`) is prohibited.
- **Commit Authorship**: Never append AI attribution trailers (`Co-authored-by: ...`).
- **Commit Responsibility**: Autonomous agents stage and verify; operator reviews and pushes.

---

## Reference Runbook Excerpt
```markdown
## Hard rules

- Every pipeline run is paid; one run per actual change, never a rerun to confirm.
- Only the driver session runs the pipeline, stamps the database, or edits the prompt file.
- Full runs: one discovery run per level unless the user confirms another after review. Never start `--on full` (including verify or `--force-full`) without that confirmation. `merge` still stands in for an unconfirmed verify.
- Nothing in a note, prompt line or draft may come from a case: no case phrases, no code lists lifted from a miss, no wording that only fits one note.
- A note may draw on the taxonomy (titles, descendants, source Includes/Excludes), the manual, and general medical knowledge.
- Remedies in order: notes, then a prompt line, then `min_x`. `min_x` moves only after a notes change and a prompt change both failed on the same miss, by at most +2 per level per tuning cycle, logged in the review file.
- `top_x` is the user's; never edit it.
- Never edit anything under `database/` by hand; the notes generator is the only writer. A taxonomy error is a flag.
- Never delete a case; `strip` keeps the original in `datasets/trash`.
- A level's discovery run happens only after that level's notes audit has landed and been stamped.
- Level N+1 runs `--from` level N's promoted run, never `--from-gt`.
- Do not commit; the user commits.
- Keep the unit tests green; run them after every code, notes or prompt change.

## Session setup

- `env/bin/python -m unittest discover -s tests -t . -q` → OK.
- `grep -oE '^[A-Za-z_]+=' .env` → includes `GEMINI_API_KEY=` (driver only; never print values).
- `pdftotext -layout <manual> tuning/<sys>/packs/manual.txt` (`brew install poppler` if missing).
- `env/bin/python scripts/tune_level.py --config <config> list --system <sys>` → runs on disk.
- `cat results/<SYS>/tuning-ledger.jsonl` → runs so far.
- `git status --short` → note the starting state; leave unrelated changes alone.
- Read `tuning/<sys>/review.md` top to bottom: it is the state of the work.

## Notes rules

- Shape: `<prose>. Includes: term; term; term.` on one line, no `|`, at most one `Includes:` section.
- Prose says what the row covers and where its near neighbours sit ("stroke sits under the circulatory chapter").
- `Includes:` lists the terms a clinician writes that the title does not imply; the pipeline also treats them as alternate titles for matching output.
- A term appears in the `Includes:` list of one sibling only. The other sibling's prose points to it. Where the manual's index puts a term decides the owner.
- Word caps (`scripts/am_achi_notes.py`): AM L1 400, L2 100, L3 60, L4 40, L5 30; chapters R00-R99, S00-T98 and U50-Y98 get 700, 200, 120, 80, 60. Above the cap needs a flag line saying why.
- Write from the row's descendants to the leaf (the pack lists them, sampled below a depth), the source Includes/Excludes, the manual's chapter and block notes, and medical knowledge.
- Sub-agents that draft notes see packs only, never `datasets/`. They are leaves: they do not launch Task.
- `check` every draft against its pack; `overlap` every level before it is written.

## Notes audit (before a level's discovery run)

- One audit session per chapter group; each owns its draft files and nothing else.
```
