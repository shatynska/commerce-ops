> Symbols are named without line numbers: the previous draft of this
> change carried a dozen and every one was stale by the time
> `redesign-step-fields` landed (design.md — Context).

## 1. Make the adapter's own faults carry their fields

Attribution is two-tier (design.md — *Attribution is two-tier*). These
eleven faults know their field where they are raised, so they carry it
structurally and no string is ever matched for them.

- [x] 1.1 Restructure `_anchor_from_form` so each integer input is parsed where its name is known, and the fault carries that name. Today all three are read inside one `try` and re-raised as `timing anchor: {exc}`, so which of `anchor_days`, `anchor_start` or `anchor_end` failed is unrecoverable by any mapping
- [x] 1.1a **Keep reading only the inputs the submitted anchor kind uses.** The archived requirement *A timing anchor offers only the inputs its own kind uses* has not-offered inputs still submitting, so a reconsidered kind discards nothing. Parsing eagerly would make a stale `soon` in a hidden Start box reject a write that succeeds today — a rule change this change forswears
- [x] 1.1b **Keep every failure wrapped in `InvalidPlaybookError`**, `WindowAnchor.__post_init__`'s `ValueError` included. `save_edit` catches only that type, so an unwrapped escape turns a rendered fault into a 500
- [x] 1.2 Keep the window `end precedes start` fault as a *combination* over `anchor_start` and `anchor_end`, not a parse failure — it already reads correctly and only needs its fields attached
- [x] 1.3 Have `_enum` attach the field name it was already given, and the create route attach `discipline` to the fault from `Discipline(...)`. Neither needs a lookup: both hold the name at the raise site
- [x] 1.3a Make fields a **required** argument of whatever carries a structural fault, so a new adapter fault cannot be raised without deciding them, and let mypy enforce it. A carrier defaulting to no fields would reintroduce the silent gap the two-tier split exists to remove — and unlike the text-keyed half, nothing else would catch it (design.md — Attribution is two-tier)
- [x] 1.4 Fix `_authorable_fields` dropping faults: build the timing anchor into the same accumulator as the enum faults, rather than assigning it before the `if faults: raise`. A submission wrong in both an enum and the anchor must report both
- [x] 1.4a **Gather the create route's discipline fault alongside the ones `_authorable_fields` collects**, rather than parsing it after that helper has already raised. Accumulate in the create route around the helper; do **not** give the shared helper a create-only discipline parameter, since the edit route calls it and has no discipline to parse — the discipline is create-surface vocabulary and belongs on the create route. Without this the rescoped "every fault the surface parses" guarantee is true on the edit surface and false on the create one — a create wrong in an enum and in the discipline still reports one fault — which is the defect the rescoping was meant to retire, not inherit (design.md — What "every fault" can and cannot mean)
- [x] 1.5 Write the adapter-level rejection tests this path has never had — `grep` finds no existing test matching `timing anchor:` or `not a recognised value`. Neither 1.4 nor 1.4a can be verified against a suite that does not exercise them. Cover both routes that reach these helpers, `save_edit` and `create`; the other three write routes do not call them

## 2. Tests derived from the delta specs

- [x] 2.1 Dispatch `ai-toolkit:openspec-test-writer` scoped to the two ADDED requirements' scenarios; the two new scenarios on the editing requirement — *Faults from different sources arrive together* and *A create wrong in a field and in its discipline reports both*, which is 1.4a's only derived coverage; and the new *A rejected create does not name the step it did not persist* scenario on the creation requirement. Every other scenario in the two MODIFIED blocks is reproduced unchanged and already covered
- [x] 2.2 Record the baseline: run `uv run pytest` and confirm the new tests fail for the stated reason, not for a missing import or fixture

## 3. The text-keyed half

Eleven attributed faults plus one recognised page-level fault, all
crossing from the domain or the application as prose. The eleven from
section 1 are already attributed and must **not** be added here — keying
them on text would reintroduce the fragility the two-tier split exists
to remove.

