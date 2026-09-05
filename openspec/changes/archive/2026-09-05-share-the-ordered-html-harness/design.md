## Context

See `proposal.md` — *Why*. The state this design starts from:
`tests/support/html.py` exists, is imported by 20 files, and models one of the
three data shapes the suite's rendered-page tests use. Eleven files hold a
divergent shape that measurement says they do not use, or use in one expression.

Those eleven files declare **97 module-level helpers whose bare name matches one
in `tests/support/html.py`**, plus **30 module-level constants** —
`_VOID_TAGS`, `_HIDDEN_CLASSES`, `_HX_VERBS`, every one of them **equal by AST
comparison** to its shared counterpart (several differ in line formatting, so
they are not byte-identical and that word is not used of them). Deciding each helper's fate is the substance of this
change; the parser core is the easy part.

Three constraints shape everything below.

1. **`Node` is a `@dataclass` with value equality.** Twenty files depend on that
   form. `AGENTS.md` — *Declaration form is part of the contract* — says a
   shared type's dataclass-ness, `frozen`, `eq` and `__repr__` are part of what
   its users rely on. So the shape of `Node` is fixed for this change: nothing
   is added to it.
2. **Value equality also means `==` cannot identify a node, and comparing two
   is not even safe.** Two sibling `<td>` cells with the same text and
   attributes are equal (`==` true, `is` false). Worse, two structurally
   similar cells under *different* parents raise `RecursionError`: `td == td`
   compares the differing parent rows, each row compares its children, which are
   the cells again. Measured on
   `<table><tr><td>same</td></tr><tr><td>same</td></tr></table>` — an ordinary
   table page. So an `==`-based `document_order` is not merely silently wrong on
   equal siblings; on the pages these tests parse it crashes. Anything that
   locates a node inside its tree must compare with `is`.
3. **A file that imports shared names as `_`-prefixed aliases while keeping a
   local helper under a shared spelling owes the reader a stated reason at that
   declaration.** Before this change a file has no shared imports and the
   question does not arise; after it, it does. Decision 5 settles what
   discharges it.

## Goals / Non-Goals

**Goals:**

- One shared HTML harness for every file whose data model measurement shows it
  does not need.
- Document order answered by derivation, so the shared `Node` is untouched.
- Every one of the 97 helpers and 30 constants dispositioned explicitly, by a
  rule stated in advance rather than decided at each one.

**Non-Goals:**

- **No test function body changes.** Not one line inside a `def test_` is
  touched: no assertion, no locator, no needle, and no identifier. An earlier
  draft of this design proposed renaming ten kept helpers off their shared
  spellings and amended this non-goal to permit the resulting edits. Measured,
  those renames reach **92 sites, 56 of them inside test bodies, across five
  files** — and Decision 5 now rejects them for that reason among others. The
  non-goal is restored to its strong form because the change can hold it.
- Taking the six files this change records as keeps. Their reasons are in
  `proposal.md` — *What stays local*.
- Removing dead test helpers. Two of the keeps below execute zero times because
  their *callers* are unreachable; deleting them means deleting those callers,
  which is a different claim than this change measured.
- Fixing the `_carries` / `_attribute_text` / `_ancestors` divergence in the two
  files this change does not touch. That is a `docs/deferred-work.md` entry, per
  *Incremental development and scope control*.
- Any change under `src/`.

## Decisions

### 1. Document order is derived by one function, not stored on a field

`document_order(node: Node) -> int` returns the node's index in a pre-order walk
of the document it belongs to: climb `parent` to the root, then walk down
counting elements, matching the target **by identity**. The document root is
`0`, the first element `1` — the numbering the eight local parsers produce
(`test_launch_detail_breadcrumb.py:466-472`), so the five read sites keep their
exact meaning.

**The equivalence holds by construction, and the measurement corroborates it
rather than establishing it.** Decision 2 says execution can only ever veto a
*keep*, and this premise must be held to the same standard. In every one of the
eight parsers, `_open` increments the counter exactly once per element and
appends the node to its parent in the same call, so a node's counter value is
its position in the sequence of open events; `handle_endtag` only truncates the
stack and never reparents or reorders; and `handle_startendtag` routes through
`_open` as well, so void and self-closing elements take a position exactly as
`elements()` yields them. The sequence of open events over a tree built this way
*is* its pre-order traversal. The instrumented run — **11 files, 138 parses,
19,056 nodes, zero order, shape or text mismatches** — is what confirms no
parser deviates from that shape in practice.

