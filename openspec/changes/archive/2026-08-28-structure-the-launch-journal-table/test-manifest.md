# Test manifest — `structure-the-launch-journal-table`

**Not an OpenSpec artifact.** This file is not read by `openspec instructions
apply` or any other OpenSpec tooling — it will not appear among that command's
context files. Whoever implements this change must read it on purpose, at
this path: `openspec/changes/structure-the-launch-journal-table/test-manifest.md`.

This pass is **additive only**: it wrote two new test files and edited
nothing that already existed. No existing test was edited, deleted, or
disabled, and no implementation code was written. Every test below is
expected to fail on an absent target unless stated otherwise; a passing test
noted below as "pre-existing behaviour, unaffected" is not evidence that this
change is implemented — it establishes only that the fact it asserts was
already true before this pass.

## Baseline

Full tier, taken before any test in this pass was written:

```
uv run pytest tests/unit tests/agents
```

**1472 passed, 0 failed** — branch `explore-journal-structure`,
`/home/shatynska/projects/commerce-ops-journal`, 2026-08-28.

After this pass (same command, with the two new files present):
**1474 passed, 12 failed** (1472 + 14 new tests = 1486; 12 of the 14 new
tests fail on the expected absent target, 2 pass because the fact they
assert — `what`/`when`/`cause` and newest-first ordering — was already
implemented before this change and is unaffected by it). No pre-existing
test's outcome changed.

`ruff check .`, `ruff format --check .` and `uv run mypy .` are clean across
the whole repository, including both new files.

## New test files

- `tests/unit/launch/application/test_launch_journal_categorization.py`
- `tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py`

## Scenario accounting

17 scenarios across the two delta specs. Every one is accounted for below,
exactly once.

### `launch-journal` — MODIFIED requirement *One launch's journal is
readable, most recent first* (13 scenarios)

