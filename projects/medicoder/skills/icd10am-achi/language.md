# Language

ICD-10-AM / ACHI dual-coding glossary. This file is the source of truth; new terms go here.

## Dual coding

**Notation**:
How a listing’s four columns are written. A present glyph is 1; omit the glyph when 0. `†` dagger flag (`is_dagger`). `*` asterisk flag (`is_asterisk`). `∞` paired flag (`is_paired`). `α` assignable flag (`is_assignable`). In a flag string these are column values, not the printed heading. Example: G01 is `* ∞ α`; A69.2 is `† α`; M01.1 is `* ∞`.
_Avoid_: `d=` `a=` `p=` `asg=`, `is_dagger=1` in prose, the word `assignable` in a flag string

**Heading symbol**:
The † or * printed on a code number in that code’s own tabular heading, as in A18.0†. It is not stored in the database `title` string. **Paired flag** 1 is the stored sign that this listing has a heading symbol.
_Avoid_: title dagger, title asterisk, dagger flag, asterisk flag

**Own-entry evidence**:
The tabular listing for this code: heading symbol, title, and that listing’s inclusion notes. Another code citing this code as † or * is not own-entry evidence.
_Avoid_: reverse mapping, reverse-mapped dagger

**Dual-code pair**:
One etiology assignment and one manifestation assignment, sequenced etiology then manifestation.
_Avoid_: dagger-asterisk map, reverse map

**Dagger flag**:
Own-entry notes or title treat this listing as etiology. Set from own-entry only. Mutually exclusive with asterisk flag. The listing may sit in a dual-code pair as the etiology, with partners in `mapping.json` at the α code. That mapping is optional: assign the listing standalone when no manifestation is documented. Compulsory pairing is the paired flag, not this flag. A69.2 is `† α`: mapping lists G01 and M01.20; still assign A69.2 alone when there is no manifestation.
_Avoid_: heading symbol, note dagger flag, reverse-mapped dagger

**Asterisk flag**:
Own-entry notes or title treat this listing as manifestation. Set from own-entry only. Mutually exclusive with dagger flag. The listing may sit in a dual-code pair as the manifestation, with partners in `mapping.json` at the α code. That mapping is optional: assign the listing standalone when no etiology is documented. Compulsory pairing is the paired flag, not this flag.
_Avoid_: heading symbol, note asterisk flag

**Note dagger flag**:
Boolean meaning this listing is etiology in at least one dual-code pair in its own inclusion notes, or the dagger flag is already 1. Excludes and instructional mentions of * or † (as in G09) do not set it. 0/1 only; never null. A69.2 is 0.
_Avoid_: dagger flag, † character present

**Note asterisk flag**:
Boolean meaning this listing is manifestation in at least one dual-code pair in its own inclusion notes, or the asterisk flag is already 1. Same Excludes / instructional-prose rule as the note dagger flag. 0/1 only; never null.
_Avoid_: asterisk flag, * character present

**Site-code inheritance**:
A fifth-character site code copies the parent stem’s dagger, asterisk, and paired flags. M47.00 copies M47.0†; M01.20 copies M01.2*.
_Avoid_: independent L5 heading symbol

**Paired flag**:
Boolean meaning when this listing is assigned it must be dual-coded with its partners in `mapping.json`. A 1 means this listing’s own code number prints a heading symbol († or *). Does not imply α. This flag is the compulsory overlay; dagger flag or asterisk flag without it stays standalone.
_Avoid_: dagger flag, asterisk flag, pair-capable

**Assignable flag**:
Glyph `α` for `is_assignable`. This listing is a harvestable leaf. Look up `mapping.json` at this code, not at a parent without α.
_Avoid_: the word assignable in a flag string