**Why derived rather than stored.** A stored `order` requires a field on `Node`,
which changes `__eq__` and `__repr__` for the 20 files already importing it, for
the benefit of five expressions in five files.

*Alternatives considered.*

- **`precedes(a, b) -> bool`.** Fits four of the five sites exactly and reads
  better at them. It does not fit the fifth, `_rows_in_order`, which needs a
  sort key. Two functions where one serves both is a wider surface for no gain,
  and `document_order` composes into `precedes` at a call site in one
  expression.
- **`positions(root) -> list[Node]`, indexed at the call site.** Rejected on
  constraint 2: the natural call is `positions(root).index(node)`, and
  `list.index` compares with `==`. Siblings share a parent *object*, so tuple
  comparison short-circuits on identity rather than recursing, and two equal
  cells resolve to the first — silently, as a plausible integer.
- **Memoising the walk per root.** Rejected as premature. The one site inside a
  sort key runs over a 390-node tree with a handful of rows.

`document_order` takes `Node`, never `Text`: `Text` has no `parent` and no
position to climb from. A node whose `parent` chain reaches no `#document` is
its own root and answers `0`; its child answers `1`, which the contract test
pins so the wording cannot be read as "a detached subtree answers 0 throughout".

### 2. The disposition rule: each instrument is a veto in one direction only

Three instruments were run over the 97 helpers, and **no two of them agree**.

- **An AST comparison**, normalised for the helper's own name, its parameter
  names, its docstring and the `_` prefix on referenced names. It answers *are
  these the same code?*
- **A leaf-equivalence proof**: a pytest plugin wraps every one of the 97 and,
  on each call, compares the local result against the shared function's result
  over a converted twin of the same tree. It answers *did they agree on what the
  tier asked?*
- **Reading the source of every helper the AST comparison separates.** It
  answers *is there an input for which these differ?*

Each is wrong in a knowable direction, and the population contains a concrete
instance of each failure.

| instrument | fails by | instance |
|---|---|---|
| AST comparison | over-reporting difference — a rename or a respelling reads as divergence | `_tree` in three files differs only in its parameter name (`page`); `_all_text` in `test_members_admin_presentation_vocabulary` is `" ".join(t.text for t in _texts(node)).lower()`, a respelling of the shared function |
| leaf proof | over-reporting *sameness* — it sees only the inputs the tier supplies | `_carries` in `test_product_index_page` agrees on 4 of 4 calls while carrying a body that widens the shared reading to descendants |
| reading | being a judgement | — which is why it is used only to adjudicate what the AST comparison separated, never to survey |

**So the rule is:**

> A helper **migrates** only when the AST comparison says it is the same code,
> the proof records no disagreement, **and every helper its body calls also
> migrates**. Where the AST comparison separates them, the source is read and
> the question is *whether any input distinguishes the two* — not whether the
> text matches. A divergent branch means **keep**, whatever the proof recorded;
> a respelling with no distinguishing input means **migrate**, and the proof's
> agreement corroborates it.

**The callee clause is load-bearing in both directions.** The AST comparison is
normalised over the `_` prefix, so it reads a local callee and a shared callee
as the same name; "same code" is therefore asserted modulo callees. Checked
exhaustively over the 97: **no migrating helper's body references a keep**, so
the clause changes no answer in that direction.

**The converse occurs four times**, and each is recorded rather than assumed —
a keep whose body calls a helper that migrates out from under it:

| keep | calls, all migrating |
|---|---|
| `_attribute_text` — `test_members_admin_presentation_vocabulary` | `_all_text`, `_elements` |
| `_carries` — `test_product_dossier_page` | `_classes`, `_elements` |
| `_carries` — `test_product_dossier_established_by_automation` | `_classes`, `_elements` |
| `_carries` — `test_product_index_page` | `_classes`, `_elements` |