- [x] 3.1 Build the mapping for the eleven domain and application faults design.md inventories: three single-field, five step-level combinations, and the three roster/registry preconditions
- [x] 3.2 Give the gate-holding fault — a gate left with no active blocking step — an explicit entry classified **set-level with no fields**. It is not attributed, but it must be *recognised*: it is the one page-level fault an edit or a create can provoke, and without an entry the exhaustiveness check at 3.6 cannot tell "held by the criterion" from "fell through unmatched"
- [x] 3.3 Classify each fault step-level or set-level. This is the same split section 5 consumes, so it is built once and used twice
- [x] 3.4 Return, for each fault, the fields it concerns — empty where it concerns none — and leave the fault text as the write reported it. The one permitted mutation is section 5's identifier removal, applied after classification, never here. No adapter-authored message text: what says "these are refused together" is that one fault marks several fields
- [x] 3.5 Where more than one fault concerns a field, mark the field once carrying all of them. Do not let the first rule that names a field win
- [x] 3.6 Write the exhaustiveness test: provoke every rule an **edit or create** can provoke, assert each fault is either attributed or is the recognised page-level entry from 3.2, and that none falls through unrecognised. Do not attempt the seven faults no write can provoke — the four `_gate_sequence_faults` produces, `_gate_condition_faults`'s empty threshold description, duplicate-identifier, and `StepDefinition.__post_init__`'s unrecognised discipline (design.md — The inventory)
- [x] 3.7 Note in the test what it does not cover: a rule *added* later is not caught, only a rule reworded — and that the structural half of section 1 is exempt only because 1.3a makes fields a required argument. The requirement says so; the test should not imply otherwise

## 4. Rendering

- [x] 4.1 Render a marked field's faults adjacent to the control they concern, in `_fields.html`, so both authoring surfaces inherit it from one place
- [x] 4.2 Keep marking distinct from the partial's two existing "not offered" spellings — `disabled` on automation controls, `hidden` on anchor groups. Marking says a submitted value was refused; it must not change whether a control is offered
- [x] 4.3 Mark a control that is **not** offered the same as any other. The combination treatment guarantees this case: a `human` step carrying an automation brief marks `automation_brief`, which renders `disabled` in exactly that state (design.md — Marking is a third axis)
- [x] 4.4 Keep the full fault list rendered at page level on both authoring surfaces, unchanged. Attribution is additional, never a filter
- [x] 4.5 Render an unattributed fault exactly as today, at page level, so an unrecognised fault degrades rather than disappearing
- [x] 4.6 Confirm the discipline fault marks the discipline field on the create surface, and that nothing marks it on the edit surface, where the field renders as read-only text
- [x] 4.7 Leave `page.html` alone. Three write routes reject onto it and it carries no authorable form; the requirement binds the edit and create surfaces only, and list-level rejections keep rendering as they do

## 5. The generated identifier on a rejected create

- [x] 5.1 Remove the leading `step '<identifier>' ` from a **step-level** fault reported by a create, leaving the rest of the fault exactly as reported, using the classification 3.3 already built
- [x] 5.2 Leave set-level faults' identifiers intact: they may legitimately name steps that do exist
- [x] 5.3 Leave an **unrecognised** fault's identifier intact too — unrecognised is unclassified, and guessing would strip identifiers from faults naming steps the admin needs to look at
- [x] 5.4 Confirm no application-layer export was needed and `AUTHORED_NAMESPACE` is still unexported from `launch/application/__init__.py`
- [x] 5.5 Confirm the edit surface is unaffected — the step it names does exist, so its identifier is correct there

## 6. Verification

- [x] 6.1 Run `uv run pytest` and confirm the tests from section 2 now pass, with no previously passing test weakened, skipped or deleted
- [x] 6.2 Run `ruff check`, `ruff format --check`, `mypy`, and `import-linter` — confirm no new module-boundary violation
- [x] 6.3 Confirm `git diff` touches no file under `launch/domain/` or `launch/application/`, and none under `access/` — the whole point of the adapter-side decision
- [x] 6.4 Exercise both surfaces by hand: a single-field fault marks one control; a `human` step carrying an automation brief marks both kind and brief, the brief still un-offered; a gate-holding fault marks nothing and stays at page level; a rejected create names no generated identifier
- [x] 6.5 Confirm a retirement rejected from the list still renders exactly as it does today — attribution must not have leaked onto the step list
- [x] 6.6 Confirm the integration tier passes. It needs the local database migrated to head, which this project has already been bitten by; `alembic/env.py` reads `DATABASE_URL` from the environment only and never loads `.env`
