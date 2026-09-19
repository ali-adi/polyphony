# Safety & Operational Policies: medicoder

These policies are strictly enforced across all executor engines (`claude`, `agy`, `cursor`) before, during, and after task execution.

## 1. Protected Database Snapshots
- **Rule**: Never edit, modify, truncate, or overwrite any file under `database/` or `*/database/*`.
- **Rationale**: These are pre-computed taxonomy database snapshots. Corrupting them invalidates ICD-10 codings.
- **Action on Violation**: Immediate execution block and task abort.

## 2. Cost Safety & API Pipeline Throttling
- **Rule**: Autonomous agents may only run pipeline commands targeting `configs/smoke.yml` or `configs/sample.yml` without `--cases`.
- **Blocked Commands**:
  - Direct runs of `--config configs/full.yml`
  - Running `scripts/tune_level.py --force-full`
- **Rationale**: Full pipeline sweeps make dozens of paid external Gemini API calls. Full evaluations must be explicitly initiated by the human operator.

## 3. Git Operations & Repository Integrity
- **Rule**:
  - Bulk staging (`git add -A`, `git add .`, `git add --all`, `git add -u`) is strictly forbidden. Files must be added explicitly by path.
  - Automatic `git push` or `git merge` is disabled.
  - AI attribution signatures (`Co-authored-by: ...`) in git commit messages are blocked.
- **Rationale**: Prevent accidental inclusion of credentials, temporary evaluation artifacts, or unintended commits.

## 4. Database Query Safety
- **Rule**: SQLite database queries must be strictly read-only (`sqlite3 -safe -readonly` or `SELECT` statements only). `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER` are blocked.

## 5. Verification Before Stop (Quality Gate)
- **Rule**: Before any task or iteration is declared successful, the full test suite must pass (`python -m unittest discover -s tests -t .`).
- **Action on Failure**: Agent must inspect failures and fix them or halt with a report.