All six distinct callees are AST-identical to their shared counterparts, so no
keep's meaning moves. That is benign — but only by measurement, and one of the
four has **zero calls**, so for `_attribute_text` no instrument would have
reported a divergence had the shared `all_text` differed from the local one it
replaces. Task 4.1 requires the check be recorded at all four.

**Execution agreement licenses nothing on its own, and the reason is sharper
than "partial coverage".** `_texts` in
`test_playbook_admin_presentation_vocabulary` refuses to descend into a named
control. Instrumented over that file: **163 calls, 4 of which pass a subtree
that does contain a control — and 0 disagreements.** The divergent branch does
not merely go unexercised; it *executes* and still does not reach the result,
because the controls it skipped held no text runs. A rule phrased as "the proof
saw the branch, so the branch is proved" would have migrated it. Nothing short
of reading the source separates that function from the shared one.

Applying the rule to all 97: **87 migrate, 10 keep.**

### 3. The ten keeps, each with the input that distinguishes it

| file | helper | calls / disagreements | what distinguishes it |
|---|---|---|---|
| `test_product_dossier_established_by_automation` | `_all_text` | 127 / 127 | does not lowercase |
| `test_product_dossier_established_by_automation` | `_carries` | 7 / 0 | widens the class reading to descendants |
| `test_product_dossier_page` | `_all_text` | 17,609 / 14,349 | does not lowercase |
| `test_product_dossier_page` | `_carries` | 30 / 4 | widens to descendants |
| `test_product_index_page` | `_all_text` | 6,134 / 5,861 | does not lowercase |
| `test_product_index_page` | `_carries` | **4 / 0** | widens to descendants — the proof agreed by sample |
| `test_members_admin_presentation_vocabulary` | `_attribute_text` | **0 / 0** | joins *every* attribute value plus the element's text; shared filters to `class`, `title`, `aria-label`, `id`, `data-*` |
| `test_playbook_admin_presentation_vocabulary` | `_texts` | 163 / 0 | does not descend into a named control |
| `test_playbook_admin_presentation_vocabulary` | `_all_text` | **0 / 0** | does not lowercase |
| `test_playbook_admin_presentation_vocabulary` | `_element_hidden` | 1,475 / 12 | additionally treats `<input type="hidden">` as hidden |

Three of the ten were dispositioned with **zero or coincidental** execution
evidence, which is the whole reason the rule is composite. A declaration nothing
executes reports zero, never pass.

**The three zero-call keeps are kept, not deleted.**
`_attribute_text` has two call sites, both inside `_member_row`
(`test_members_admin_presentation_vocabulary.py:510`), **which has no callers of
its own**; `_all_text` in `test_playbook_admin_presentation_vocabulary` has one
call site the tier never reaches; `_all_text` in
`test_playbook_admin_edit_create_breadcrumb` has only its own recursion and is
fully dead — and that one is the sole zero-call helper the AST comparison calls
*identical*, so it migrates like any other.

### 4. `_texts` is two different situations, not one

The earlier draft of this design said `_texts` differs from the shared `texts`
"only in return type, in all three ORDINAL files". That was measured wrong. It
is two of three:

- `test_members_admin_presentation_vocabulary:365` and
  `test_admin_surface_navigation_and_assets:534` traverse exactly as the shared
  function does and differ only by returning `list[Text]` rather than
  `list[str]`. They **migrate**, and their consumers unbox.
- `test_playbook_admin_presentation_vocabulary:371` skips control subtrees by
  design, with the reason in its own docstring. It **keeps**.

The consumers that unbox are **two sites, both inside helpers**:
`test_members_admin_presentation_vocabulary.py:476` and
`test_admin_surface_navigation_and_assets.py:578`, each
`" ".join(t.text for t in _texts(x))` becoming `" ".join(_texts(x))`. The third
consumer in that file, `_all_text:375`, disappears — it migrates to the shared
`all_text` in the same step.

The nine references to `_texts` in `test_playbook_admin_presentation_vocabulary`
are untouched, because that file's `_texts` stays under its own name.

### 5. A kept helper is recorded, not renamed

Constraint 3 asks what tells a reader that `_carries` in a file full of shared
aliases is not `tests.support.html.carries`. An earlier draft of this design
answered *rename it*, giving each of the ten keeps a name that says what it does.
Measured, that answer is wrong on three counts.

