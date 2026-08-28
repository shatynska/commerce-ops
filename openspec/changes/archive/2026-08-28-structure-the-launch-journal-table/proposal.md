## Why

The launch detail page renders its journal as a bullet list of run-on sentences (`what` / `when` / `cause` spans in an `<li>`). The facts a reader actually scans for — what kind of thing happened, and whether it went well or was blocked — are buried mid-sentence rather than being their own scannable column, which makes a launch's history slower to orient in than it needs to be.

## What Changes

- Render the journal as a table on the launch detail page, columned by the facts already carried by each entry, instead of a prose bullet list.
- Add a short, fixed label per journal kind (e.g. `Outcome`, `Approval`, `Refusal`) in place of the raw kind string (`step-outcome-recorded`), composed once alongside the existing `what`/`cause` wording.
- Add a category to each composed entry, used to visually group the table by kind — **and, for two kinds, by a fact the occurrence's `details` already carries**, so that a negative outcome reads distinctly from ordinary progress rather than blending into it:
  - `gate-approval-recorded`: a rejecting decision categorizes as blocked; an approving one as judgment.
  - `step-outcome-recorded`: an outcome of `Blocked` or `Refused` categorizes as blocked; every other outcome (`NotStarted`, `InProgress`, `Satisfied`, `NotApplicable`) categorizes as progression.
- The four categories: Progression (`launch-started`, `step-outcome-recorded` outside its two blocked outcomes, `gate-opened`, `launch-graduated`), Judgment (`gate-approval-recorded` when approving, `metric-attested`), Blocked (`advance-refused`, `gate-approval-recorded` when rejecting, `step-outcome-recorded` when `Blocked` or `Refused`), Admin (`launch-date-moved`).

## Capabilities

### Modified Capabilities
- `launch-journal`: a read journal entry additionally carries a short kind label and a category, both composed at read time from the stored occurrence (the kind, and — for `gate-approval-recorded` and `step-outcome-recorded` — the `details` fact that distinguishes a negative outcome, already recorded); no new fact is stored, and existing entries gain the new label/category the same way they already gain improved wording.
- `launch-admin`: the launch detail page renders its journal as a table (columns for label, what, when, cause, and a category-driven visual grouping carried as a marker on each row) instead of a bullet list of composed sentences, and continues to render newest-first and to state plainly when a journal is empty.

## Impact

- `src/commerce_ops/launch/application/journal.py`: `JournalEntry` gains `label` and `category` fields; `compose()` gains the kind→label map and the category rule (kind, with the `gate-approval-recorded` and `step-outcome-recorded` exceptions keyed on `details["decision"]` / `details["outcome"]` respectively).
- `src/commerce_ops/launch/infrastructure/driving/launch_admin.py`: `JournalLine` carries the new fields through to the page; `_journal_lines` unchanged in spirit (still composes nothing, still sorts newest-first).
- `src/commerce_ops/launch/infrastructure/driving/templates/launch.html`: the journal section becomes a `<table>`; each row carries a category marker.
- `src/commerce_ops/shared/infrastructure/driving/static/vocabulary.css`: gains the four categories' visual treatment, per the shared-presentation rule the base `launch-admin` spec already holds — no page-owned styling.
- No schema or storage change: `launch_journal_entries` and `JournalOccurrence` are untouched: the label and category are read-time projections, matching how `what`/`cause` already work.
