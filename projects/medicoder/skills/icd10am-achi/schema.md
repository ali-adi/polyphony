# Schema

Project model of ICD-10-AM and ACHI as stored in this repo. Terms: [language.md](language.md). Query SQLite or `mapping.json` for live values; this file is rules, not a count cache.

Paths: `database/icd10am_achi/icd10am.sqlite`, `icd10achi.sqlite`, `mapping.json`. PDF: `database/manuals/ICD-10-AM.pdf` only when a column or note cannot answer.

## ICD-10-AM

Walker names (`medicoder/taxonomy/systems.py`): L1 Chapter, L2 Block, L3 Category, L4 4-character code, L5 5-character code.

```
L1 chapter (code_from–code_to)
  → L2 block (code_from–code_to)
    → L3 category (3-char)
      → L4 4-char
        → L5 5-char
```

L1/L2 are ranges, never assigned. Dual-coding and α columns exist on L3–L5 only.

### Columns (L3–L5)

| Column | Meaning |
|--------|---------|
| `code`, `title` | Tabular code and rubric. Heading symbols are not in `title`. |
| `notes` | Raw extraction. Pipeline never reads this. |
| `authored_notes` | Model-facing text. Pipeline reads this column. |
| `acs_codes` | Australian Coding Standards refs. |
| `is_assignable` | α assignable flag. This row is a harvestable code (a leaf). |
| `is_dagger` | †. Dagger flag. Mutually exclusive with `is_asterisk`. |
| `is_asterisk` | *. Asterisk flag. |
| `is_paired` | ∞. Paired flag. |

Treat the column as what the DB stores; treat [language.md](language.md) as what the flag *is*. Prose uses Notation; this table is SQLite names.

### Flag rules

- **Assignable flag**: L3/L4 α ⇔ no children at the next level. Every L5 row is α. Rows without α group children; the walker descends them (`Taxonomy.classify_picks`). Pairing is evaluated on the α descendant, not on a stem you cannot code.
- **Dagger / asterisk flags**: etiology vs manifestation from own-entry notes and title. Never both. May have partners in `mapping.json`; that pair is optional. Standalone assignment is allowed. Compulsory pairing is the paired flag.
- **Paired flag**: when this listing is assigned, emit a dual-code pair from `mapping.json` (etiology then manifestation). Paired flag 1 means the listing prints a heading symbol. Paired does not require α: if paired and not α, walk down until an α descendant, then look up that code in `mapping.json`.
- **Inheritance (down only)**: if a parent has dagger, asterisk, or paired flag = 1, every child has the same flag. Children may be flagged when the parent is not (`A18.0` under unflagged `A18`).

### `mapping.json`

AM↔AM dual-code pair graph. Bidirectional. No ACHI codes. The walker does not load this file.

| `type` | `code` |
|--------|--------|
| `direct` | one partner string |
| `list` | array of site/sibling codes |
| `edge` | a range string |

Keys exist at L3, L4, and L5. Stems without α are often absent as keys (`M01.1` is not a key; `M01.15` is). Look up the α code.

### Pipeline

`medicoder/taxonomy/hierarchical.py` loads `id, parent, code, title, authored_notes, is_assignable`. It ignores dagger, asterisk, and paired flags. `CodeEntry` has no dual-coding fields. A harvested manifestation without its etiology is a pipeline gap, not a pairing-model error.

## ACHI

Walker names: L1 Chapter, L2 Site, L3 Procedure Type, L4 Block, L5 Code, L6 Extension.

```
L1 chapter (chapter_number, block_from–block_to)
  → L2 site (title, no code)
    → L3 procedure type (junction: site × `icd10achi_procedures`)
      → L4 block (`block_no`, displayed `[n]`)
        → L5 code
          → L6 extension
```

- L3 is a junction row: `procedure_id` → `icd10achi_procedures.title`. Same procedure title can appear under many sites.
- Chapter 20: some L4 blocks hang off a site with no procedure type (`parent_id` null; `Taxonomy.l4_site`).
- L5 also stores `mbs_item` and `code_extension`.
- `icd10achi_companions`: "Code also when performed" links. Offered as extra candidates, never forced. Loaded when `companions: true`.

α is a leaf flag on L5/L6, same harvest rule as AM.

## Scripts

Execute (read-only lookup):

```bash
python scripts/lookup_icd10am.py E11
python scripts/lookup_icd10achi.py --level 5 96196-00
```

`lookup_icd10am.py` prints an L3 category plus L2/L1 ancestors. L4/L5 flags: query SQLite.

Read, then run; they do not write SQLite unless asked:

- `scripts/extract_icd10am_heading_symbols.py` — printed heading † / * from the PDF (check against paired flag) → `tmp/icd10am_heading_daggers.txt` and `…_asterisks.txt`.
- `scripts/extract_icd10am_dual_coding.py` — current positives plus note-role proposals (`scripts/icd10am_dual_coding.py`).
- Source lists used to set the paired flag: `text_dagger.txt`, `text_asterisk.txt`.

Note dagger / note asterisk flags have no columns. Derive them with `scripts/icd10am_dual_coding.py` (`note_role`, `propose_flags`).

`scripts/generate_am_achi_notes.py` stamps `authored_notes` from YAML when asked to write notes.

## Known holes

- `K23` / `K67`: L4 children asterisk-flagged and paired; L3 unflagged. `text_asterisk.txt` lists the L3 headings.
- `M32.1`: dagger flag, paired flag 0, notes list `*` partners; PDF heading extract includes it (paired flag should be 1 if the heading prints †).
- `B37.3`: in `text_dagger.txt` (paired flag 1, so a heading symbol); not in the PDF heading-dagger extract.
