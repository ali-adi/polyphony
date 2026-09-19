# Schema

Project model of ICD-10-CM and ICD-10-PCS as stored in this repo. Terms: [language.md](language.md). Query SQLite for live values; this file is rules, not a count cache.

Paths: `database/icd10cm_pcs/icd10cm.sqlite`, `icd10pcs.sqlite`. No `mapping.json`. PDF: `database/manuals/cm_guidelines.pdf` or `pcs_guidelines_2026-508.pdf` only when a column or note cannot answer.

## ICD-10-CM

Walker names (`medicoder/taxonomy/systems.py`): L1 Chapter, L2 Block, L3 Category, L4 4-character code, L5 5-character code, L6 6-character code, L7 7-character code.

```
L1 chapter (code_from–code_to)
  → L2 block (code_from–code_to)
    → L3 category (3-char)
      → L4 4-char
        → L5 5-char
          → L6 6-char
            → L7 7-char
```

L1/L2 are ranges, never assigned. Assignable columns exist on L3–L7 only.

### Columns (L3–L7)

| Column | Meaning |
|--------|---------|
| `code`, `title` | Tabular code and rubric. |
| `notes` | Raw extraction. Pipeline never reads this. |
| `authored_notes` | Model-facing text. Pipeline reads this column. |
| `is_assignable` | This row is a harvestable code (a leaf). |

No ACS, dagger, asterisk, or paired columns.

### Assignable

L3–L6 assignable ⇔ no children at the next level. Every L7 row is assignable. Unassignable rows group children; the walker descends them (`Taxonomy.classify_picks`).

### Pipeline

`medicoder/taxonomy/hierarchical.py` loads `id, parent, code, title, authored_notes, is_assignable`. It ignores instructional prose (Code first, Use additional code, Code also, Excludes1, Excludes2). A harvested manifestation without its etiology is a pipeline gap, not a pairing-model error.

## ICD-10-PCS

Walker names: L1 Section, L2 Body System, L3 Root Operation, L4 Character 4, L5 Character 5, L6 Character 6, L7 Character 7. Characters 4–7 are named by position because `axis_name` varies by section.

```
L1 section (1-char)
  → L2 body system
    → L3 root operation
      → L4 character 4 (unique_parts)
        → L5 character 5 (unique_approaches)
          → L6 character 6 (unique_devices)
            → L7 character 7 (full 7-char code)
```

- L1 and L7 store `title` on the row. L2–L6 store a unique_* id; `load_pcs` composes `parent title, value` (`None` dropped).
- `axis_name` on L4–L7 is the clinical axis (Body Part, Approach, Contrast, Method, Qualifier, …). unique_* table names do not always match that axis.
- L2–L6 are stub axes (`medicoder/taxonomy/stubs.py`): the model sees one unique_* title shared across parents.
- Only L7 is assignable. L1/L2 are never; L3–L6 `is_assignable` is 0 in this DB.
- No companions table. `companions: false` in the system config.

### Pipeline

`medicoder/taxonomy/pcs.py` loads L1/L3/L7 `authored_notes` and unique_* `authored_notes` into `axis_notes` when that column exists. It sets notes NULL for L4–L6 rows (`_ICD10PCS_NO_NOTES`). Stub candidates show unique_* `authored_notes`, not the stamped row notes.

## Scripts

Execute (read-only lookup):

```bash
python scripts/lookup_icd10cm.py S72.001A
python scripts/lookup_icd10pcs.py 0BB10ZZ
python scripts/lookup_icd10pcs.py --level 3 0BB
```

`lookup_icd10cm.py` prints the given code at its real depth (3–7 characters) plus every ancestor. `lookup_icd10pcs.py` prints the axis path with unique_* titles and `axis_name`.

Read, then run; they do not write SQLite unless asked:

- `scripts/generate_cm_notes.py` — stamps `authored_notes` from `scripts/cm_level{n}_guideline_notes.yml` (L1–L2 exist; L3–L7 keyed by code when the file exists) and optional `cm_level{n}_block_summaries.yml`.
- `scripts/generate_pcs_notes.py` — L1 from `scripts/pcs_level1_notes.yml`; L2 hand-authored and left alone; L3–L6 templates from child titles.

## Known holes

- CM L3–L7 `authored_notes` are mostly empty; L1/L2 hold guideline stamps.
- `load_pcs` does not load L4–L6 row `authored_notes`. Proposing a note on those rows does not reach the prompt; stubs read unique_* `authored_notes` (`icd10pcs_level6_unique_devices` has that column; parts and approaches do not).
- unique_* table names do not always match the clinical axis (`unique_approaches` holds Contrast; `unique_devices` holds Method).
