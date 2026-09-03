## Context

See `proposal.md` — *Why*. What this adds is the state of the code the change lands in.

Five facts settle most of the design:

- **The sink mechanism is already generic.** `automation_pass._record_finding` looks a recorder up by step identifier and calls `recorder(product_id, finding.value)`; the mapping is `recorders: Mapping[str, SubCategoryRecorder]`, wired at the composition root as `{"lp.listing.007": _record_sub_category}` (`worker.py:139`). Nothing about it is sub-category-specific except the Protocol's parameter name. This change does not build a mechanism; it adds one fact to the one that exists.
- **A failed write already suppresses the recording.** `_record_finding` answers a boolean and the caller skips the step when it is false, so a kept finding can only ever accompany a write that succeeded. The delta's "keeping follows the write" is therefore a property the existing control flow already has, and what the requirement adds is that it must not be lost.
- **The two automated steps sit on opposite sides of the confirmation line, and this is what shapes the change.** `lp.listing.007` names no confirmer, so the pass records its outcome directly. `lp.strategy.006` names one, so its terminal proposals are *held* and the recording is made by the accept path (`automation_confirmation.py:283` passes a `record_outcome` of its own). A design that kept the finding only on the recording the pass makes would therefore deliver nothing for the compliance step — the step this whole line of work exists for. Verified against the live step set, not inferred.
- **The report's step entry carries the recording whole.** `launch_admin` reads `entry.progress` and takes `provenance.evidence` off it, so a finding stored as part of the recording travels to the page with no separate projection. The delta still states it as a report obligation, because relying on it silently is what `launch-instance`'s "a fact a consumer needs SHALL travel on the report" exists to prevent.
- **The Outcome cell is already a disclosure.** `launch.html:158-170` renders `step.evidence` inside `<details>`/`<summary>`, clamped to two lines, with a provenance line. The split has somewhere to go that does not cost a new interaction.

## Goals / Non-Goals

**Goals.** Two nullable columns, one registration change, one rendering change; the existing path for a recording with no finding untouched; both automated steps covered — the one the pass records directly and the one whose result waits for a confirmer.

**Non-goals, beyond the proposal's.**

- **No generic "structured evidence" abstraction.** There is exactly one shape here — a field, a value, a comment — because that is what `Success[T]` already carries plus the one fact the sink knows. A schema for arbitrary structured evidence would be designed against one example.
- **No change to `Success`/`Failure`.** The finding shape is `subcategory-advisor`'s and is deliberately universal. Adding a field name to it would put a catalog concept in every handler's return value, which is the opposite of what this change is for.

## Decisions

### A sink registration carries its field's name and wording

**Chosen** over a second mapping keyed by step, and over the handler naming its own field.

The composition root already knows that `lp.listing.007`'s finding goes to `record_sub_category`. It is the only place that knows, and the field's name is the same knowledge one word further on. So the registration becomes a small frozen value rather than a bare callable:

```
FindingSink(record=..., field="sub_category", reads_as="Sub-category")
recorders = {"lp.listing.007": FindingSink(_record_sub_category, "sub_category", "Sub-category")}
```

A parallel mapping (`finding_fields = {...}`) was rejected because two mappings keyed by the same thing drift: a step could acquire a sink and no field name, or a field name and no sink, and neither is a state worth being able to represent. Coupling them in one value makes both impossible.

The handler naming its own field was rejected on the rule `subcategory-advisor` sets and this change quotes in its delta: a handler reports a value and a comment, and where the value goes is not its business. It is also the direction that does not survive a second sink — two steps writing the same field would each have to spell it identically, with nothing checking they did.

`SubCategoryRecorder` keeps its name and its `sub_category: str` parameter for now. Widening it is `screen-for-hazard-categories`'s to do, when a second sink with a different value type actually exists; renaming it here would be a rename with no caller that needs it.

### The finding travels with the pending result

**Chosen** over keeping the finding only on recordings the pass makes.

The alternative was tempting and is what the first draft of this change specified: keep the finding where `_record_finding` already runs, and scope the change to outcomes the pass records directly. It is smaller, and it is wrong — `lp.strategy.006` names a confirmer, so its terminal proposals are held and its recording is made elsewhere. The mechanism would have shipped complete, passed its tests, and produced nothing on the page for the only step anyone wanted it for.

So `automated_step_results` gains the same nullable `jsonb` column, written when the result is held and read when it is accepted. Three paths, and each is stated in the delta:

- no confirmer, or a non-terminal outcome → the pass records, and carries the finding;
- confirmer and a terminal outcome → held with the finding, carried onto the acceptance recording;
- rejected → the recording carries none, because the member declined the fact it asserts.

The cost is a second column and a hop through the pending-result store. That is the price of the feature working for a confirmable step, and every step this is for is confirmable — which is the point of naming a confirmer in the first place.

### One `jsonb` column per store, not three

**Chosen** over `finding_field text` + `finding_value jsonb` + `finding_comment text`.

`launch_step_progress` gains `finding jsonb NULL`, holding `{"field": ..., "value": ..., "comment": ...}`.

