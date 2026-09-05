# Test manifest — `share-the-ordered-html-harness`

Written by the test-writing pass, before any of the change's implementation
tasks were performed. **Not an artifact the OpenSpec schema knows about**: it
does not appear among `openspec instructions apply`'s context files and has to
be read on purpose.

**This pass is additive only. It adds tests and never subtracts.** It wrote one
parked test file and this manifest. No existing test was edited, deleted or
disabled; `tests/support/html.py` is untouched; none of the eleven migrating
files was touched; nothing under `src/` was read, written or imported.

Baseline commit: **`0df7b9e`** (`docs(openspec): propose
share-the-ordered-html-harness`), which is also `HEAD` on this branch.

## Why almost nothing was derived

`<changeRoot>/.openspec.yaml` sets `skip_specs: true` and the change carries
**no delta specs**. There are therefore **zero `#### Scenario:` blocks** to
enumerate, and zero to account for — the count this pass owes is `0 = 0`. That
is the exemption `AGENTS.md` — *Test design before implementation* — states in
advance:

> A change that declares it carries no specification deltas has none to derive
> from and owes no new tests; what it owes is that the existing suite stays
> green.

`proposal.md` — *Modified Capabilities* restates it and adds the change's own
invariant: **the collected count outside `tests/unit/support/` does not move,**
and the assertion-identity multiset does not move either. So deriving a broad
suite here would not be thoroughness — it would break the invariant the change
is verified by. Nothing was derived beyond the single target `tasks.md` 3.2
plans, which must live under `tests/unit/support/`.

Absent delta specs **together with** the `skip_specs: true` marker is the
exempt route, not a blocked dispatch. Both were read at
`<changeRoot>/.openspec.yaml` and `<changeRoot>/` — never inferred.

`specsRoot` was not needed: the change carries no `MODIFIED`, `REMOVED` or
`RENAMED` delta because it carries no delta at all, so there is no existing
requirement to compare against. Unlike its predecessor, this change's design
turns on no existing capability either — its constraints are properties of
`tests/support/html.py` and of the eleven local parsers, both of which sit
inside the dispatched test-path glob.

## What was written

**One file, 14 test functions, under `tests/unit/support/`** — the deliberate
exception to the tier layout, whose subject is the harness itself.

It is **parked** at

```
<changeRoot>/pending-tests/test_html_document_order.py.pending
```

and task 3.2's commit `git mv`s it into place at

```
tests/unit/support/test_html_document_order.py
```

dropping the `.pending` suffix, in the same commit that adds `document_order`
to `tests/support/html.py`. See *Where this file lives*, below, for why it
cannot land before that.

Once in place, run it with:

```
uv run pytest tests/unit/support/test_html_document_order.py
```

### `tests/unit/support/test_html_document_order.py` — 14 tests (serves 3.2)

Task 3.2's list is treated as the floor. Rows 6, 10, 11 and 14 are beyond it and
are derived from `design.md` Decision 1's stated semantics and constraint 1;
each is marked in *Assertion classification*.

