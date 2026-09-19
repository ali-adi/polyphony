---
name: icd10am-achi
description: ICD-10-AM and ACHI as stored in this repo — language, schema, lookup, and extract/maintain.
disable-model-invocation: true
---

# ICD-10-AM / ACHI

Project model is law: SQLite, `mapping.json`, scripts, and the medicoder walk. Open a PDF only when a column or note cannot answer.

Use [analyze-runs](../analyze-runs/SKILL.md) for run artifacts.

## Process

### 1. Name the job

One of: **lookup** a code, **interpret** dual-coding flags, **extract/maintain** flags or notes, **ACHI structure** (companions, junctions, Chapter 20).

Done when exactly one job is named.

### 2. Load language

Read [language.md](language.md). Use those terms; the `_Avoid_` lists are the banned synonyms.

Done when every dual-coding word in the reply is a heading from that file, and flag strings use Notation (`†` dagger flag, `*` asterisk flag, `∞` paired flag, `α` assignable flag).

### 3. Load schema

Read [schema.md](schema.md) for columns, flag rules, `mapping.json`, ACHI shape, and scripts.

Done when the job's columns and scripts are identified.

### 4. Dual-coding walk cases

If the job is interpret (or a lookup whose row is dagger, asterisk, or paired), read [examples.md](examples.md) and match the row to a scenario.

Done when the row is named as one of those shapes, or as ordinary (no dual flags).

### 5. Act

- **lookup** — run the script; SQLite only for L4/L5 flags `lookup_icd10am.py` does not print:

  ```bash
  python scripts/lookup_icd10am.py E11
  python scripts/lookup_icd10achi.py --level 5 96196-00
  ```

- **interpret** — dagger/asterisk/paired from SQLite (heading symbol from paired flag; dagger/asterisk from notes and title, optional `mapping.json` partners, standalone unless paired); note dagger/note asterisk from `scripts/icd10am_dual_coding.py`; partners from `mapping.json` at the α code.
- **extract/maintain** — read then run the extract scripts in schema.md. They do not write SQLite unless asked.
- **ACHI structure** — schema.md ACHI section; companions from `icd10achi_companions`.

Done when the answer cites own-entry evidence (the listing, not a reverse citation) and, for a paired α row, the `mapping.json` partners.
