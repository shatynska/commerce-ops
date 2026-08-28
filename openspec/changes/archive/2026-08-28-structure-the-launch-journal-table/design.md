## Context

See proposal.md for motivation. Two facts about the current shape matter for the approach:

- `JournalOccurrence` (stored) already carries every fact needed here — `kind` and, for the two kinds that fork by an outcome, `details["decision"]` (`gate-approval-recorded`, a closed `"approving"`/`"rejecting"` enum) and `details["outcome"]` (`step-outcome-recorded`, the domain's `StepOutcome` type name — `"NotStarted"`, `"InProgress"`, `"Satisfied"`, `"Blocked"`, `"Refused"`, `"NotApplicable"`). Nothing new needs to be persisted.
- `compose()` is already the one place where "how a kind reads" is decided, and the whole reason it exists is so that a wording improvement reaches every already-appended entry at read time (`launch-journal` spec, "An entry stores structure, never rendered prose"). The label and category belong there for the same reason `what`/`cause` do.

## Goals / Non-Goals

**Goals:**
- One label and one category per composed entry, both derived at read time, both centralized in `journal.py`.
- The category reflects what a reader scanning for trouble actually wants to know, not just the occurrence's kind in isolation.

**Non-Goals:**
- No new stored column, no migration. `LaunchJournalEntry`/`JournalOccurrence` are unchanged.
- No filtering or grouping UI (sorting by category, collapsing sections) — parked, per the exploration, for a later change.
- No change to `Slack` or any other journal consumer; only `launch_admin`'s table is in scope, though the label/category living in `journal.py` means another surface gets them for free later.

## Decisions

**Short label per kind, not the raw enum or a mechanical humanization.** Considered three forms: the raw `kind` string verbatim (zero-cost but reads as a log, and duplicates the `Kind` idea nowhere else); a mechanical kebab→Title Case transform (`Gate Approval Recorded` — no hand-authored table, but still verbose and redundant with the `cause`/`what` text sitting in the next column); and a short hand-picked noun per kind (`Outcome`, `Approval`, `Attestation`, `Refusal`, ...). Chose the third: a table's kind column is scanned as a category, and an 8-entry lookup table is cheap to hand-author and just as cheap to keep current if a ninth kind is ever added (already a migration, per `JOURNAL_KINDS`).

**Category is a function of `(kind, details)`, not `kind` alone — and the fork is applied to every kind that can carry a negative outcome, not only the one first considered.** `gate-approval-recorded` covers both an approving and a rejecting decision (`launch-journal` spec, "A rejecting approval is journaled too"); `step-outcome-recorded` covers a `Blocked` or `Refused` outcome as much as a `Satisfied` one. A category scheme that puts either kind of negative result in the same visual group as ordinary progress defeats the purpose of adding grouping in the first place — the whole point is to let a reader spot trouble without reading every sentence, and a blocked or refused step is at least as common a thing to be scanning for as a rejected approval. Review of an earlier draft of this design (which forked only `gate-approval-recorded`) flagged exactly this gap: the stated goal implied the wider rule, and leaving `step-outcome-recorded` unforked was an oversight, not a considered exclusion.

So the category rule inspects `details["decision"]` for `gate-approval-recorded` and `details["outcome"]` for `step-outcome-recorded`; every other kind's category is a pure function of `kind`. This mirrors a pattern `compose()` already uses (`_what` already branches on `details` per-kind), so it's not a new shape in this module, just two more branches instead of one.

Within `step-outcome-recorded`, only `Blocked` and `Refused` fork to `blocked`. `NotStarted` and `InProgress` are ordinary in-progress states, not trouble; `Satisfied` is the successful terminal state; `NotApplicable` is a deliberate skip, not a failure — none of the four reads as "something went wrong" the way `Blocked` (stuck on something outside itself) or `Refused` (recognised as a prohibited tactic) does.

**Four categories, not per-kind coloring.** Progression / Judgment / Blocked / Admin. Fewer, coarser buckets are what make a color-coded scan work — 8 distinct colors for 8 kinds would be as noisy as reading the sentence. The grouping:

| Category | Kinds |
|---|---|
| Progression | `launch-started`, `step-outcome-recorded` (outcome not `Blocked`/`Refused`), `gate-opened`, `launch-graduated` |
| Judgment | `gate-approval-recorded` (approving), `metric-attested` |
| Blocked | `advance-refused`, `gate-approval-recorded` (rejecting), `step-outcome-recorded` (outcome `Blocked` or `Refused`) |
| Admin | `launch-date-moved` |

**`JournalEntry` gains two fields (`label`, `category`), not a replacement of `what`/`cause`.** The composed sentence stays — the table's `Cause`/`What`-equivalent column still needs it — the label and category are additive columns for the table to key on, not a rewording of the existing composition.

**Category is exposed as a plain string enum-like value (`"progression"` / `"judgment"` / `"blocked"` / `"admin"`), not a CSS class name.** Keeps `journal.py` free of a presentation concern (CSS classes belong to `launch_admin.py`/the template); the page maps the category value to a literal marker per row, following the base `launch-admin` spec's own convention for presentation-carrying markers (`outcome-tag`, `state-<name>`, `narrowing-bar`): the row carries `category-<value>` — `category-progression`, `category-judgment`, `category-blocked`, `category-admin` — and `vocabulary.css` (the same shared stylesheet every other admin marker's styling lives in — base spec: "the pages' presentation comes from the shared admin vocabulary") gains the four categories' visual treatment keyed on those markers.

## Risks / Trade-offs

[A future ninth journal kind lands without updating the label/category maps] → both maps should be exhaustive matches (a missing kind raises rather than silently falling through), the same discipline `JOURNAL_KINDS`' check constraint already applies at the schema level — enforced in tests, not just by convention.

[The new `_KIND_LABEL`/`_category` maps raise on an unmapped kind, while the existing `_what` function instead falls back to a generic sentence (`"an occurrence of kind '{kind}' was recorded"`) — two different error-handling philosophies for the same theoretical case, in the same module] → accepted as-is rather than reconciled. The case is unreachable in production: `JOURNAL_KINDS`' check constraint on `launch_journal_entries` guarantees `kind` is always one of the eight mapped values, so neither path is ever actually exercised on an unmapped kind outside a test written to force it. Making `_what` raise too, to match, is a reasonable follow-up but out of scope here — this change adds two new maps, not a rewrite of the function it sits beside.

[Category logic drifts from the sentence wording — e.g. `_what`'s rejecting-decision text and the category's rejecting-decision check read `details["decision"]` differently, or similarly for the `Blocked`/`Refused` outcome check] → both already exist in `compose()`'s scope; two small shared helpers (`_is_rejecting(occurrence)` for the decision check, `_is_blocked_outcome(occurrence)` for the `Blocked`/`Refused` check) used by both the existing `_cause`/`_what` logic and the new category rule keep them from diverging, rather than duplicating the same string comparisons in two places.

## Migration Plan

No schema migration. Ship as one change: `journal.py` (label map, category rule, `JournalEntry` fields) → `launch_admin.py` (`JournalLine` carries the new fields) → `launch.html` (table markup, `category-<value>` row marker) → `vocabulary.css` (the four categories' visual treatment, keyed on that marker). No rollback concern beyond a normal revert — nothing is persisted, so nothing to unwind.