| # | Test (runner-selectable) | Serves | First run |
|---|---|---|---|
| 1 | `tests/unit/support/test_html_document_order.py::test_the_document_root_answers_zero` | 3.2, Decision 1 — the root is `0` | fails, absent target |
| 2 | `…::test_the_first_element_answers_one` | 3.2, Decision 1 — the first element is `1` | fails, absent target |
| 3 | `…::test_siblings_ascend_in_document_order` | 3.2 — siblings ascend | fails, absent target |
| 4 | `…::test_a_descendant_answers_after_its_ancestor` | 3.2 — a descendant follows its ancestor | fails, absent target |
| 5 | `…::test_two_equal_siblings_answer_distinct_positions` | **3.2's named trap**; constraint 2 — `is`, never `==` | fails, absent target |
| 6 | `…::test_an_equal_cell_in_an_earlier_row_does_not_claim_the_answer` | constraint 2, the non-sibling shape (derived) | fails, absent target |
| 7 | `…::test_a_void_element_takes_a_position` | 3.2; Decision 1 — `<br>` via `handle_starttag`, never pushed | fails, absent target |
| 8 | `…::test_a_self_closing_element_takes_a_position` | 3.2; Decision 1 — `<span/>` via `handle_startendtag` | fails, absent target |
| 9 | `…::test_a_text_run_takes_no_position` | Decision 1 — `_open` increments per *element* (derived) | fails, absent target |
| 10 | `…::test_every_element_answers_its_index_in_the_shared_pre_order_walk` | Decision 1 — "exactly as `elements()` yields them" (derived) | fails, absent target |
| 11 | `…::test_the_answer_is_counted_from_the_document_root` | Decision 1 — "climb `parent` to the root" (derived) | fails, absent target |
| 12 | `…::test_a_detached_node_answers_zero` | **3.2's explicit pin**; Decision 1 | fails, absent target |
| 13 | `…::test_a_detached_nodes_child_answers_one` | **3.2's explicit pin** — "not 0 throughout" | fails, absent target |
| 14 | `…::test_the_node_type_gains_no_order_field` | constraint 1 — nothing is added to `Node` (derived) | see below — **would pass today** |

## The ordering reality, and how it was handled

**13 of the 14 fail in the same state: the target does not exist.**
`ai-toolkit:testing`'s second failure state — the assertions never executed, so
whether they are any good is still unverified. None is in the first state (code
ran, wrong value).

The failure is at **collection**, not at assertion. Measured by placing the file
at its final path, running, and removing it again:

```
ImportError: cannot import name 'document_order' from 'tests.support.html'
!!!! Interrupted: 1 error during collection !!!!
```

`uv run mypy .` over the same placement reports **exactly one error, and no
other file's result moves**:

```
tests/unit/support/test_html_document_order.py:49: error: Module
  "tests.support.html" has no attribute "document_order"  [attr-defined]
Found 1 error in 1 file (checked 536 source files)
```

**Test 14 is the one exception, and it was investigated rather than recorded as
coverage.** `ai-toolkit:testing`'s fourth state — a first-run pass — is an alarm
where the target is absent. Here it is not that: `Node` already exists, so test
14 sits in the skill's *second situation* (the target already exists) and a pass
is its expected, meaningful result. It asserts that `Node`'s field tuple is
still `(tag, attrs, parent, children)` — the invariant `design.md` constraint 1
fixes and that `document_order` exists in order to preserve. It is a regression
pin, not evidence about `document_order`. In practice it will not run until the
import at line 49 resolves, because the collection error takes the whole module
with it.

Nothing was stubbed to make the tests execute. Creating `document_order`, or an
empty placeholder for it, so collection would succeed is writing implementation
and is the point at which this pass would have become one.

### What was validated instead, since the assertions could not be

Per `AGENTS.md` — *An expression harvested out of a file must be validated by
evaluating it* — every arrange expression in the file was **executed** against
the real `tests.support.html` before the file was written, using the `PAGE`
literal extracted from the file itself rather than a retyped copy:

- `PAGE` parses to **17 elements** in the pre-order sequence `html, head, title,
  body, nav, a, a, main, h1, table, tr, td, td, br, img, span, p` — so the
  hard-coded integers 9, 12, 13, 14, 16 and the range `1..17` are read off the
  parser's own output, not off a reference implementation. **No implementation
  of `document_order` was written anywhere, including in scratch**; the expected
  integers come from `enumerate(elements(root), start=1)`, which is the shared
  walk `design.md` Decision 1 derives the numbering from.
- `<span/>` does **not** swallow the following `<p>` (16 then 17), confirming
  `handle_startendtag` never pushes — the premise test 8 rests on.
- The two `<td>` siblings satisfy `left == right` **and** `left is not right`,
  so test 5 genuinely exercises the trap rather than asserting it.
