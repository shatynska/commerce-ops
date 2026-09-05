# Tasks

Every figure below is re-taken on the branch, never inherited. Where a task
states an expected count, the result records **actual against expected**, so a
phase whose population total is also its target can still report a shortfall.

**The core** a file migrates is not a fixed list of names. It is *every
module-level helper in that file whose bare name matches one in
`tests/support/html.py` and which §1's instruments disposition `migrate`* —
plus the `_Text`, `_Node` and `_TreeParser` those helpers rest on, **plus the
module-level constants `_VOID_TAGS`, `_HIDDEN_CLASSES` and `_HX_VERBS`, which
are aliased rather than deleted** (`design.md` Decision 6). Each file's helper
set is named at its own task, because the eleven differ: they declare between 4
and 13 migrating helpers each, 97 shared-name helpers and 30 constants in total.

**No line inside a `def test_` is touched by any task below.** If a task appears
to require one, it is wrong and stops the phase.

## 1. Baselines and the instruments

- [x] 1.1 Re-take the four baselines at the branch point and record them here:
      `tests/unit` + `tests/agents` collected, `tests/unit/support` collected,
      `tests/integration` collected and skipped, and the assertion-identity
      multiset via `~/share-the-playbook-builders/assert_identity.py`'s own
      `collect()`. **Do not re-implement that detector** — one omitting
      `_assert`-prefixed helper calls reports 648 rather than 759.

      Expected, from `proposal.md`: 2,569 / 87 / 159 with 0 skips /
      6,612 · 238 · 759 · 172 over 2,192 functions in 332 files.

- [x] 1.2 Confirm the integration tier actually runs in this worktree before
      trusting its green: `docker ps` shows `commerce-ops-postgres-1`, and
      `.env.test` names a database whose name ends in `_test`. A skipped tier
      reports `Passed` and is not evidence.

- [x] 1.3 Re-run the instruments of `design.md` Decision 2 over the 97 helpers
      and record the table: the AST comparison (normalised for the helper's own
      name, its parameters, its docstring and the `_` prefix), the
      leaf-equivalence proof's per-helper call and disagreement counts, the
      reading that adjudicates whatever the AST comparison separated, and **the
      callee check in both directions** — whether a migrating helper's body
      calls a keep, and whether a keep's body calls a migrating helper.

      Put any pytest plugin in a directory containing **nothing else**. A stray
      module there shadows a stdlib import through `PYTHONPATH` — a leftover
      `queue.py` did exactly this and surfaced as an unrelated `ValueError`
      inside `concurrent.futures`.

      **Expected: 87 migrate, 10 keep, 0 migrating helpers calling a keep, and
      4 keeps calling a migrating helper** — `_attribute_text` in
      `test_members_admin_presentation_vocabulary` (calls `_all_text`,
      `_elements`) and the three kept `_carries` (each calls `_classes`,
      `_elements`). All six distinct callees must be AST-identical to their
      shared counterparts; report it if any is not. Report actual against every
      one of those figures.

      The AST comparison must be normalised for the helper's *own name* as well
      as its parameters; without that it reports all 97 as differing, which is a
      result that looks like a finding.

- [x] 1.4 Re-confirm the whole-tree proof on this branch, over **all eleven**
      files rather than the eight that carry `order`: **138 parses, 19,056
      nodes, zero order, shape and text mismatches**, with the order comparison
      applying to the eight ORDERED files and the tree comparison to all eleven.
      This is the named instrument for the three ORDINAL parsers, which would
      otherwise migrate on the `_tree` row of the leaf proof alone.

- [x] 1.5 Re-confirm the `_texts` control probe on
      `test_playbook_admin_presentation_vocabulary`: 163 calls, **4 of which
      pass a subtree containing a control**, 0 disagreements. This is the
      measurement `design.md` Decision 2 rests on — the divergent branch
      executes and still does not reach the result.

- [x] 1.6 Confirm by AST comparison that all 30 constant declarations across
      the eleven files are **equal in value** to their shared counterparts, so
      aliasing them changes nothing. Several differ in line formatting, so the
      claim is value equality and not byte equality. **Expected: 30 equal, 0
      differing.**

## 2. Phase A — the six files carrying a field they never read

No addition to `tests/support/html.py` is required by this phase. If it is
green, the core migration is proved independently of `document_order`.

Every file in this phase: delete the local `_Text`/`_Node`/`_TreeParser`
declarations and the migrating helpers' bodies; **alias from
`tests/support/html.py`, under the file's existing `_`-prefixed spellings, every
name that something still reads afterwards**; and give each kept helper a
`**Kept local**` docstring per 4.1.

**Alias what remains referenced, not everything that migrated** (`design.md`
Decision 6). An alias nothing reads is a `ruff` F401 error and fails 2.9. The
measured exceptions, to be re-confirmed rather than trusted:

- `_TreeParser` is read by nothing in **any** of the eleven once `_tree` is an
  alias. It is never aliased.
- `_Text` is unread in **three** — `test_product_surfaces_header_and_presentation`,
  `test_members_admin_presentation_vocabulary`,
  `test_admin_surface_navigation_and_assets`. `_Node` is read in all eleven.
- **Seven migrating helpers have no surviving reader** and are deleted rather
  than aliased: `_flat` in `test_launch_detail_breadcrumb`,
  `test_launch_journal_page`, `test_playbook_admin_edit_create_breadcrumb` and
  `test_product_dossier_breadcrumb`; `_all_text` in
  `test_playbook_admin_edit_create_breadcrumb`; `_carries` in
  `test_members_admin_presentation_vocabulary`; and `_ancestors` in
  `test_playbook_admin_presentation_vocabulary`.

These seven are not the *removing dead test helpers* non-goal, which is about a
helper whose deletion would require deleting its callers. These have no callers
once the migration lands.

**Nothing is retyped.** Because `Node` and `Text` arrive as `_Node` and `_Text`
wherever they are still read, the **150** references to them outside the harness
helpers — every file-specific helper's annotation, and **five `isinstance`
checks** — stand exactly as written. This is what the predecessor did
(`test_members_header_names_every_surface.py:92`). A task that asks for
`-> _Node` to become `-> Node` is asking for 150 edits to reach the same objects;
confirm from the diff that no annotation moved.

- [x] 2.1 Before migrating each file, confirm by search across all three tiers
      that it reads neither `.order` nor `.ordinal`, and that nothing reaches
      either field by another spelling.

- [x] 2.2 `test_product_dossier_page` — **4 migrate**: `_ancestors`, `_classes`,
      `_elements`, `_tree`. **2 keep**: `_all_text` (17,609 calls, 14,349
      disagree — does not lowercase); `_carries` (30 / 4 — widens to
      descendants). Drop `order` from `_Node`.

- [x] 2.3 `test_product_dossier_established_by_automation` — **4 migrate**:
      `_ancestors`, `_classes`, `_elements`, `_tree`. **2 keep**: `_all_text`
      (127 / 127); `_carries` (7 calls, **0 disagreements**, body widened).
      Drop `order`.

- [x] 2.4 `test_product_surfaces_header_and_presentation` — **5 migrate**:
      `_ancestors`, `_element_disabled`, `_element_hidden`, `_elements`,
      `_tree`. **No keeps**: this file declares neither `_all_text` nor
      `_carries`. Drop `order`.

- [x] 2.5 `test_members_admin_presentation_vocabulary` — **13 migrate**:
      `_all_text`, `_ancestors`, `_carries`, `_classes`, `_element_disabled`,
      `_element_hidden`, `_elements`, `_flat`, `_inherited`, `_nearest`,
      `_size`, `_texts`, `_tree`. Its `_all_text` is
      `" ".join(t.text for t in _texts(node)).lower()` — a respelling of the
      shared function, not a divergence, so it migrates and its body
      disappears. **1 keep**: `_attribute_text` (**0 calls** — its two call
      sites are inside `_member_row:510`, which has no callers of its own).
      Drop `ordinal` from `_Text`.

      **This file carries the sharpest of the four callee interactions**
      (`design.md` Decision 2): the kept `_attribute_text` calls `_all_text`,
      which migrates here, and has **zero calls** — so no instrument would
      report a divergence had the shared `all_text` differed from the local one
      it replaces. Record at the keep that the two were compared and answer the
      same.

- [x] 2.6 `test_admin_surface_navigation_and_assets` — **11 migrate**:
      `_all_text`, `_ancestors`, `_classes`, `_element_disabled`,
      `_element_hidden`, `_elements`, `_flat`, `_inherited`, `_size`, `_texts`,
      `_tree`. **No keeps.** Drop `ordinal`.

- [x] 2.7 `test_playbook_admin_presentation_vocabulary` — **9 migrate**:
      `_ancestors`, `_carries`, `_classes`, `_element_disabled`, `_elements`,
      `_flat`, `_inherited`, `_nearest`, `_tree`. **3 keeps**: `_texts` (163
      calls, 0 disagreements, skips named controls); `_element_hidden`
      (1,475 / 12, also treats `<input type="hidden">` as hidden); `_all_text`
      (**0 calls**, does not lowercase). Drop `ordinal`.

      Note that this file's `_carries` **migrates** — unlike the three
      `_carries` at 2.2, 2.3 and 3.7, it is the shared reading. And its kept
      `_element_hidden` reads `_HIDDEN_CLASSES`, so that constant is aliased
      here rather than dropped.