| # | Scenario | Status |
|---|---|---|
| 1 | A launch's journal is read most recent first | **Uncovered by this pass.** Unchanged from the prior spec — this change adds nothing to ordering. Deliberately exercised only at the integration tier (`tests/integration/launch/test_launch_journal_live.py`), per `test_launch_journal_read.py`'s own documented reasoning (a fake journal that re-sorted would test the fake, not the repository's `ORDER BY`). |
| 2 | Entries naming the same moment report the later append first | **Uncovered by this pass.** Same reasoning as #1. |
| 3 | An entry reports what occurred, when, and what caused it | **Covered — pre-existing.** `test_launch_journal_read.py::test_an_entry_reports_what_occurred_when_and_what_caused_it`. Unchanged content; not rewritten. |
| 4 | An occurrence naming nobody reports the command as its cause | **Covered — pre-existing.** `test_launch_journal_read.py::test_an_occurrence_naming_nobody_reports_the_command_as_its_cause`. |
| 5 | An entry reports a label naming its kind | **Covered — new.** `test_launch_journal_categorization.py::test_an_entry_reports_a_label_naming_its_kind` |
| 6 | An entry reports a category | **Covered — new.** `test_launch_journal_categorization.py::test_an_entry_reports_a_category` |
| 7 | A rejecting approval categorizes as blocked | **Covered — new.** `test_launch_journal_categorization.py::test_a_rejecting_approval_categorizes_as_blocked` |
| 8 | An approving approval categorizes as judgment | **Covered — new.** `test_launch_journal_categorization.py::test_an_approving_approval_categorizes_as_judgment` |
| 9 | A blocked or refused step outcome categorizes as blocked | **Covered — new, exhaustive.** `test_launch_journal_categorization.py::test_a_blocked_or_refused_step_outcome_categorizes_as_blocked[Blocked]` and `[Refused]` |
| 10 | Every other step outcome categorizes as progression | **Covered — new, exhaustive.** `test_launch_journal_categorization.py::test_every_other_step_outcome_categorizes_as_progression[NotStarted]`, `[InProgress]`, `[Satisfied]`, `[NotApplicable]` |
| 11 | An out-of-scope launch reports an empty journal | **Covered — pre-existing.** `test_launch_journal_read.py::test_an_out_of_scope_launch_reports_an_empty_journal` |
| 12 | A launch with nothing recorded reports an empty journal | **Covered — pre-existing.** `test_launch_journal_read.py::test_a_launch_with_nothing_recorded_reports_an_empty_journal` |
| 13 | A product with no launch record reports an empty journal | **Covered — pre-existing.** `test_launch_journal_read.py::test_a_product_with_no_launch_record_reports_an_empty_journal` |

Plus one test **not** tied to a `#### Scenario:` block, so not counted in
the 17 above: `test_launch_journal_categorization.py::test_an_unmapped_kind_raises_rather_than_omitting_label_or_category`.
DERIVED from `tasks.md` 1.1/1.3/4.2 and `design.md`'s first
Risk/Trade-off ("A future ninth journal kind lands without updating the
label/category maps"), which both direct that the label map and the
category rule be matched exhaustively, raising rather than falling
through. This is dispatcher-directed coverage (the dispatch explicitly
called out "the exhaustive-match discipline… per tasks.md 1.1/1.3/4.2"),
not a scenario in either delta spec.

### `launch-admin` — MODIFIED requirement *A launch's detail page renders
its journal, newest first* (4 scenarios)

| # | Scenario | Status |
|---|---|---|
| 1 | An entry names what occurred, when, and what caused it | **Covered — new (revised fixture).** `test_launch_admin_journal_table.py::test_an_entry_names_what_occurred_when_and_what_caused_it`. See "Obsolete tests" below for why this is written fresh rather than left to the same-titled pre-existing test. |
| 2 | An entry's row shows its label and carries its category marker | **Covered — new, exhaustive over all four categories.** `test_launch_admin_journal_table.py::test_an_entrys_row_shows_its_label_and_carries_its_category_marker` |
| 3 | Entries render newest first | **Covered — new (revised fixture).** `test_launch_admin_journal_table.py::test_journal_entries_render_newest_first`. Same reasoning as #1. |
| 4 | An empty journal says so | **Uncovered by this pass.** Unchanged content, and unaffected by the entry-shape change this delta makes (the fixture constructs no entry at all). Already covered — pre-existing: `test_launch_admin_detail.py::test_an_empty_journal_says_so`. |

**Total: 17/17 scenarios accounted for.**

## Assertion classification

### `test_launch_journal_categorization.py`

- `test_an_entry_reports_a_label_naming_its_kind` — **specified**: label is
  non-empty, and is not the raw kind string (spec: "drawn from the fixed
  set of labels rather than the raw kind string"). **derived**: that the
  label is a pure function of kind (checked by comparing two same-kind
  entries with different, label-irrelevant details) — the spec says "a
  fixed set, one per kind" but does not spell out "function of kind alone"
  as an assertion; inferred from that phrase and from `design.md`'s
  Decision that the category rule is "a function of `(kind, details)`" and
  the label rule is even simpler (kind alone, per `tasks.md` 1.1's mapping
  keyed only by kind).
- `test_an_entry_reports_a_category` — **specified**: category is one of
  the four fixed values.
- The four fork tests (`test_a_rejecting_approval_categorizes_as_blocked`,
  `test_an_approving_approval_categorizes_as_judgment`,
  `test_a_blocked_or_refused_step_outcome_categorizes_as_blocked`,
  `test_every_other_step_outcome_categorizes_as_progression`) — **specified**
  throughout: both the positive assertion (categorizes as X) and the
  negative one (not Y) are stated directly in the delta spec's own
  scenario text ("categorized blocked, not judgment", etc.).
- `test_an_unmapped_kind_raises_rather_than_omitting_label_or_category` —
  **derived**, in full: no scenario states this; it comes from `tasks.md`
  and `design.md` as described above. **Deliberately untested**: the exact
  exception type, since the artifacts fix only that the maps must raise.

### `test_launch_admin_journal_table.py`

- `test_an_entry_names_what_occurred_when_and_what_caused_it` —
  **specified**: what/when/cause all present, per the (unchanged) scenario
  text.
- `test_journal_entries_render_newest_first` — **specified**: newest-first
  ordering, per the (unchanged) scenario text.
- `test_an_entrys_row_shows_its_label_and_carries_its_category_marker` —
  **specified**: the row shows the label; the row carries `category-`
  followed by the category, using the literal tokens the delta spec gives
  (`category-progression`, `category-judgment`, `category-blocked`,
  `category-admin`) — "the literal tokens are given because they are what
  a test is derived from". **specified** (from requirement prose, not a
  numbered scenario): the journal renders inside a `<table>` element — the
  requirement's own SHALL clause ("SHALL render the launch's journal as a
  table") is what this traces to, not a `#### Scenario:` block. **derived**:
  that a row carries *only* its own category's marker, not another
  category's marker too (`_carries_marker` checked negatively for the
  other three) — the spec states what a row must carry, not what it must
  not; the negative check guards against a page marking every row
  identically and this assertion happening to pass by coincidence.

## Obsolete tests

**Applicable** — the `launch-admin` delta is MODIFIED, and its sibling
`launch-journal` delta (also MODIFIED) changes the shape of the entry that
composes `JournalLine` (adds `label`/`category`). Two pre-existing tests in
`tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py`
model the entry shape this change supersedes. Both are **candidates for
human confirmation** — not deleted or edited by this pass.

1. `tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py::test_a_journal_entry_names_what_occurred_when_and_what_caused_it`

   Superseded by: `launch-admin`'s MODIFIED requirement *A launch's detail
   page renders its journal, newest first*, together with `launch-journal`'s
   sibling MODIFIED requirement that adds `label`/`category` to every
   composed `JournalEntry`.

   Evidence: the fake entry is built (lines ~1696–1703) as
   `type("_Entry", (), {"what": occurred, "when": when, "cause": cause, "kind": "approval"})()`
   — no `label`, no `category`. `tasks.md` 2.2 directs `_journal_lines` to
   carry `entry.label`/`entry.category` through into `JournalLine`; once
   implemented, an entry object lacking those attributes raises
   `AttributeError` the moment the page tries to read them, which this
   fixture would trigger.

2. `tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py::test_journal_entries_render_newest_first`

   Superseded by: the same delta pair as above.

   Evidence: the fake entries are built (lines ~1744–1753) as
   `type("_Entry", (), {"what": mark, "when": moment, "cause": "a recorded outcome"})()`
   for each of three marks — carrying none of `kind`, `label`, `category`.
   Same `AttributeError` risk as above.

`test_an_empty_journal_says_so` in the same file is **not** flagged: it
constructs no entry at all (`_journal` returns `()`), so nothing about the
entry-shape change touches it.

## Unresolved project questions / INVENTED items needing confirmation

None of these block the pass; each is an assumption a test depends on,
recorded so the implementer or reviewer can confirm or correct it.

1. **The exact wording of the eight `_KIND_LABEL` values is not
   asserted.** `design.md` explicitly declines to fix exact label wording
   (it gives examples — "Outcome", "Approval" — not a binding set), while
   `tasks.md` 1.1 gives a specific literal set (`Start`, `Outcome`,
   `Attestation`, `Approval`, `Gate Opened`, `Graduation`, `Date Moved`,
   `Refusal`). Since the dispatch instructs deriving strictly from the
   delta specs' scenarios and the scenario itself only states "a short
   label… drawn from the fixed set… rather than the raw kind string",
   `test_an_entry_reports_a_label_naming_its_kind` asserts non-emptiness,
   non-identity with the raw kind, and consistency per kind — not the
   literal words. If the implementer intends the exact `tasks.md` 1.1
   wording to be load-bearing (e.g. rendered verbatim in the admin
   table), a stronger test asserting those literal strings would need to
   be added separately; this pass does not add it, to avoid asserting an
   INVENTED value against a spec that deliberately leaves it open.

2. **Whether the unmapped-kind exhaustive-match raises via an exception
   propagating out of `read_launch_journal`, versus some other observable
   (a logged error with a fallback value, for instance).** `tasks.md`
   1.1/1.3 says "raise… rather than falling through", and `read_launch_journal`
   at review time calls `compose()` directly with no exception handling
   around it (confirmed by reading `use_cases.py`), so raising there
   should propagate. `test_an_unmapped_kind_raises_rather_than_omitting_label_or_category`
   asserts this via `pytest.raises(Exception)` — deliberately broad, since
   no artifact fixes the exception type. If the implementation instead
   catches and logs (mirroring `_journal`'s append-failure containment),
   this test's premise would need correcting.

3. **Marker representation** (`_attribute_tokens`/`_carries_marker` in
   `test_launch_admin_journal_table.py`): INVENTED as a token among
   `class`, `id`, or a `data-*` attribute, mirroring how
   `test_launch_admin_detail.py` reads `outcome-tag`/`state-*`. If the
   implementation instead expresses `category-<value>` some other way
   (e.g. only as inline `style`), this locator needs correcting — flagged
   in the new file's own docstring and at the helper.

4. **Row representation** (`_journal_row` in the same file): INVENTED as
   a literal `<tr>` ancestor of the element holding an entry's unique
   `what` text. The requirement text says "table" and "row", which this
   reads as literal `<table>`/`<tr>` markup; a page expressing rows some
   other way (e.g. `<table>` of `<div>` "rows") needs this corrected — the
   locator fails loudly by name (`pytest.fail`) rather than silently
   reading the wrong element, so a fixture correction here does not require
   guessing what to correct it to.

No project-convention question was unanswered by `AGENTS.md`/`CLAUDE.md` —
both name the test command, the test-path glob, the three-tier layout, and
the `uv run pytest` invocation, and this pass follows all four. No
stack-specific skill beyond `python` applies (no LangGraph, Terraform,
Ansible, or bash content is under test here).

## What the implementation step must make pass

Once `journal.py`, `launch_admin.py`, `launch.html`, and `vocabulary.css`
are implemented per `tasks.md`, every test in both new files listed above
must pass, in addition to the full pre-existing suite remaining green
(`uv run pytest tests/unit tests/agents`, plus `tests/integration` at
push time per this project's tiering). The two flagged pre-existing tests
in `test_launch_admin_detail.py` are the implementer's decision to make —
this pass does not alter them.