- `ROWS` yields `table, tr, td, tr, td` → the two cells are at 3 and 5.
- `RUN` yields `p, b` → the text run takes no position.
- `next(iter(elements(main))) is heading` holds, which is what makes test 11's
  answer of `9` (rather than `1`) the discriminating one.
- The detached `Node("div", {}, None)` with an appended child has
  `child.parent.parent is None`, so its chain reaches no `#document`.
- `uv run ruff check` and `uv run ruff format --check` over the parked file
  (via `--stdin-filename` at its final path): **clean**. One RUF015 finding was
  fixed in the parked file before this manifest was written.

## Assertion classification

The change carries no specification deltas, so **no assertion here is
`specified` in the delta sense.** Each instead traces to a planning artifact,
recorded per assertion rather than left implicit, or is marked `derived`.

| Assertion | Class | Traces to |
|---|---|---|
| The document root answers `0` | traceable | `tasks.md` 3.2; `design.md` Decision 1 |
| The first element answers `1` | traceable | `tasks.md` 3.2; Decision 1, citing `test_launch_detail_breadcrumb.py:466-472` |
| Siblings ascend | traceable | `tasks.md` 3.2 |
| A descendant answers after its ancestor | traceable | `tasks.md` 3.2 |
| Two equal siblings answer **distinct** positions | traceable | `tasks.md` 3.2 ("the `==`-vs-`is` trap"); `design.md` constraint 2 |
| The two equal siblings answer **12 and 13** specifically, not merely distinct | derived | No artifact fixes the integers. Asserted because "distinct" alone is satisfied by an implementation that is off by one for both, and the five read sites compare two answers so a uniform offset is invisible to them. |
| An equal cell in an **earlier row** does not claim the answer | derived | Not stated; 3.2 names only the sibling case. Asserted because `list.index`/`in` is the likeliest wrong implementation and a real table page is where it is met. |
| A void element takes a position | traceable | `tasks.md` 3.2; Decision 1 ("void and self-closing elements take a position exactly as `elements()` yields them") |
| A self-closing element takes a position | traceable | `tasks.md` 3.2; Decision 1 |
| A text run takes **no** position | derived | Not stated as a case. Follows from Decision 1's premise that `_open` increments once per *element* while `handle_data` appends a `Text`. Asserted because an implementation counting text runs answers plausibly and disagrees with every `.order` this change replaces. |
| Every element's answer equals its index in `elements()` | derived | Not stated as a test. It is Decision 1's own equivalence claim, asserted directly rather than sampled. |
| The answer is counted from the document root, not from the subtree handed in | derived | Not stated as a case; it is Decision 1's "climb `parent` to the root". Asserted because a walk that starts at the argument's subtree passes tests 3 and 4 unchanged. |
| A detached node answers `0` | traceable | `tasks.md` 3.2; Decision 1 |
| A detached node's child answers `1` | traceable | `tasks.md` 3.2 (explicitly required, "so the rule cannot be read as *a detached subtree answers 0 throughout*") |
| `Node`'s fields are still `(tag, attrs, parent, children)` | derived | Not stated as a test. `design.md` constraint 1 and `proposal.md` state that no field is added to `Node`; nothing else in the change would fail if one were. |

**Deliberately untested**, each with its reason:

- **`document_order` refusing a `Text`.** Decision 1 says it "takes `Node`,
  never `Text`". That is a typing statement, and `uv run mypy .` runs strict
  over the whole tree — the same mechanism `AGENTS.md` relies on for
  `_conforms`. A pytest assertion mimicking it would pin a runtime `TypeError`
  no artifact describes and no call site produces.
- **`Node.__eq__` raising `RecursionError` for two structurally similar nodes
  under different parents.** Found while validating this file (see *Findings*),
  and material to whoever implements 3.1 — but it is a property of `Node`, not
  of `document_order`, and asserting it would pin a pathology as a contract.
  Recorded in the file's docstring and here instead.
