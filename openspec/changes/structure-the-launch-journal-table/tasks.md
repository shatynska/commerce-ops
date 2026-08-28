## 1. Journal composition (`launch/application/journal.py`)

- [ ] 1.1 Add a `_KIND_LABEL` mapping covering all eight `JOURNAL_KINDS`, each a short noun (`Start`, `Outcome`, `Attestation`, `Approval`, `Gate Opened`, `Graduation`, `Date Moved`, `Refusal`), matched exhaustively (raise on an unmapped kind rather than falling through).
- [ ] 1.2 Add two shared helpers reading `details`: `_is_rejecting(occurrence)` for `details["decision"]`, used both by the existing `_what`/`_cause` wording and by the new category rule; `_is_blocked_outcome(occurrence)` for `details["outcome"] in {"Blocked", "Refused"}`. Both used by the category rule so the wording and the categorization can't diverge on what counts as a rejection or a blocked outcome.
- [ ] 1.3 Add a `_category` function: `admin` for `launch-date-moved`; `blocked` for `advance-refused`, a rejecting `gate-approval-recorded`, and a `step-outcome-recorded` with `_is_blocked_outcome`; `judgment` for `metric-attested` and an approving `gate-approval-recorded`; `progression` for everything else (`launch-started`, `gate-opened`, `launch-graduated`, and a `step-outcome-recorded` outside `_is_blocked_outcome`). Exhaustive match, same discipline as 1.1.
- [ ] 1.4 Add `label: str` and `category: str` fields to `JournalEntry`.
- [ ] 1.5 Wire both into `compose()`.

## 2. Read-model plumbing (`launch/infrastructure/driving/launch_admin.py`)

- [ ] 2.1 Add `label: str` and `category: str` to `JournalLine`.
- [ ] 2.2 Carry `entry.label` and `entry.category` through in `_journal_lines`, unchanged in spirit — still composes nothing, still sorts newest-first by `when`.

## 3. Template and shared styling (`launch/infrastructure/driving/templates/launch.html`, `shared/infrastructure/driving/static/vocabulary.css`)

- [ ] 3.1 Replace the journal `<ol>`/`<li>` markup with a `<table>`: columns for label, what, when, and cause.
- [ ] 3.2 Give each row the marker `category-` followed by its category value (`category-progression`, `category-judgment`, `category-blocked`, `category-admin`).
- [ ] 3.3 Add the four categories' visual treatment to `vocabulary.css`, keyed on the `category-*` markers (color/weight per category; `category-blocked` visually distinct from the rest) — not page-owned styling, per the shared-presentation rule this page's other markers already follow.
- [ ] 3.4 Keep the empty-journal statement unchanged (still renders when `launch.journal` is empty, table only rendered otherwise).

## 4. Tests

- [ ] 4.1 `tests/unit/launch/application/test_launch_journal_read.py`: extend or add cases asserting `label` and `category` per kind, including both `gate-approval-recorded` branches (approving → judgment, rejecting → blocked) and both `step-outcome-recorded` groupings (`Blocked`/`Refused` → blocked; `NotStarted`/`InProgress`/`Satisfied`/`NotApplicable` → progression).
- [ ] 4.2 Add a case asserting an unmapped/unknown kind raises rather than silently omitting a label or category (guards the exhaustive-match discipline from 1.1/1.3).
- [ ] 4.3 `tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py`: extend journal-rendering cases to assert `JournalLine.label`/`.category` are carried through from the composed entry.
- [ ] 4.4 Update/add a template-facing check (wherever the existing journal-list rendering is asserted) to confirm the journal renders as a table with a row per entry carrying its `category-*` marker, still newest-first, still stating "nothing is recorded" when empty.

## 5. Verification

- [ ] 5.1 `uv run pytest` — full `tests/unit` + `tests/agents` tier green.
- [ ] 5.2 `ruff check` / `ruff format --check` / `mypy` clean on the touched files.
