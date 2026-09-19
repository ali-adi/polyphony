---
name: analyze-runs
description: Diagnose misses in a medicoder run for one coding family (AM/ACHI or CM/PCS), or compare two runs.
disable-model-invocation: true
---

# Analyze runs

One family per invocation: **AM/ACHI** (`icd10am`, `icd10achi`) or **CM/PCS** (`icd10cm`, `icd10pcs`). Skip the other family's `##` sections even when they sit in `report.md`.

Do not propose flag, grouping, ACS, companions, or pairing-enforcement changes.

## Process

### 1. Pin the run dir(s)

One `results/run_*` to diagnose, or two to compare (baseline then treatment). If none were given, ask.

Done when each path exists and contains `report.md`, `results.json`, and `config.json`.

### 2. Name the family

- Exactly one of [icd10am-achi](../icd10am-achi/SKILL.md) or [icd10cm-pcs](../icd10cm-pcs/SKILL.md) is attached → that family.
- Else the run's `config.json` `systems` are only AM/ACHI or only CM/PCS → that family.
- Else ask.

Then read that family's `language.md` and `schema.md`. For an AM dagger, asterisk, or paired miss, also [examples.md](../icd10am-achi/examples.md). For a CM/PCS interpret-shaped miss, also [examples.md](../icd10cm-pcs/examples.md). Use that family's skill to look up a code.

AM/ACHI: the walker does not read dagger, asterisk, paired flags, or `mapping.json` — a harvested manifestation without its etiology is a pipeline gap, not a model pairing error.

CM/PCS: the walker does not parse Code first, Use additional code, or Code also — a harvested manifestation without its etiology is a pipeline gap, not a pairing-model error.

Done when the family is named and those files are read.

### 3. Index missed and partial cases

Do not ingest all of `report.md`. Read the header, then that family's two `## {display}` summary tables. Collect every `###` case whose status is missed or partial.

From `results.json` / the case heading: lost-at stage (first hierarchy level with an expected miss). If harvest missed a code that every numbered stage found, lost-at is the deepest numbered stage where that code was still a candidate.

Done when every missed and partial case in that family is filed under one lost-at level.

### 4. Read the lost-at call (every expected miss)

For each expected miss, open **only** the lost-at stage (audit.json `layers[level]`, or that `####` in `report.md`). Pull four artifacts; skip the rest of the prompt's candidate list:

1. **Level prompt** — the instruction above the candidate rows (`configs/prompts/{system}.yml` for that level, as rendered).
2. **GT candidate** — title and Notes (`authored_notes`). If the row has no notes, say so.
3. **Thinking**
4. **Selection** — ranked picks

A miss that was **not offered** is filed at the earlier stage that dropped its parent.

Done when those four artifacts are in hand for every expected miss.

### 5. Diagnose by lost-at level

Group misses by lost-at L1…Ln (the two systems separately).

For each level, decide whether `configs/prompts/{system}.yml` for that level needs a new selection rule (keep `{min_x}` `{top_x}` `{title}|{notes}` `{medical_note}`). Compare the would-be instruction to the current yml text. If they match, label **Original Prompt** and do not reprint the instruction. If they differ, label **Proposed Prompt** and print a unified diff of that instruction (`+` added, `-` removed, context lines unchanged). Then the **notes** list: each changed candidate as the new YAML sentence for that code/title (see targets below). Then **every case** lost at that level, one-by-one, with evidence from thinking, picks, and the GT row.

Levers are only that prompt and those notes. Prompt for a selection rule that repeats across cases; notes for a synonym or inclusion the thinking missed on that row.

Notes YAML (the value is the sentence):

- AM: `scripts/icd10am_notes.yml`
- ACHI: `scripts/icd10achi_notes.yml`
- CM: `scripts/cm_level{n}_guideline_notes.yml` at the lost-at level (create the file if missing)
- PCS L1: `scripts/pcs_level1_notes.yml`
- PCS L2+: none, unless that axis value already has unique_* `authored_notes` — then the replacement axis sentence

Done when every lost-at level has Original Prompt or a Proposed Prompt diff, a notes proposal (or “none”), and a case paragraph for every miss at that level.

### 6. Compare (two runs)

Diff `config.json` (`systems`, `prompts_sha256`, `db_sha256`, `authored_notes`, `group_rows`) then the two family summary tables and which cases moved status.

Done when every status change is attributed to a config/data change or called unexplained.

## Output

Per lost-at level, the prompt line is **Original Prompt** (instruction unchanged; do not reprint it) or **Proposed Prompt** (a `diff` fence of `configs/prompts/{system}.yml` for that level: `+` added, `-` removed). Then notes and cases.

    ## {display}

    ### L{n}
    **Original Prompt**
      — or —
    **Proposed Prompt**
    {diff fence of the yml instruction}

    **Notes**
    - {code}: {new authored_notes sentence}
    - none

    **Cases**
    - Case {id} ({codes}): {why it failed}. Evidence: thinking “…”; picked {titles}; GT {title} was {unmentioned | considered | not offered | picked-then-replaced}.

    ### L{n+1}
    …

    ## {other display in the family}
    - (same by level, or “not in this run”)

    ## Compare   (two runs only)
    - config: {what changed}
    - {system}: {status moves}
