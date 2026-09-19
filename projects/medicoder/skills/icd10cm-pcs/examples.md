# Interpret examples

Worked rows. Terms: [language.md](language.md). Not a pair graph.

## Excludes1 vs Excludes2

**A06** Amebiasis — `asg=0`. Excludes1: other protozoal intestinal diseases (`A07.-`) — never with `A06`. Excludes2: acanthamebiasis (`B60.1-`), Naegleriasis (`B60.2`) — not part of `A06`, both allowed if documented.

## Code first / Use additional code (notes, not pairs)

**A40** Streptococcal sepsis — `asg=0`. Notes list Code first partners (postprocedural sepsis, catheter, labor, …). Prose only; no `mapping.json`. The walker does not emit those partners.

**B20** HIV disease — `asg=1`. Code first HIV complicating pregnancy (`O98.7-`) if applicable. Use additional code(s) to identify all manifestations. Assign `B20` alone when those notes do not apply.

## 7th character

**S72.001A** Fracture of unspecified part of neck of right femur, initial encounter for closed fracture — L7 `asg=1`. Siblings **S72.001D** subsequent, **S72.001S** sequela. The 7th character is the L7 row, not a flag on `S72.001`.

## Placeholder X

**H54.0X33** Blindness right eye category 3, blindness left eye category 3 — the X pads so two category digits can sit in the 6th and 7th places. Not unspecified-as-a-flag.

## Laterality

**S72.21** Displaced subtrochanteric fracture of right femur vs **S72.22** left. Right/left lives in the code and title. No laterality flag.

## PCS path, device vs none, qualifier diagnostic vs none

**0BB10ZZ** Excision of Trachea, Open Approach — Section `0` Medical and Surgical → Body system `0B` Respiratory → Root operation Excision → Body Part Trachea → Approach Open → Device No Device → Qualifier none. `asg=1` at L7 only.

**0BB10ZX** same path, Qualifier Diagnostic.

## Approach vs method

**0BB10ZZ** L5 `axis_name` Approach = Open (Medical and Surgical).

**7W00X0Z** Osteopathic Treatment of Head using Articulatory-Raising Forces — L6 `axis_name` Method = Articulatory-Raising. Character 6 is not Device here.

## Section-dependent axis

**B00B0ZZ** Plain Radiography of Spinal Cord using High Osmolar Contrast — L5 `axis_name` Contrast, not Approach. Same walker level as Open on `0BB10`.
