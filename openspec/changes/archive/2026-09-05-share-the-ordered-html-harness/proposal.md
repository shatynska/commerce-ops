## Why

`share-the-unit-test-harness` (archived 2026-09-04) hoisted the hand-rolled HTML
parser out of the rendered-page tests. Its task 3.1 found that the 37 files
carrying one did not carry the *same* one, and classified them by the data model
their parser builds:

| model | shape | files |
|---|---|---|
| STANDARD | `Node(tag, attrs, parent, children)` + `Text(text)` | 25 |
| ORDERED | `Node(…, order, children)` + `Text(text)` | 8 |
| ORDINAL | `Node(tag, attrs, parent, children)` + `Text(ordinal, text)` | 4 |

It migrated 20 of the 25 STANDARD files and left 17: the 12 ORDERED and ORDINAL
files, because *"they track document order, which the shared queries do not
model"*, and 5 STANDARD files that *"differ in `_flat` or the parser's
`handle_data`"*. Both reasons are recorded, at the task and again in
`tests/support/html.py`'s own docstring.

**That classification was made by reading the data model. Run instead, six of
the twelve turn out never to read the field they were kept for.**

* Three of the eight ORDERED files — `test_product_dossier_page`,
  `test_product_dossier_established_by_automation`,
  `test_product_surfaces_header_and_presentation` — declare `order: int`,
  assign it in `_open`, and **read it nowhere**. `order` is written and never
  looked at.
* Three of the four ORDINAL files —
  `test_members_admin_presentation_vocabulary`,
  `test_admin_surface_navigation_and_assets`,
  `test_playbook_admin_presentation_vocabulary` — declare `ordinal: int` on
  `_Text`, assign it in `handle_data`, and **read it nowhere**.

`.order` is read at exactly **five sites in five files** and `.ordinal` at
exactly **one file**. The other six carry the divergent model by copy-paste, and
were held back by a classifier that saw the field rather than its use. This is
the method lesson the last four slices each recorded — reading finds candidates,
running decides — arriving once more.

**And this change qualifies it.** Running decides *what the tier asked*, which
is not the same as what a function is. `design.md` Decision 2 states the
qualification and the population contains the instance that forces it.

## What Changes

**Document order is derivable, and this was proved by execution, not argued.**
A plugin wrapped `_tree` in all eight ORDERED files across the commit-time tier
and, on every parse, compared each node's stored `.order` against its index in a
pre-order walk of the same tree, and compared the whole local tree — tags,
attributes, children, text runs — against the tree `tests.support.html.tree`
builds from the same HTML:

```
11 files · 138 parses · 19,056 nodes
order mismatches 0 · shape mismatches 0 · text mismatches 0
```

The order comparison applies to the eight files that carry `order`; the tree
comparison covers all eleven, so the three ORDINAL parsers are proved by the
same named instrument rather than resting on a leaf row.

Every tree construction in those files goes through `_tree` — every
`_TreeParser()` call site sits inside it — so the wrapper saw every parse the
tier performs. And the equivalence holds *by construction*, which is what
licenses it: `_open` increments once per element and appends in the same call,
`handle_endtag` only truncates the stack, and `handle_startendtag` routes
through `_open`, so the sequence of open events over such a tree is its
pre-order traversal. The run corroborates that no parser deviates in practice.
Storing the index was never necessary; a query can derive it.

So the change:

- **Adds one function to `tests/support/html.py`: `document_order(node) -> int`**,
  the node's position in a pre-order walk of the document it belongs to, found
  by climbing `parent` to the root and walking down. **No field is added to
  `Node`.** That matters: `Node` is a `@dataclass`, so a new field would change
  `__eq__` and `__repr__` for all 20 files that already import it, which
  `AGENTS.md`'s *Declaration form is part of the contract* rule forbids doing
  incidentally. Deriving changes nothing for existing users.