- **Memoisation, caching, or the cost of the walk.** Decision 1 rejects
  memoising as premature; asserting anything about it would design behaviour the
  change declines.
- **The 97 helper dispositions, the 30 constants, and all eleven migrations.**
  They are migrations, not behaviour. `tasks.md` §1's three instruments, §2.10's
  and §3.8's mechanical `def test_` check, and §5.1's assertion-identity
  multiset are what close them. A test per declaration would move the collected
  count outside `tests/unit/support/`, which is the one thing `proposal.md`
  commits will not happen.
- **The ten kept-local helpers.** Recorded keeps under `tasks.md` 4.1; they do
  not migrate, so the shared module has no contract to state about them, and
  their existing tests are untouched.
- **Everything else in `tests/support/html.py`.** `tree`, `elements`, `texts`,
  `all_text`, `attribute_text`, `classes`, `carries`, `element_hidden`,
  `element_disabled`, `inherited`, `ancestors`, `nearest`, `size`, `flat` are
  unchanged by this change. `document_order` is the only new function.

## Obsolete tests

**Not applicable — the change carries no `MODIFIED`, `REMOVED` or `RENAMED`
delta, because it carries no delta specs at all.** No requirement is superseded,
so no existing test can bear on superseded behaviour, and no search for bearing
tests was owed. Recorded with that reason rather than left as an empty list.

Three substantive notes, because "not applicable" does **not** mean "nothing
existing changes":

1. **160 local declarations across 11 files are deleted by this change**, and
   17 test files are edited. Those are *fixtures*, not tests: `design.md`'s
   strong non-goal is that **no line inside a `def test_` is touched**, which
   `tasks.md` 2.10 and 3.8 check mechanically and 5.1's assertion-identity
   multiset (6,612 / 238 / 759 / 172 over 2,192 functions in 332 files) checks
   again from the outside. If that multiset moves, an assertion changed and the
   change stopped being a migration. **No declaration was deleted by this pass.**
2. **The five `.order` read sites** — `_before_title` in
   `test_launch_detail_breadcrumb:630`, `test_launch_journal_page:718`,
   `test_playbook_admin_edit_create_breadcrumb:529`,
   `test_product_dossier_breadcrumb:439`, and `_rows_in_order:306` in
   `test_product_index_page` — are the tests most at risk, and the risk is
   **silent passing**, not failing. All five compare or sort two answers, so a
   `document_order` that is uniformly offset, or that locates by `==` and
   answers the first equal node, leaves them green. They are not obsolete, must
   not be edited, and are protected from the outside by tests 5, 6 and 11 above.
3. **The parked file is itself an ordinary existing test on any repeat pass.**
   If this pass runs again, it is bound by the additive-only rule like any
   other: replaced wholesale only through a fresh manifest, never edited to
   match an implementation that has since appeared.

## Where this file lives

It is **not** under `tests/unit/support/` yet. Naming an absent symbol aborts
collection of the entire commit tier — measured above, `Interrupted: 1 error
during collection` — so the `pre-commit` hook would block every commit,
including this manifest's own; and `uv run mypy .` is strict over the whole tree
with no excludes, so the file must sit where **neither** tool reads it.

It is parked at `<changeRoot>/pending-tests/` with a `.py.pending` suffix — the
convention `share-the-aggregate-fakes` set — and is tracked, so 14 tests do not
ride in a worktree nobody has committed. Task 3.2 `git mv`s it into place in the
same commit that adds `document_order`, which is the sequencing `tasks.md` §3
already prescribes (3.1 before 3.2), now with a second reason.

## Unresolved project questions

No channel exists to ask on, so each is recorded with the assumption taken and
the tests depending on it.

1. **The file's name.** The directory's convention is one file per shared type
   (`test_fake_step_store.py`); `document_order` is a *function* on
   `tests/support/html.py`, which the directory has no precedent for — no
   `test_html_*.py` exists today. **Assumption:** `test_html_document_order.py`,
   the exact name `tasks.md` 3.2 states. **Depends on it:** the path only.