Three columns say the same thing and cost three migrations the next time the shape moves — and it will move: `screen-for-hazard-categories` puts an array in `value` where `sub_category` puts a string. One `jsonb` absorbs that without a schema change. It also makes the absent case exactly one thing to check (`NULL`) rather than three columns that could disagree.

**`NULL` is the whole of "carries nothing", and `{"value": []}` is not it.** This is the distinction the delta insists on, and one column makes it structural rather than a convention: the row either has a finding or it does not, and an empty *value* lives inside a finding that exists. Every row written before this migration is `NULL`, which is the correct reading with no backfill.

### A sink names its field and how that field reads

The registration carries two strings, not one: the storage field (`sub_category`) and the wording an admin reads (`Sub-category`). The first is what is kept on the recording and what a later step would match on; the second is what the page renders.

They are separate because they answer to different readers and change for different reasons. A column is renamed by a migration; a wording is changed because it read badly. Rendering the storage identifier would put the page's newest and most prominent fact on screen as a snake_case token, in a capability that already requires its outcome vocabulary be rendered "as the words an admin uses rather than as those tokens".

Where a sink supplies no wording the field's own name is rendered — a fact rendered awkwardly beats a fact not rendered, which is this surface's standing rule.

### The split leads the cell; the evidence stays under it

The summary renders the result and the comment; the disclosure keeps the verbatim evidence and the provenance line it already has.

This is what lets the delta require both "the result leads with the field and value and nothing else" and "the verbatim evidence is still rendered" without contradiction. It also resolves a tension that would otherwise appear in `screen-for-hazard-categories`: the compliance screen renders its citation of the screened categories into its produced text, and a cell that showed only the finding would drop that citation from the page — the one place a narrowed screen was supposed to leave a trace.

The clamp stays. A two-line clamp over "field: value" plus the first line of a comment is a better two lines than the same clamp over a paragraph, which is most of the point.

### Treatment carries the distinction, colour reinforces it

The result and the comment get different elements with different classes, and the requirement is stated over the rendered response so a test can assert it. Colour comes from `vocabulary.css` tokens — `--danger-ink`/`--danger-rule`/`--danger-wash` exist with dark-mode variants, and a positive counterpart is added if none exists.

**Colour alone is not the distinction**, for two reasons the delta states and one it does not: this project's admin surfaces already carry state by treatment rather than by colour alone (`launch-admin`'s outcome-tag requirement is explicit about it), colour-blind readers exist, and a token that has not been given a dark-mode value renders as something arbitrary in one theme. Structure — separate blocks, a rule, or a label on the comment — is what actually carries it.

**The marker names are specified; the appearance is not.** `finding-result` and `finding-comment` are named in the delta because a test author works from the delta before any implementation exists, and a contract a test asserts against cannot be left to be guessed. What those markers then *look like* — spacing, weight, rule, which token — is a visual question, settled by running the admin surface and looking at it in both themes. Deferring the appearance is a deferral; deferring the contract would have been a skipped decision.

The markers are necessary and not sufficient, and the delta says so: two elements carrying two class names differ in the response even when the stylesheet distinguishes them by `color` alone, which is exactly what the accessibility clause forbids. The stylesheet rule that carries the structural difference is its own task, and the page carries no styling of its own — `launch-admin` forbids that.

## Risks / Trade-offs

**A `jsonb` column invites arbitrary shapes.** → The only writer is `_record_finding`, which constructs it from a `FindingSink` and a `Success`. Nothing accepts a caller-supplied blob, and the row mapping validates the three keys on read.

**Keeping the comment duplicates text already inside `evidence`.** → Accepted, and deliberate. They are different records: `evidence` is what a member was shown, and must not change when rendering changes; the retained comment is structured and may be rendered differently over time. Deriving one from the other is what would couple them.

**The rendering could regress the common path.** → Every recording that carries no finding must render byte-for-byte as before. That is a stated scenario and it covers the great majority of rows, `lp.strategy.006`'s existing 25 among them.

**`lp.listing.007` starts rendering something nobody has reviewed.** → Its finding has been written to products since August and shown on no page, so this is the first time anyone sees it. That is the point, but it is worth expecting the sub-category values to look worse than the compliance array will.

## Migration Plan

One Alembic revision adding `finding jsonb NULL` to **both** `launch_step_progress` and `automated_step_results`. No backfill: absent is the correct reading for every existing row in either table.

Deployment is the ordinary path — branch, PR, merge, deploy. Both columns are nullable and unread by any older code path, so the migration is safe to apply ahead of the code and safe to leave in place on a rollback.

Rollback is a revision dropping both columns. Nothing depends on the data they carry.

## Open Questions

- **Should the dossier's retained-results list get the same split?** It renders results too (`product-dossier`), and would benefit identically. Left out to keep this reviewable; worth doing once the treatment here has been looked at and settled, so both surfaces adopt the same one rather than two.
- **Should a held (pending) result carry the split into Slack?** A member deciding on a proposal arguably wants the fact separated from the prose more than a reader of the record does. Deferred with the dossier, and for the same reason.