- **Migrates 11 of the 17 remaining files** onto the shared module — the 8
  ORDERED and 3 of the 4 ORDINAL — removing **1,197 lines across 160
  declarations**, and leaving each file's own query helpers, which are not
  duplicated anywhere.

Those eleven files declare **97 module-level helpers whose bare name matches one
in `tests/support/html.py`**, and deciding each one is the substance of the
change. Three instruments were run over all 97 and **no two agree**: an AST
comparison over-reports difference, the leaf-equivalence proof over-reports
sameness, and reading adjudicates between them. `design.md` Decision 2 states
the composite rule — each instrument vetoes in one direction only. The result is
**87 migrate, 10 keep**, and three of the ten keeps had zero or coincidental
execution evidence, which is why the rule cannot rest on the proof alone.

The sharpest instance: `_texts` in `test_playbook_admin_presentation_vocabulary`
refuses to descend into a named control. Instrumented, it runs **163 calls, 4 of
them over a subtree that does contain a control, and 0 disagreements** — the
divergent branch executes and still does not reach the result, because those
controls held no text. Only reading the source separates it from the shared
function.

| group | files | needs `document_order` |
|---|---|---|
| ORDERED, reads `.order` | 5 | yes — 4 × `node.order < title.order`, 1 × a sort key |
| ORDERED, never reads it | 3 | no |
| ORDINAL, never reads `.ordinal` | 3 | no |

**Six of the eleven migrate with no new API at all.** They are STANDARD files
wearing a divergent data model, and the only thing standing between them and the
shared module was a dead field.

**Expected migrated: 11 of 11**, stated per phase so a shortfall has something
to report against — 6 in the dead-field phase, 5 in the derived-order phase. A
phase whose population total is also its target cannot report a shortfall, which
is the reason the last slice recorded for stating these separately.

### What stays local, and why

- **`test_playbook_admin_fault_attribution.py`** keeps its ORDINAL parser. Its
  `ordinal` is not a document position: `_attributed_fragments` synthesises
  `_Text` fragments out of *attribute values* and numbers them **negatively**
  (`ordinal = -1`, decrementing), so a fragment's ordinal is an identity for
  text that has no position in the document at all. Nothing derivable from tree
  position can produce it. This is a stronger reason than the one on record, and
  it is recorded at the declaration.
- **The five STANDARD stragglers** stay, on the reason task 3.1 gave, which this
  change re-measured rather than inherited. Three of them
  (`test_launch_admin_start_marks`, `test_launch_detail_finding_members`,
  `test_launch_detail_finding_rendering`) build `Text(data)` **raw** where the
  shared parser builds `Text(flat(data))`, and their `_all_text` does not
  lowercase where the shared one does; migrating them would change what their
  assertions see, and *a migration that changes an assertion is not a
  migration*. The other two
  (`test_playbook_admin_dependency_option_filtering`,
  `test_playbook_admin_multi_value_controls`) carry `_flat` with a different
  signature entirely — `_flat(node: Node) -> str`, not `_flat(text: str) -> str`.

**One thing this change found that task 3.1 did not record**, and which is
reported here rather than fixed here, because it belongs to two files this
change does not touch: those same two files also declare `_carries`,
`_attribute_text` and `_ancestors` with **behaviour different from the shared
functions of the same names** — `_carries` matches an `id` and any `data-*`
value as well as a class; `_attribute_text` joins one node's own attribute values
rather than walking descendants and filtering by key; `_ancestors` walks past
`#document` rather than stopping below it. Elsewhere those spellings are
aliases for the shared functions: **12 files alias at least one, `ancestors` in
12, `attribute_text` in 4, `carries` in 3**. Task 3.1 caught this collision for `_flat` and `_tree` and named it as a
hazard; it did not catch these three. It is a naming hazard, not a defect — every
assertion is correct as written — so it goes to `docs/deferred-work.md` as a
cleanup rather than being folded in here, per *Incremental development and scope
control*.

