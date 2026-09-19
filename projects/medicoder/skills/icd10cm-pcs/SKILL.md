---
name: icd10cm-pcs
description: ICD-10-CM and ICD-10-PCS as stored in this repo — language, schema, lookup, and extract/maintain.
disable-model-invocation: true
---

# ICD-10-CM / PCS

Project model is law: SQLite, scripts, and the medicoder walk. Open a PDF only when a column or note cannot answer.

Use [analyze-runs](../analyze-runs/SKILL.md) for run artifacts.

## Process

### 1. Name the job

One of: **lookup** a code, **interpret** (Excludes1/2, Code first / Use additional code / Code also, 7th character, placeholder X, PCS axis/section), **extract/maintain** notes, **PCS structure** (axes, unique_* tables, section-dependent axis names).

Done when exactly one job is named.

### 2. Load language

Read [language.md](language.md). Use those terms; the `_Avoid_` lists are the banned synonyms.

Done when every CM/PCS word in the reply is a heading from that file.

### 3. Load schema

Read [schema.md](schema.md) for columns, PCS shape, and scripts.

Done when the job's columns and scripts are identified.

### 4. Interpret walk cases

If the job is interpret (or a lookup whose notes hit Excludes1/2, Code first, Use additional code, Code also, a 7th character, placeholder X, laterality, or a PCS axis/section), read [examples.md](examples.md) and match the row to a scenario.

Done when the row is named as one of those shapes, or as ordinary.

### 5. Act

- **lookup** — run the script; SQLite only for what it does not print:

  ```bash
  python scripts/lookup_icd10cm.py S72.001A
  python scripts/lookup_icd10pcs.py 0BB10ZZ
  python scripts/lookup_icd10pcs.py --level 3 0BB
  ```

- **interpret** — Excludes1/2, Code first, Use additional code, Code also, 7th character, placeholder X, laterality from that listing's `notes` and `title`; PCS axis from `axis_name` and unique_* titles. No pair graph.
- **extract/maintain** — read then run the generate scripts in schema.md. They do not write SQLite unless asked.
- **PCS structure** — schema.md PCS section; unique_* lookups; stub axes L2–L6.

Done when the answer cites that listing's own `notes` and `title` (not a reverse citation from another code).