- [x] 2.8 Unbox the two `_texts` consumers whose local function migrated, named
      individually: `test_members_admin_presentation_vocabulary.py:476` and
      `test_admin_surface_navigation_and_assets.py:578`, each
      `" ".join(t.text for t in _texts(x))` → `" ".join(_texts(x))`. Both are
      inside helpers. The third consumer,
      `test_members_admin_presentation_vocabulary.py:376`, is inside
      `_all_text`, which 2.5 deletes. **These two lines are the only call-site
      edits in the whole change**; every other migrated helper keeps its
      signature.

- [x] 2.9 After each file: `uv run pytest tests/unit tests/agents`,
      `uv run mypy .` and `uv run ruff check` — the last is what catches an
      alias nothing reads. `mypy` is the seam that catches a half-migrated file
      (`design.md` Decision 8); a green suite alone does not establish one, and
      it is also what turns a missed `.order` or `.ordinal` read into an error
      rather than a silent pass.

- [x] 2.10 Confirm from `git diff` that no line inside a `def test_` changed in
      any of the six files. This is the non-goal's own check and it is
      mechanical: the diff's changed line numbers must fall outside every
      `test_`-prefixed function's span.

      **Expected migrated in Phase A: 6 of 6 files, 46 of the 97 helpers.**

## 3. Phase B — `document_order` and the five files that read `.order`

- [x] 3.1 Add `document_order(node: Node) -> int` to `tests/support/html.py`.
      Pre-order index within the document reached by climbing `parent`; the
      root answers `0` and the first element `1`; the target is located **by
      identity, never by `==`** (`design.md` constraint 2). It takes `Node`,
      never `Text`.

      Constraint 2 is stronger than "silently wrong", measured while the
      contract test was written: two structurally similar cells under different
      parents raise `RecursionError` under `==`, so an equality-based
      implementation crashes on an ordinary table page rather than answering
      wrongly. Neither failure is acceptable; the point is that `is` is not a
      refinement here, it is the only thing that works.

- [x] 3.2 Write `tests/unit/support/test_html_document_order.py`, pinning:
      the root is `0` and the first element `1`; siblings ascend; a descendant
      follows its ancestor; **two equal sibling nodes get distinct answers**
      (the `==`-vs-`is` trap, which is the one a plausible integer would hide);
      a self-closing and a void element each take a position; a detached node
      answers `0` **and its child answers `1`**, so the rule cannot be read as
      "a detached subtree answers 0 throughout". This is the only collected
      count allowed to move.

- [x] 3.3 `test_launch_detail_breadcrumb` — **9 migrate**: `_all_text`,
      `_ancestors`, `_classes`, `_element_disabled`, `_element_hidden`,
      `_elements`, `_flat`, `_inherited`, `_tree`. **No keeps.** Drop `order`;
      rewrite `_before_title:630` as
      `_document_order(node) < _document_order(title)`.

- [x] 3.4 `test_launch_journal_page` — same 9 migrate, no keeps; read site
      at `:718`.

- [x] 3.5 `test_playbook_admin_edit_create_breadcrumb` — same 9 migrate, no
      keeps; read site at `:529`. Its `_all_text` has **0 calls** and only its
      own recursion; the AST comparison calls it identical to the shared one, so
      it is not a keep — but nothing reads it after migration either, so it is
      **deleted rather than aliased**, per the §2 preamble. Same for its
      `_flat`.

- [x] 3.6 `test_product_dossier_breadcrumb` — **8 migrate**: `_ancestors`,
      `_classes`, `_element_disabled`, `_element_hidden`, `_elements`, `_flat`,
      `_inherited`, `_tree`. **No keeps.** Read site at `:439`. Its proof is
      thin (1 parse, 51 nodes); record that rather than rounding it up.

- [x] 3.7 `test_product_index_page` — **6 migrate**: `_ancestors`, `_classes`,
      `_element_disabled`, `_element_hidden`, `_elements`, `_tree`. **2 keep**:
      `_all_text` (6,134 / 5,861); `_carries` (**4 calls, 0 disagreements** —
      the proof agreed by sample, the body widens to descendants). Rewrite
      `_rows_in_order:306`'s sort key as
      `key=lambda pair: _document_order(pair[1])`.

- [x] 3.8 After each file: `uv run pytest tests/unit tests/agents` and
      `uv run mypy .`; and 2.10's mechanical check that no `def test_` line
      moved.

      **Expected migrated in Phase B: 5 of 5 files, 41 of the 97 helpers.**

## 4. The keeps, each recorded at its declaration

