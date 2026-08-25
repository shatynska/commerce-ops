## Why

An authoring write rejected by validation renders its faults as prose at
page level. On a surface carrying fourteen inputs, an admin reading
*"step 'mg.listing.42' has execution mode 'automated' but no rule
policy"* has to translate a sentence back into which controls to touch —
and `mg.listing.42` names a step that was never persisted, because
`create_step` generates the identifier before validating
(`playbook_authoring.py:208`).

This was originally scoped inside `add-step-page` and carved out on
review: it applies to both authoring surfaces, not just the new one, and
it carries unresolved design questions that should not hold that page.

## What Changes

- Faults are attributed to the fields they concern, in three treatments,
  because the coherence rules do not all speak about one field:
  - a fault about **one field** marks that field;
  - a fault about a **combination** marks every field in the
    combination and states the combination is what is refused, because
    neither value is wrong alone and either is a valid thing to change;
  - a fault about the **step set** stays at page level with no field
    marked.
- The full fault list stays rendered whole. Attribution is additional,
  never a filter, and a fault the mapping does not recognise degrades to
  today's page-level rendering.
- A fault reported while creating no longer identifies the step by the
  identifier the write would have generated.

## Capabilities

### Modified Capabilities

- `playbook-admin`: gains a requirement that a rejected write names the
  fields its faults concern, with the three treatments above.

## Impact

Confined to `launch/infrastructure/driving/` — the mapping in
`playbook_admin.py` and the rendering in `_fields.html`.

## Open questions this change must resolve before its design is written

Carried forward from the `add-step-page` review, which found the
original plan's answers incomplete:

- **The mapping is twelve entries, not seven.** The original table
  omitted every timing-anchor fault — `_anchor_from_form`
  (`playbook_admin.py:175-193`) produces five: integer parse failures on
  `anchor_days`, `anchor_start` and `anchor_end`, `WindowAnchor`'s
  "end offset precedes start" re-wrapped from the domain, an
  unrecognised `Cadence`, and an unknown kind — and both discipline
  faults, one from `Discipline(...)` in the create route
  (`playbook_admin.py:435`) and one from `StepDefinition.__post_init__`
  (`launch_playbook.py:291-300`). The window start/end fault is itself a
  *combination*.
- **Twelve entries crosses the threshold** the original design set for
  promoting to structured faults in the domain
  (`Fault(fields=..., message=...)`). That trade-off must be re-decided
  on the real number, not the underestimate — noting it would change
  `InvalidPlaybookError`, whose shape is shared with
  `access/domain/principals.py`.
- **"Marks the field" names no observable.** It must be stated at
  behaviour level — what a response body shows — or the test author,
  who works from the specs and not the implementation, has nothing to
  assert.
- **The "combination is what is refused" statement has no source.** The
  rendered text is the domain's prose, which names a value
  (*"is classified 'prohibited-tactic' and cannot block its gate"*).
  Either the mapping carries adapter-authored message text, or the
  requirement rests on the shared grouping rather than on new words.
- **Combinations can overlap.** `hazard=prohibited-tactic` plus
  `binding=lesson` plus `blocking=yes` fires two rules that both mark
  `blocking` (`launch_playbook.py:435-445`). The rendering must be
  defined.
- **Stripping the generated identifier has no mechanism** that respects
  the untouched-application-layer constraint: the identifier is
  generated inside `create_step` and is not on the exception, and
  `AUTHORED_NAMESPACE` is not exported from `launch/application/`. The
  workable adapter-only argument is that the persisted set is coherent
  by construction, so any step-level fault a create reports concerns the
  submitted step — but set-level faults can legitimately name other
  steps, so blanket stripping is wrong.
- **A pre-existing defect sits next to this work**, out of scope unless
  deliberately adopted: `_authorable_fields` (`playbook_admin.py:226`)
  discards accumulated enum faults when `_anchor_from_form` raises
  first, so a submission wrong in both ways reports only the anchor.
