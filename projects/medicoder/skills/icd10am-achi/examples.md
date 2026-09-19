# Dual-coding examples

Worked rows. Flag strings: [Notation](language.md). Terms: [language.md](language.md).

## Mandatory pair, α on the same row

**G01** Meningitis in bacterial diseases classified elsewhere — `* ∞ α` (no L4). Assign `G01`, then an etiology from `mapping.json`. Sequence: etiology then `G01`.

**B59** Pneumocystosis — `† ∞ α`. Mapping: `B59` → `direct` `J17.3`. Assign `B59` then `J17.3`.

**A18.0** Tuberculosis of bones and joints — under unflagged `A18`. `† ∞ α`. Heading symbol †; dagger flag from own-entry notes/title. Mapping includes `list` site ranges (`M01.10–19`, …) and `direct` partners.

**D63.0** Anaemia in neoplastic disease — parent `D63` is `*` (never assign the category). `D63.0` is `* ∞ α`. Mapping type `edge`: `C00-D48`.

## Mandatory pair, not α — walk down

**M01.1** Tuberculous arthritis — `* ∞` → L5 `M01.15` Pelvic region and thigh `* ∞ α`. `M01.1` is not a mapping key; `M01.15` is (`direct` `A18.0`). Sequence: `A18.0` then `M01.15`. Same shape: other M01/M03/M07/M09/M49/… site stems, and dagger stems **M05.3**, **M47.0**.

## Optional dagger (standalone allowed)

**A69.2** Lyme disease — `† α`. Mapping still lists partners for when a manifestation is documented. Assign `A69.2` alone if there is none. Contrast: `M01.2` Arthritis in Lyme disease is `* ∞` → walk to `M01.2x`, which must pair (typically with `A69.2`).

**A01.0** Typhoid fever — `† α`. Typhoid as a disease is complete; meningitis in typhoid is `A01.0` + `G01`.

**A18.1** Tuberculosis of the genitourinary system — `† α`. Dagger flag from inclusion terms (`bladder† (N33.0*)`); paired flag 0 so the listing can be assigned without a pair when those terms do not apply.

## Dagger inherited, not paired

**C88.0** Waldenström's macroglobulinaemia — `†` → `C88.00` / `C88.01` (remission split) `† α`. Same shape: `C90.0`, `M10.0` (gout site fifth character). Children inherit the dagger flag, not the paired flag.

## Asterisk on the child only

**K23** / **K67**: L3 unflagged; L4 children `* ∞ α`. Allowed by downward inheritance only.