2. **Whether the module-level fixtures should be public or `_`-prefixed.**
   `AGENTS.md` says `tests/support/` exports public names and call sites alias
   them, but says nothing about a *test* module's own constants; the neighbouring
   contract tests use both spellings. **Assumption:** public (`PAGE`, `ROWS`,
   `RUN`) for the constants and `_`-prefixed for the two helpers, matching the
   split in `test_fake_product_reader.py`. **Depends on it:** naming only; no
   assertion moves.
3. **Whether hard-coded absolute indexes are the house style, or relative
   comparisons are.** No artifact says. **Assumption:** absolute, because the
   five consumer sites are all *relative* comparisons and would not detect a
   uniform offset — so pinning the absolute numbering here is the only place it
   is pinned at all. **Depends on it:** tests 5, 6, 7, 8, 9, 10 and 11, all of
   which would still be meaningful (and weaker) if rewritten relatively.
4. **Whether the contract test may name integers derived from a fixture rather
   than from a stated requirement.** The eight local parsers are the de-facto
   specification of the numbering and `design.md` cites one of them by line, so
   the integers trace to code inside the test glob rather than to a spec.
   **Assumption:** acceptable here, and it is why *every* such integer was
   re-derived by executing the shared parser rather than read off a local one.
   **Depends on it:** the same seven tests.
5. **No `python`-stack skill question arose that `AGENTS.md` left open**, and
   both convention files were read (`CLAUDE.md` imports `AGENTS.md`; there is no
   third). Recorded so its absence is a finding rather than an omission.

## Baseline

**Full commit-tier baseline**, taken at `0df7b9e` before any test was written:

```
uv run pytest tests/unit tests/agents  ->  2569 passed in 73.54s
```

Zero pre-existing failures, so every failure reported above is attributable to
this pass. Collected counts:

| | at `0df7b9e` | after 3.2 lands | now, with the target absent |
|---|---|---|---|
| `tests/unit` outside support | 2,246 | **2,246 — must not move** | 2,246 |
| `tests/unit/support` | 87 | **101** | 87 (the file is parked) |
| `tests/agents` | 236 | **236 — must not move** | 236 |
| commit tier total | 2,569 | 2,583 | 2,569 |

**The expected figure for `tasks.md` 5.1 is `tests/unit/support` = 101**
(87 + 14). It is the only collected count allowed to move. Task 1.1's expected
2,569 / 87 is confirmed here at the branch point.

**`tests/integration` was not run by this pass.** It carries none of these 14
tests and nothing here reaches it; `tasks.md` 1.2 and 5.2 own that tier, and
`AGENTS.md`'s worktree trap (a skipped tier reports `Passed`) applies to them,
not to this pass.

Because the file is parked, the tier as it stands **is** the with-the-new-tests-
set-aside run — no `--ignore` was needed, and the 2,569 above is both the
baseline and the current state of the tree.

## Findings, reported rather than acted on

1. **`Node.__eq__` raises `RecursionError` on two structurally similar elements
   under different parents.** Comparing the two `<td>` in
   `<table><tr><td>same</td></tr><tr><td>same</td></tr></table>` recurses:
   `td == td` compares their differing `parent` rows, each row compares its
   `children`, which are the cells again. Observed directly:
   `RecursionError: maximum recursion depth exceeded`, ~1,000 frames.

   This **strengthens** `design.md` constraint 2 rather than contradicting it:
   an `==`-based `document_order` is not merely silently wrong on equal
   siblings — on an ordinary table page it crashes. Worth a line at 3.1, and
   worth knowing before writing any future query over `Node` that scans by
   value. Not fixed here; `Node` is out of this pass's remit and constraint 1
   forbids touching it.

2. **No instruction was found inside the change's artifacts directed at a test
   author** — nothing of the "skip this", "no tests needed", "already covered"
   kind. Recorded because such a line would have been a finding to report rather
   than something to act on.