- **Its cost is misstated by an order of magnitude.** The rename reaches **92
  sites, 56 of them inside `def test_` bodies, across five files** —
  `_all_text` alone is read at 25 sites in `test_product_dossier_page` and 17 in
  `test_product_dossier_established_by_automation`. An earlier draft claimed
  three test-body sites in one file. Roughly half the change's diff would be
  identifier churn in assertion lines, inside a change whose entire character is
  that nothing a test asserts moves.
- **It carries a silent-corruption risk the recorded note does not.** `_carries`
  is a proper substring of `_page_carries`, declared in two of the three files
  that would rename it, and of test *function names* such as
  `test_an_entry_carries_what_produced_it`. A textual rename corrupts those
  consistently at definition and call site, leaving the suite green and `mypy`
  silent.
- **It is not this repository's answer to this question.** `AGENTS.md` says
  *"Where the values or the form differ, the file keeps its own declaration and
  **the reason is recorded**"* — recorded, not renamed. Measured with
  `grep -rn '\*\*Kept local\*\*' tests/ --include='*.py'`: **four
  declarations carry that exact note**, and widening the pattern to any recorded
  keep wording (`Kept local`, `kept local rather`, `stays local`, `keeps its own
  declaration`) reaches **seven files, two of them in `tests/support/`**. The
  figure is small because the preceding slices had few keeps — but **none of
  them renamed anything**, which is the part that decides this.

So each of the ten keeps gets a `**Kept local**` docstring naming the shared
function it is not, the input that distinguishes them, and its measured call and
disagreement counts. That is what a reader hits at the declaration, it is the
convention four predecessors established, and it costs ten docstrings against 92
edits.

*The alternative is not dismissed as worthless.* A rename is strictly more
legible at the call site, and if these helpers had a fan-out of two or three it
would be the better answer. At a fan-out of 92 it buys legibility with exactly
the kind of diff this change exists to avoid producing.

### 6. The constants are aliased, not deleted and not left behind

All eleven files declare `_VOID_TAGS`, `_HIDDEN_CLASSES` or `_HX_VERBS` — 30
declarations in total, and **every one is equal to its shared
counterpart by AST comparison** — several differ in line formatting, so the
claim is value equality, not byte equality. They are part of the core and are aliased
(`from tests.support.html import VOID_TAGS as _VOID_TAGS`), not dropped.

**`Node` and `Text` are aliased the same way where they are still read**, under
each file's existing `_`-prefixed spellings, which is what the predecessor did
in its 20 migrated files (`from tests.support.html import Node as _Node`, at
`test_members_header_names_every_surface.py:92`). So **nothing is retyped**: the
**150** `_Node` / `_Text` references outside the harness helpers across the
eleven files — annotations on every file-specific helper, and **five
`isinstance` checks** — stand exactly as written. An earlier draft of `tasks.md`
asked for those annotations to be rewritten to `Node`/`Text`; that would be 150
edits to reach the same objects the alias already names.

**The rule is *alias what remains referenced*, not *alias everything that
migrated*.** An alias nothing reads is a `ruff` F401 error, so a blanket rule
would fail the phase it belongs to. Measured over the eleven files, taking the
migrating helpers' bodies as deleted:

| name | still read after migration |
|---|---|
| `_Node` | **11 of 11** — aliased everywhere |
| `_Text` | **8 of 11** — deleted in `test_product_surfaces_header_and_presentation`, `test_members_admin_presentation_vocabulary` and `test_admin_surface_navigation_and_assets`. The predecessor's ratio is the same shape: `Text as _Text` in 8 of its 20 |
| `_TreeParser` | **0 of 11** — its only references are its own `class` line and `_tree`, both deleted. It is never aliased |

Seven migrating **helpers** are in the same position and are likewise deleted
rather than aliased: `_flat` in `test_launch_detail_breadcrumb`,
`test_launch_journal_page`, `test_playbook_admin_edit_create_breadcrumb` and
`test_product_dossier_breadcrumb`; `_all_text` in
`test_playbook_admin_edit_create_breadcrumb`; `_carries` in
`test_members_admin_presentation_vocabulary`; and `_ancestors` in
`test_playbook_admin_presentation_vocabulary`. Each is read only by the parser
or by another migrating helper, so nothing survives to read it.

