# Language

ICD-10-CM / PCS glossary. This file is the source of truth; new terms go here.

## ICD-10-CM

**Excludes1**:
A note meaning the excluded code is never assigned with this code.
_Avoid_: excludes, exclusion, Excludes2

**Excludes2**:
A note meaning the excluded condition is not part of this code, but both may be assigned if documented.
_Avoid_: excludes, exclusion, Excludes1

**Code first**:
Instructional note naming the etiology or underlying condition to sequence ahead of this listing. Prose in `notes` only; not a paired flag.
_Avoid_: dagger, pairing, dual coding, mapping

**Use additional code**:
Instructional note naming a manifestation or extra detail to assign with this listing. Prose in `notes` only.
_Avoid_: asterisk, pairing, dual coding

**Code also**:
Instructional note to assign another code when the extra condition is documented; sequencing is not implied. Prose in `notes` only.
_Avoid_: code first, use additional code, companion

**7th character**:
The seventh character of an ICD-10-CM code (encounter, healing, gestation, …), stored as an L7 row.
_Avoid_: seventh-character extension, L7 character, encounter flag, qualifier

**Placeholder X**:
An X in a CM code that pads unused character positions so a 7th character can attach.
_Avoid_: unspecified X, dummy character, wildcard

**Laterality**:
Right, left, or bilateral encoded in a CM code's characters and title, not a flag.
_Avoid_: laterality flag, side flag

The walker does not parse Code first, Use additional code, or Code also. A harvested manifestation without its etiology is a pipeline gap, not a pairing-model error.

## ICD-10-PCS

**Section**:
L1. First character of a PCS code.
_Avoid_: chapter

**Body system**:
L2.
_Avoid_: chapter, site

**Root operation**:
L3.
_Avoid_: procedure type

**Axis**:
One of the seven characters, whose meaning is named by `axis_name` and may change by section.
_Avoid_: level, character 4 meaning body part always

**Approach**:
Common L5 axis in Medical and Surgical (Open, Percutaneous, …). Not every section's character 5 is Approach.
_Avoid_: method, access

**Device**:
Common L6 axis. The unique_* table also holds substances, methods, and equipment.
_Avoid_: implant, DME

**Qualifier**:
L7. Completes the 7-character code. Every L7 row is assignable.
_Avoid_: 7th character