**No production code changes.** Nothing under `src/` is read, written or
imported differently.

## Capabilities

### New Capabilities

None. This change adds no behaviour to the system under test.

### Modified Capabilities

None. `.openspec.yaml` sets `skip_specs: true`, as `share-the-unit-test-harness`,
`share-the-value-doubles`, `share-the-stateful-fakes`,
`share-the-playbook-builders` and `share-the-aggregate-fakes` all did: this
change moves duplicated test arrangement into an existing shared module and
changes no specified behaviour. Per `AGENTS.md` — *Test design before
implementation* — a change declaring no specification deltas owes no new tests
derived from deltas; **what it owes is that the existing suite stays green and
its collected count outside `tests/unit/support/` does not move.**

Baselines re-taken on this tree at `9c15833`, not inherited:

```
tests/unit + tests/agents      2,569 passed          (tests/unit/support 87 of these)
tests/integration                159 passed, 0 skipped
assertion identity     6,612 / 238 / 759 / 172   over 2,192 functions in 332 files
```

The integration tier was run here against a configured `.env.test` and a
`commerce-ops-postgres-1` container that is up — 159 passed, zero skipped — so
the green is evidence that it ran, not the fail-open green `AGENTS.md` warns
about. The assertion-identity figure was taken with
`~/share-the-playbook-builders/assert_identity.py`'s own `collect()`, per the
recorded instruction not to re-implement that detector. Only
`tests/unit/support` may move.

## Impact

- **`tests/support/html.py`** — one new function, `document_order`. No change to
  `Node`, `Text`, `TreeParser` or any existing query. The module docstring's
  three-model census is updated to say which files still hold each model and why.
- **`tests/unit/support/`** — a contract test for `document_order`, added to its
  87. This is the only collected count allowed to move.
- **11 test files** under `tests/unit`, losing 1,197 lines across 160
  declarations and gaining aliased imports. **No line inside a `def test_` is
  touched.** The five `.order` read sites become `document_order(...)` calls in
  the same expressions, two `_texts` consumers unbox inside helpers — those two
  lines are the change's only call-site edits — and each of the ten kept helpers
  gains a `**Kept local**` docstring. **No identifier is renamed**, and nothing
  is retyped: `Node`, `Text` and `TreeParser` are aliased under the files'
  existing `_`-prefixed spellings, so all 150 `_Node`/`_Text` references across
  the eleven files, five of them `isinstance` checks, stand unchanged.

  An earlier draft renamed the ten keeps off their shared spellings instead.
  Measured, that reaches **92 sites, 56 of them inside test bodies**, and
  `_carries` is a proper substring of `_page_carries` and of three test function
  names; `design.md` Decision 5 rejects it, because a recorded note is what
  `AGENTS.md` asks for and what the preceding slices did.
- **Six further test files**, receiving a recorded-keep note and nothing else —
  `test_playbook_admin_fault_attribution` and the five STANDARD stragglers
  (tasks 4.2 and 4.3). No code in them changes, so the diff touches 17 test
  files while 11 are migrated.
- **`AGENTS.md`** — *The shared harness* section, recording what this slice took,
  what it left, and the rule it establishes: that a population classified by the
  shape of its data model must be re-classified by what the tests actually read
  before any of it is called a keep.
- **`docs/deferred-work.md`** — one new entry for the three-name collision in the
  two files this change does not touch.
- **`docs/proposed-change-order.md`** — its "**The harness thread is finished**"
  sentence is what this change falsifies, and it is amended rather than deleted
  so the record shows what was believed and what measurement changed.
- **Conflict-prone in `tests/unit/launch/infrastructure/driving/`**, where **10
  of the 11** files live — only `test_members_admin_presentation_vocabulary` is
  elsewhere, under `tests/unit/access/infrastructure/driving/`. It does not run
  concurrently with anything else editing the admin-surface tests.
