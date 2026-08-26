## Why

An authoring write rejected by validation renders its faults as prose at
page level. On a form carrying eighteen inputs, an admin reading *"step
'mg.listing.001' is automated and beyond draft (status 'active') but
carries no automation brief"* has to translate a sentence back into which
controls to touch — and on the create surface `mg.listing.001` names a
step that was never persisted, because `create_step` generates the
identifier before validating.

Two of the fault sources make the translation harder than reading alone
suggests:

- **The anchor's parse failures name no field at all.** All three integer
  inputs are read inside one `try`, and the fault is `timing anchor:
  {exc}` — `invalid literal for int() with base 10: 'soon'`. Which of
  `anchor_days`, `anchor_start` or `anchor_end` was wrong is not in the
  message, so no amount of mapping recovers it. The function has to be
  restructured to know what it was parsing.
- **Some faults never arrive.** `_authorable_fields` assigns
  `fields["timing_anchor"] = _anchor_from_form(form)` *before* its
  `if faults: raise`, so a submission wrong in both an enum and the
  anchor reports only the anchor. A change about showing every fault
  cannot leave a path that drops most of them.

This was originally scoped inside `add-step-page` and carved out on
review: it applies to both authoring surfaces, not just the create page,
and it carried unresolved design questions that should not hold that page.
`add-step-page` has since shipped, so the create surface it attributes
faults on now exists.

## What Changes

- Faults are attributed to the fields they concern, in three treatments,
  because the coherence rules do not all speak about one field:
  - a fault about **one field** marks that field;
  - a fault about a **combination** marks every field in the
    combination, because neither value is wrong alone and either is a
    valid thing to change;
  - a fault about the **step set or a gate** stays at page level with no
    field marked.
- The full fault list stays rendered whole. Attribution is additional,
  never a filter, and a fault the mapping does not recognise degrades to
  today's page-level rendering.
- **Attribution is two-tier.** Eleven faults are raised inside the
  adapter, which already knows the input it was reading, so they carry
  their fields structurally and no string is matched. The other eleven
  arrive as prose from the domain or the application and are matched on
  message text — that half alone is fragile, and it is the half where
  the coupling is real.
- **A test provokes every rule an edit or a create can provoke and
  asserts each fault attributes.** This is not an optional extra: the
  text-keyed half would otherwise stop matching silently on a reworded
  message and degrade to page level with nothing going red.
- **`_anchor_from_form` parses each input on its own**, so a bad integer
  says which box it came from.
- **`_authorable_fields` stops discarding faults**: the anchor is built
  into the same accumulator as the enum faults, and the create route's
  discipline joins it rather than being parsed after the raise — so a
  submission wrong in two ways reports both, on either surface.
- A fault reported while creating no longer identifies the step by the
  identifier the write would have generated.

## Capabilities

### Modified Capabilities

- `playbook-admin`: gains a requirement that a rejected write names the
  fields its faults concern, with the three treatments above, binding
  the two surfaces that carry the authorable form; gains a second
  requiring that no rule an edit or create can provoke goes
  unattributed by accident; and the existing guarantee that a rejection
  reports **every** fault is strengthened, scoped to the values the
  surface itself parses, with a scenario covering the path that
  currently drops them.

**The step list is deliberately out of scope.** Three of the five write
routes — retire, un-retire, status change and move — reject onto
`page.html`, which carries no authorable form for a fault to be
attributed against. Those rejections keep rendering exactly as they do.

`launch-playbook` and `playbook-authoring` are deliberately **not**
modified. No rule changes, no fault text changes, nothing about what a
write accepts.

## Impact

Confined to `launch/infrastructure/driving/` — the mapping and the
fault-gathering helpers in `playbook_admin.py`, and the rendering in
`_fields.html`, which both authoring surfaces include.

`page.html` is **not** touched: it renders the rejections of the three
write routes this change leaves alone.

## Decisions carried in from review

The `add-step-page` review found the original plan's answers incomplete,
and the field redesign has since moved the ground under them. Resolved:

- **Attribution lives in the adapter, not the domain.** The alternative
  — `Fault(fields=..., message=...)` replacing bare strings — is
  rejected because field names are adapter vocabulary the domain must
  not learn: it knows a step has a `timing_anchor`, not that a window
  anchor renders as two inputs called `anchor_start` and `anchor_end`.
  That `InvalidPlaybookError`'s shape is shared with
  `access/domain/principals.py` supports the conclusion but does not
  carry it.
- **But structured attribution belongs in the adapter too, wherever the
  field is already known.** Eleven faults are raised by
  `playbook_admin.py` itself, which holds the input name at the raise
  site, so those need no text matching at all. Only the eleven that
  cross a boundary as prose are matched on message text. This halves
  what the change's fragility applies to.
- **The count is twenty-two: eleven structural, eleven text-keyed.** The
  original estimate of twelve predated `redesign-step-fields`, which
  removed `binding`, `execution` and `rule_policy` and added rules keyed
  on `kind`, `status`, `automation_brief`, `handler` and `assignees`.
  `design.md` carries the inventory, along with one fault recognised and
  held at page level, seven that no write can provoke, and three that
  render on the step list rather than an authoring form.
- **"Marks the field" is stated as an observable** — what the response
  body carries — so the test author has something to assert.
- **The combination treatment rests on shared marking, not on new
  words.** The rendered text stays the domain's own prose; what says
  "these are refused together" is that the same fault marks each field.
  No adapter-authored message text.
- **Overlapping combinations are defined**: a field named by more than
  one fault is marked once and carries both.
- **Stripping the generated identifier has a mechanism now**, and it
  falls out of the attribution work rather than needing its own. The
  classification already separates step-level faults from set-level
  ones. A step-level fault reported by a *create* can only concern the
  step being created. `playbook-authoring`'s *Every write is validated
  as the playbook it would produce* makes the persisted set coherent by
  construction under every load-time rule — its scenario *What a write
  cannot persist, a load cannot see* states it — and that requirement's
  third paragraph scopes the two precondition rules to the steps a write
  touches, which for a create is the new definition alone. So the leading `step '<identifier>' ` is dropped
  there and left intact everywhere else, including on faults the surface
  does not recognise.