**This is not the "removing dead test helpers" non-goal.** That non-goal is
about a helper whose deletion would require deleting its *callers* — the two
zero-call keeps of Decision 3. These seven have no callers at all once the
migration lands, and leaving them would be leaving an unused import.

Both other options fail. Deleting them breaks the kept
`_element_hidden` in `test_playbook_admin_presentation_vocabulary`, which reads
`_HIDDEN_CLASSES`, and several file-specific helpers that read `_HX_VERBS` —
loudly, as a `NameError`, but only if a test reaches them. Leaving them in place
after their readers migrate strands a dead constant that `ruff` does not flag.

### 7. The migration order puts the no-API files first

Two phases, and the split is not cosmetic:

- **Phase A — the six files with a dead field.** They need nothing from
  `tests/support/html.py` that does not already exist. If Phase A is green, the
  core migration is proved independently of `document_order`.
- **Phase B — the five files that read `.order`.** Adds `document_order`, its
  contract test, and the five read sites.

Running A first means a Phase B failure cannot be confused for a core-migration
failure. Reversing them would put the new function under every file at once.

### 8. `mypy` is the seam, and it is expected to catch a half-migration

The predecessor recorded that a shared leaf handed a *local* `Node` matches
nothing and returns silently wrong results, with the suite staying green — and
that `mypy` caught it as an incompatible-argument error. That property is why a
leaf migrates only when the core migrates with it, and why each file is migrated
in one commit rather than helper by helper. `uv run mypy .` runs on every file,
not only at the end.

It is also the guard on the dropped fields: after migration `node.order` and
`fragment.ordinal` are attribute errors on the shared types, so a read this
change failed to find fails at the seam rather than silently. Attribute access
is never implicit, so a search plus `mypy` closes that question — no execution
licence in the style of `FakeHandlerRegistry.__iter__` is needed.

## Risks / Trade-offs

- **A helper the tier calls rarely gets a thin proof.** →
  `test_product_dossier_breadcrumb` parses once, over 51 nodes. Under Decision 2
  a thin proof cannot license a migration on its own anyway; the AST comparison
  carries that weight and the call count is recorded rather than rounded up.
- **A `**Kept local**` note is weaker than a rename at the call site.** →
  Accepted deliberately in Decision 5, with the fan-out measurement that made
  the trade. The note is the convention four predecessors set, and the two
  out-of-scope files with the same shadowing get the same treatment through
  `docs/deferred-work.md`.
- **`document_order` is O(tree) per call and one site calls it in a sort key.** →
  Measured against the sizes involved (390 nodes, a handful of rows) this is
  irrelevant, and the tier's runtime is checked before and after.
- **Eleven files, ten of them in one directory.** → Conflict risk with any
  concurrent work on the admin-surface tests, stated in `proposal.md` —
  *Impact*. Nothing else is editing them.
- **The leaf proof compares results, not exceptions.** → It records a raised
  exception on either side as a disagreement rather than propagating it, the way
  the predecessor's lockstep pairing did; a helper that raises where the shared
  one does not is a keep, not a crash.

## Migration Plan

1. Take the baselines (`proposal.md` — *Capabilities*) on the branch point.
2. Re-run all instruments on the branch and record the 97-row table; confirm
   87 / 10 or report the difference.
3. Phase A — the six dead-field files, one commit per file,
   `uv run pytest tests/unit tests/agents` and `uv run mypy .` on each.
4. Phase B — `document_order` plus its contract test, then the five read-site
   files.
5. Re-take every baseline. `tests/unit` outside support, `tests/agents` and
   `tests/integration` must be unchanged; `tests/unit/support` rises by the
   contract test's count; the assertion-identity multiset must not move.
6. Update `tests/support/html.py`'s docstring census, `AGENTS.md`,
   `docs/deferred-work.md` and `docs/proposed-change-order.md`.
7. `/code-review` over the diff before the change is called complete.

**Rollback** is per-file: each migration is its own commit and reverting one
restores that file's local parser without touching the shared module. Reverting
`document_order` requires reverting the five Phase B files first.