- [x] 4.1 Give each of the ten keeps a `**Kept local**` docstring — the
      convention the four preceding slices set, and what `AGENTS.md` means by
      *"the file keeps its own declaration and the reason is recorded"*. Each
      names the shared function it is not, the input that distinguishes them,
      and its measured call and disagreement counts.

      **Three of the ten had zero or coincidental execution evidence** —
      `_attribute_text` (0 calls), `_all_text` in
      `test_playbook_admin_presentation_vocabulary` (0 calls), and `_carries`
      in `test_product_index_page` (4 calls, 0 disagreements) — and each says
      so, because a declaration nothing executes reports zero, never pass.

      **Four of the ten call a helper that migrates out from under them** —
      `_attribute_text` and the three kept `_carries`. Each of those four notes
      records that its callees were compared against their shared counterparts
      and answer the same, so the keep's meaning did not move with them.

- [x] 4.2 Record at `test_playbook_admin_fault_attribution`'s `_Text` why the
      ORDINAL model stays there: `_attributed_fragments:436-445` synthesises
      fragments out of attribute values and numbers them **negatively**, so
      `ordinal` is an identity for text with no document position, which
      nothing derived from tree position can produce.

- [x] 4.3 Record at each of the five STANDARD stragglers why it stays — raw
      `Text(data)` and an uncased `_all_text` in three, a `_flat` of a
      different signature in two — citing this change's measurement rather than
      the predecessor's wording.

- [x] 4.4 Add one `docs/deferred-work.md` entry for the divergent spellings in
      `test_playbook_admin_dependency_option_filtering` and
      `test_playbook_admin_multi_value_controls`. State the population by name
      and the command that produced it: **12 files alias at least one of the
      three; `ancestors as _ancestors` in 12, `attribute_text as
      _attribute_text` in 4, `carries as _carries` in 3** — while those two
      files declare all three locally with different behaviour and no recorded
      note. The remedy there is 4.1's note, not a rename, for the reasons
      `design.md` Decision 5 measured.

## 5. Verification and the record

- [x] 5.1 Re-take all four baselines. `tests/unit` outside support,
      `tests/agents` and `tests/integration` unchanged; `tests/unit/support`
      up by 3.2's count; the assertion-identity multiset **must not move**.
      Report actual against expected.

- [x] 5.2 Run the integration tier and confirm 159 passed, zero skipped.

- [x] 5.3 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy .`.

- [x] 5.4 Confirm mechanically that nothing under `src/` changed:
      `git diff --stat origin/main -- src/` is empty.

- [x] 5.5 Re-measure the lines removed and report actual against the **1,197
      lines across 160 declarations** `proposal.md` claims, so that figure is
      verified rather than asserted.

      **Actual: 1,408 lines deleted and 226 inserted across the eleven files,
      net −1,182.** The 1,197 was the sum of the declarations' own spans; the
      1,408 is those spans plus the comment banners and blank lines they sat
      in, which go with them. The insertions are the aliased imports and the
      ten `**Kept local**` notes. Both figures are right about different
      things, and the proposal's is the narrower one.

- [x] 5.6 Update `tests/support/html.py`'s docstring: the three-model census now
      records that the ORDERED model is gone from the suite, that three of the
      four ORDINAL files have migrated, and that the one remaining ORDINAL file
      and the five STANDARD stragglers are keeps with their reasons.

- [x] 5.6a Preserve the invented-reading record that migration would otherwise
      delete. Two migrating `_carries` record their class-token reading as an
      interpretation and themselves as the correction point — one marked
      INVENTED (`test_playbook_admin_presentation_vocabulary:400`), one naming
      the reading as `design.md`'s without that marker
      (`test_members_admin_presentation_vocabulary:393`); the shared
      `carries` docstring (`tests/support/html.py:174`) states the reading but
      not that it is an interpretation. Add that to the shared docstring, so the
      record survives for all its users rather than being lost with two of them.
      Check first whether the predecessor already settled this for the 20 files
      it migrated; if it did, say so instead of restating it.

- [x] 5.7 Update `AGENTS.md`'s *The shared harness* section with what this slice
      took and what it left, and the two rules it establishes: **a population
      classified by the shape of its data model must be re-classified by what
      the tests actually read before any of it is called a keep** — six of
      twelve files here were held back for a field none of them read — and
      **each disposition instrument is a veto in one direction only**: a source
      comparison over-reports difference and can only veto a *migrate*;
      execution over-reports sameness and can only veto a *keep*; and a migrate
      requires its callees to migrate.

- [x] 5.8 Correct `docs/proposed-change-order.md` in **both** places it makes
      the claim: "**The harness thread is finished**" at line 11, and "**The
      fakes thread is closed** … every recurring double in the suite is now
      shared or is a recorded keep" at lines 80-82. Six of those keeps were
      reasoned from a field none of them reads. Amend rather than delete, so
      the record shows what was believed and what measurement changed.

- [x] 5.9 `/code-review` over the full diff. `AGENTS.md` requires it and the
      predecessor recorded that it found six defects two passing proofs and a
      green suite could not.

- [x] 5.10 Open the pull request. Archive only after it merges, on its own
      branch in its own PR, per *Deployment and configuration*.
