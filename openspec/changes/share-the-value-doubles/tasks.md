# Tasks

Per-name expectations below are set from the measured variant structure, not
from ambition. A name landing under its expectation is a finding to record in
task 10.3, never a target to force. `design.md` Decision 3 is the boundary; no
task relaxes it.

Every task's verification is the commit tier — `uv run pytest tests/unit
tests/agents` — plus `ruff check .`, `ruff format --check .`, `uv run mypy .`
and `lint-imports`. Per-tier, never bare `uv run pytest`, which fails at
collection on `main` because two basenames repeat across tiers
(`docs/deferred-work.md`).

**Four names additionally run the integration tier at their instrument commit**
— `Member`, `CatalogProduct`, `FakeTask`, `CreatedTask` — because five of the
186 declarations live in `tests/integration/` and Decision 2's proof runs inside
the instrumented constructor, so a tier that never imports the module never runs
the check (`design.md` Decision 10). Run it with
`COMMERCE_OPS_REQUIRE_DATABASE=1`, so a skipping tier fails instead of
reporting green.

**"Instrument, verify, settle, verify"** is the procedure of tasks 3.5, 3.7 and
3.8, and it means all three every time it appears: instrument, run the
verification above, settle, run it again — **including `assert_identity.py`
between the commit before the instrument commit and the commit after the settle
commit**, never against the instrument commit itself, which adds an assertion by
construction (`design.md` Decision 8).

Counts here are AST counts. Do not re-derive one by grep: `^class _Record:`
matches 31 files against 30 declarations, the 31st being source text inside a
subprocess driver script (`design.md` — Context).

## 1. Baseline and instruments

- [x] 1.1 Record the baseline before anything is edited: collected counts for
      `tests/unit`, `tests/agents` and `tests/integration` separately, and
      pass counts and wall time for the commit tier and the integration tier.
      Expected `2,246 / 236 / 159`; commit tier `2,482 passed`. **Record what is
      measured, not what is expected** — if the tree disagrees with the parent
      change's numbers, the tree is right and the disagreement is a finding.
- [x] 1.2 Configure this worktree's `.env.test`. A worktree does not inherit it
      (`.env.*` is gitignored and `git worktree add` carries none), and until it
      is configured the integration tier skips in its entirety while `pre-push`
      reports `Passed` — a merged pull request has already claimed a tier that
      had skipped. Copy the password from the main checkout, give this worktree
      its **own** database with `_test` last in the name (the check is a suffix
      check), then `alembic upgrade head` **and**
      `uv run python -m commerce_ops.seed_playbook`. Migrated is not seeded: a
      schema-only database fails four tests, and each says so in its own
      assertion message.
- [x] 1.3 Run the integration tier once, with `COMMERCE_OPS_REQUIRE_DATABASE=1`
      so a skipping tier fails rather than reporting green. Expected
      `159 passed`.
- [x] 1.4 Copy `~/share-the-test-doubles/assert_identity.py` into the change's
      scratchpad. Its path constant is **`REPO`** (line 30), not `ROOT`, and it
      already points at this worktree — repoint it only if implementation moves
      elsewhere. Its CLI takes `<before-rev> <after-rev> [path ...]` and prints
      per-file comparisons; it has **no whole-tree counting mode**, so take the
      baseline by calling its `collect()` over `tests/**/*.py` at `main` and
      summing by key prefix (`assert::`, `raises::`, `helper::`, `param::`).
      Expect 6,623 `ast.Assert`, 238 `pytest.raises`, 757 helper-style
      `Expr(Call)`, 172 `@parametrize`. A count that disagrees means the tree
      moved; record the new one and use it.

      **Measured 2026-09-04 over 340 files: 6,623 / 238 / 759 / 172.** The
      helper-style count is 759, not 757; the other three match. 759 is the
      baseline in force.
- [x] 1.5 **Record the queue ordering before any migration begins**, not at the
      end. `docs/proposed-change-order.md` lists
      `unify-launch-adapter-dependencies` at §2, ahead of the doubles at §4,
      with a recorded dependency only on `defer-eager-clickup-convergence` — and
      that file states its numbering *is* the working order and that the
      ordering "lives nowhere else". So the constraint `proposal.md` asserts
      exists nowhere until it is written there, and the window in which this
      change is in flight is exactly the window in which someone could pick up
      §2 and delete the probe branches that 52 member doubles still depend on.
      Record in that entry that it must follow `share-the-value-doubles`, and
      place the entries accordingly. (The §4 split is a completion record and
      stays at 10.2.)
- [x] 1.6 Write the comparison helper `design.md` Decision 2 specifies
      (`_fields`: dataclass fields shallow, else `vars`). **The instrument commit
      adds it to the tree and the settle commit removes it**, because the
      instrumented classes live in ~150 tree files and cannot import a
      scratchpad module. Neither `main` nor the shipped state ever carries it,
      which is what Decision 2 means by "neither ships a checker" — four lines,
      added and removed with the instrumentation they serve.

## 2. `tests/support/values.py` and its protocols

- [x] 2.1 Create `tests/support/values.py` with a module docstring stating what
      the module is for and, explicitly, that a type here is a **double** and
      never sources a value from production — `AGENTS.md`'s rule, and the reason
      `Member` below is not `access.domain.members.Member`.
- [x] 2.2 Name the types **publicly** in `values.py` — `Member`, not `_Member` —
      and alias them at the call site. A module-private name imported across
      modules is a contradiction. **`tests/support/__init__.py` stays empty**:
      its shipped docstring records that modules here are imported by path and
      "never re-exported from this file, so the package cannot become one
      namespace everything pulls from". That is the parent change's decision and
      this change extends it rather than reversing it.
- [x] 2.3 Run one AST measurement pass over `tests/` before any type is written,
      recording per declaration: field set, each field's default, declaration
      form (plain / `@dataclass` / `frozen`), **every call site's argument shape
      — name, position and optionality — against the local's `__init__`
      signature**, and whether the file relies on `__eq__`, `__hash__` or
      `__repr__` of the local. All three clauses of `design.md` Decision 3 read
      from this one pass; measuring them separately is how they get out of step.
      The constructor measure is clause (c) and it is not optional:
      `test_product_dossier_page.py:721` passes clauses (a) and (b) and would
      `TypeError` at collection.
- [x] 2.4 Add each protocol to `tests/support/protocols.py` **in the task that
      adds its type**, never ahead of it, and add the `_conforms` assignment
      beside the type. Do not edit the module docstring's statement that these
      protocols are temporary and that `unify-launch-adapter-dependencies`
      replaces them.

## 3. `Member` and `MemberValue` — 52 declarations, expectation 52 (51 + 1 adapter)

Taken first: largest, and it carries `design.md` Decision 5. If the `id`/
`identifier` decision is wrong, learning it here is cheaper than learning it
last.

**Scoped by shape, not by name.** `_FakeMember` is five declarations, one body,
byte-identical to the dominant `_Member` and spelling the field `id` exactly as
it does:

| file | line |
|---|---|
| `test_playbook_admin_page.py` | 372 |
| `test_playbook_admin_edit_create_breadcrumb.py` | 222 |
| `test_playbook_admin_filtered_moves.py` | 639 |
| `test_playbook_step_name_link.py` | 141 |
| `test_launch_journal_page.py` | 354 |

Any frequency threshold excludes it; Goal 3 requires it, because three of the
five sit directly opposite `playbook_admin.py:321`.

- [x] 3.1 From the 2.3 pass, tabulate the 52 declarations: 37 plain `_Member`,
      10 `@dataclass` `_Member`, 5 plain `_FakeMember`. Confirm the two sets
      measured in `design.md` Decision 1 — the ten declaring `@dataclass` and
      the ten constructing with `id=` — are still identical. **If they have
      diverged, stop and re-derive Decision 5 before writing anything**; the
      two-type split rests on that identity.
- [x] 3.2 Record, for the 37 plain declarations, whether any test relies on
      identity inequality — two distinct instances carrying equal field values
      and asserted unequal — or uses a member as a set element or dict key. The
      migration does not depend on the answer (the shared `Member` is a plain
      class, so nothing changes for them), but it is `design.md` Open Question 2
      and it is cheap to answer while the corpus is open. Record it for
      `unify-launch-adapter-dependencies`.
- [x] 3.3 Add **`Member`** to `values.py`: plain class, field `id`, read-only
      `identifier` property returning `self.id`, `clickup_user_id` defaulting to
      `'clickup-1'`, **`slack_identity` typed `str | None` and defaulting to
      `None`**, `admin=False`, `active=True`. State the declaration form in a
      comment — it is part of the contract, per Decision 3 clause (b), not an
      implementation detail.

      `None` is not a stylistic choice. 42 of the 52 locals declare no
      `slack_identity` at all, and three production sites read it by shape —
      `gate_decisions.py:94` and `automated_decisions.py:125`, both
      `if getattr(member, "slack_identity", None) == slack_identity:`, and
      `thread_establishment.py:224`. A literal default would give all 42 a
      truthy identity they never had and start matching those two comparisons
      where they used to fall through. This is a displacement under the
      same-value invariant, not a superset.
- [x] 3.4 Add **`MemberValue`**: `@dataclass`, field `id`, the same `identifier`
      property, `clickup_user_id` defaulting to `None`, `slack_identity` typed
      `str | None` — all ten of its files declare it, and
      `test_mention_resolution_namespace.py:233` passes `None` deliberately.

      Add `MemberShape`, declaring `identifier` as a **read-only property** —
      `@property def identifier(self) -> str: ...` — and never as the variable
      `identifier: str`: `mypy` treats a protocol variable as settable, so the
      variable form makes the `_conforms` assignment a type error on the one
      line it exists to justify (`design.md` Decision 7). One `_conforms`
      assignment per type, both against `MemberShape`.
- [x] 3.4a Handle the one clause-(c) failure. `test_product_dossier_page.py:721`
      declares `__init__(self, display_name, *, active=True)` with `id` pinned,
      and constructs `_Member(ALICE_RENAMED)` at 1350 and
      `_Member(ALICE, active=False)` at 1378 — the display name in the position
      the shared type reads as the identifier. It keeps a **three-line adapter
      subclass** over `Member`, not its own declaration: excluding it would
      leave a member double spelling only `id`, and Goal 3 needs all 52. Count
      it as an adapter in the record, not as a clean migration.
- [x] 3.5 **Instrument.** Keep every local; add the shared import and the
      field-equality assertion over the intersection, failing with both mappings
      named. Run the commit tier **and the integration tier** — the latter so
      that `tests/integration/launch/test_seeded_step_fields.py:578` has its
      collection exercised at all — its aliased import arrives at 3.7, so 3.8
      runs the integration tier again and that is where the import is checked.
      Its proof is inapplicable rather than merely unrun, per 3.5a; the other
      four integration declarations, under three other names, *are* constructed,
      and for those the instrument-time tier is what makes the proof run. Every failure is a real difference; fix the
      shared default or exclude the file, never weaken the assertion.
- [x] 3.5a Record that `test_seeded_step_fields.py`'s `_Member` is **never
      constructed** — that file's `_FakeMembers.list_members` returns `()` and
      the class appears only in annotations — so Decision 2's proof is not
      skipped for it but inapplicable. It migrates on clauses (a)–(c) and
      `mypy` alone. Say so; an inapplicable proof recorded as a passing one is
      the silence this task list exists to prevent.
- [x] 3.6 Record the same-value checks **once each, not per file**. Two
      displacements, not one.

      **`identifier` over `id`**, at six probe sites — `clickup_sync.py:140`,
      `playbook_authoring.py:272`, `playbook_admin.py:321`,
      `activation_readiness.py:204`, `roles.py:729`, `gate_decisions.py:105` —
      and carries the same string by construction, because the property returns
      the field. All six read `identifier` first, so the two differing tails
      (`roles.py`'s `member_id`-before-`id`, `gate_decisions.py`'s `name`) do
      not change the conclusion; record that they were checked rather than
      assumed.

      **`slack_identity` over its own absence**, at the three sites in 3.3,
      resolved by defaulting to `None` — the fall-through value.

      Then run the search across `tests/` **and** `src/` for `admin`, and
      **record its result** rather than its expected result. If it is read
      anywhere by shape, it is a third displacement and the default follows the
      invariant, not convenience.
- [x] 3.7 **Settle.** Delete each local class and add
      `from tests.support.values import Member as _Member` — or `MemberValue as
      _Member`, or `Member as _FakeMember` — on its own `from` line. `I001` is
      enforced and `combine_as_imports = false`, so a merged import is split
      straight back. Anchor the class removal on `decorator_list[0]` where the
      class is decorated, or the `@dataclass` is orphaned onto the next
      declaration.
- [x] 3.8 Run `assert_identity.py` across the commit pair — the commit before
      3.5 against the commit after 3.7, never against the instrument commit
      itself, which adds an assertion by construction (`design.md` Decision 8).
      Four multisets identical, `def test_` count unchanged. Run the commit tier
      and `mypy`.
- [x] 3.9 Record any file not migrated and why, and record the adapter from 3.4a
      separately from the clean migrations. The expectation is **52 of 52 — 51
      clean and 1 adapter**. A shortfall is a finding to record, and, since Goal
      3 requires all 52 to expose `identifier`, a shortfall must also record
      which probe sites it leaves live.

      **The record: 52 of 52 — 49 clean and 3 adapters.** 39 alias `Member`
      (34 `_Member`, 5 `_FakeMember`), 10 alias `MemberValue`, 3 adapt.

      The extra two adapters are a finding, and they are one `design.md` said
      could not happen. Decision 5 states that "the plain locals hard-code
      `'clickup-1'`"; two of the 42 hard-code `"clickup-alice"` —
      `test_clickup_automated_steps_leave_loop.py:202` and
      `test_clickup_non_active_steps_leave_loop.py:164`, both via a module
      constant `ALICE_CLICKUP`. The instrument caught it on the first run, in
      all 7 tests that construct through them, which is the proof doing exactly
      what it exists for.

      They take an adapter rather than staying local, restoring the remedy
      Decision 5 originally named for this field — "declare a three-line
      subclass overriding that one default, or stay unmigrated; Decision 2's
      proof decides which, per file" — which was dropped when the two-type split
      was believed to absorb the whole `clickup_user_id` disagreement. It did
      not. The adapter is licensed here on the same ground as the clause-(c)
      one: the shared type can produce the exact object, the adapter supplies
      the pinned value rather than relocating a difference, and **the proof
      still ran over it and passed**. Both files are `clickup_sync` tests
      sitting opposite `clickup_sync.py:140`, so leaving them local would have
      cost Goal 3 two of its 52 for three lines.

      Verification: commit tier **2,482 passed** (baseline exactly), integration
      **159 passed** with `COMMERCE_OPS_REQUIRE_DATABASE=1`, `mypy` clean over
      520 files, `ruff check`/`format` clean, and `assert_identity.py` across
      the pair reports all four node kinds identical in every one of the 53
      changed files with the `def test_` count unchanged at 453.
      **142 insertions, 479 deletions.**

## 4. `CatalogProduct` — 40 declarations, expectation 31

- [x] 4.1 Measure per file as in 3.1. Known — the 33 frozen dataclasses are
      **four** groups, not two:

      | count | shape |
      |---|---|
      | 24 | exactly `name: str; sku: Sku` |
      | 6 | the same, defaulting to `PRODUCT_NAME` / `PRODUCT_SKU` |
      | 2 | `name`, `sku` **and a required `stage`** — `test_briefing_assembly.py:268`, `test_briefing_delivery.py:233` |
      | 1 | `name`/`sku` defaulted to the same literals by another spelling — `test_step_handler_contract.py:116` |

      The 7 plain classes are a fifth group, at least one carrying `id`,
      `marketplace_id`, `sub_category` and `hazard_categories` — a different
      object entirely.
- [x] 4.2 Add `CatalogProduct` as a **`@dataclass(frozen=True)`** — the form 33
      of the 40 declare — carrying `name` and `sku` and **not** `stage`, with
      its protocol and `_conforms`. Defaults from `tests.support.fixtures` where
      the local default *is* that literal; `fixtures.py`'s own rule is that
      migration matches on the value, so `test_step_handler_contract.py:116`
      migrates despite spelling its defaults differently.

      **`stage` is excluded and the two files that declare it stay local.** Only
      `briefing` reads `stage`, and it reads it directly rather than by shape;
      adding an optional `stage` to a launch-facing double would hand 30
      declarations an attribute whose absence previously raised, to satisfy two
      tests in another bounded context. That is the type-bending Decision 3 and
      risk 5 both refuse. Expectation is therefore **31 of 40**, not 33.
- [x] 4.2a The 7 plain-class declarations stay local, by `design.md` Decision 3
      clause (b) and not by field breadth. Two of them —
      `test_compliance_screen_failure_and_context.py:314` and
      `test_compliance_screen_verdict_routing.py:399` — say in their own
      docstrings that the plain form is deliberate, because
      `catalog.domain.product.Product` is plain and `!r` must leak
      `<... object at 0x...>` "exactly as it would in production". Quote that
      reason in the record rather than filing them under "field breadth".
- [x] 4.3 Instrument, verify, settle, verify — as 3.3–3.8. **The instrument
      commit runs the integration tier too**: two of the 40 declarations are at
      `test_eager_convergence_atomicity_live.py:225` and
      `test_pending_result_delivery_seam_live.py:267`, which the commit tier
      never imports.
- [x] 4.4 Record the not-migrated: the 7 plain-class variants, with 4.2a's
      reason for two of them and the measured reason for the rest.

      **The record: 31 of 40, exactly as planned.** 33 files changed, 107
      insertions against 226 deletions. The proof found **no disagreement at
      all** — every one of the 31 agreed with the shared defaults on every
      construction the suite performs, which is what licenses
      `PRODUCT_NAME`/`PRODUCT_SKU` as the defaults.

      Not migrated, 9 declarations:

      | count | why |
      |---|---|
      | 7 | plain classes carrying `id`, `marketplace_id`, `sub_category` and in two cases `hazard_categories` — a different object wearing the same name. Clause (b). Two of the seven document the plain form as deliberate, for `!r`. |
      | 2 | `test_briefing_assembly.py:268` and `test_briefing_delivery.py:233` declare a required `stage`, read only by `briefing` and read directly rather than by shape. Clause (a), and 4.2's reason for not carrying it. |

      `test_step_handler_contract.py:116` **did** migrate: it spells its
      defaults `'Bamboo Cutting Board'` and
      `field(default_factory=lambda: Sku('BCB-2027-01'))` where the other six
      import `PRODUCT_NAME`/`PRODUCT_SKU`, and `fixtures.py`'s rule is that
      migration matches on the value, not the identifier. The proof confirmed
      the values agree.

      One process finding worth recording: instrumenting all 38 declaring files
      rather than the 31 in scope produced 125 failures in one run — the
      clause-(b) population failing loudly, as it should. The exclusion list is
      derived from the 2.3 measurement, not from the name.

## 5. `Record` — 30 declarations, expectation 29

**30, not 31.** `^class _Record:` matches 31 files; the 31st is at
`test_startup_handler_report_holds_the_registry.py:259`, inside
`_REPORT_DRIVER_SCRIPT: Final = '''...'''` (lines 214–318) — a driver script
written out and run in a subprocess, so it is source text rather than a
declaration in that module. Do not migrate it and do not count it.

- [x] 5.1 The 30 are **three field sets** and **three constructor signatures**,
      and both matter:

      | count | fields | `__init__` |
      |---|---|---|
      | 16 | `definition`, `display_order`, eight provenance fields | `(self, definition, display_order: int = 10)` |
      | 13 | the same, or `definition`+`display_order` alone | `(self, definition, display_order: int)` |
      | 1 | `definition` and the eight provenance fields, **no `display_order`** | `(self, definition)` |

      State the shared type's **full field list and every default explicitly**,
      as tasks 6.1 and 8.2 do for theirs. A two-field type built from "they
      differ only in `display_order`" would fail clause (a) against 28
      declarations.

      **`display_order` defaults to `10`**, per `design.md` Open Question 1 —
      what 16 locals produce, inside the compared intersection. The eight
      provenance fields default to `None`, which is what every declaration
      carrying them uses.
- [x] 5.2 `test_launch_report_step_facts.py` **keeps its own declaration**, and
      the reason is recorded rather than inferred. It declares no
      `display_order`; production reads that field at four sites as
      `getattr(row, "display_order", 0)` — `playbook_authoring.py:180` and
      `:428`, `playbook_admin.py:911`, `playbook_repository.py:154` — and the
      file drives `update_step` into `_as_record`, so absence yields **`0`** on
      a path it exercises. A shared default of `10` would move that read
      silently, because the field is outside the compared intersection. Lowering
      the shared default to `0` to keep this one file would instead break 16
      declarations loudly. Expectation is therefore **29 of 30**.
- [x] 5.2a For `test_check_step_handlers_reads_the_authored_set.py`, which
      declares `definition` and `display_order` and none of the eight provenance
      fields, run the clause-(a) check on those eight: absence raised there, and
      a `None` default returns instead. Record the result, not the expected
      result. If anything reads one on a path that file exercises, it stays
      local too and the expectation drops to 28.
- [x] 5.3 Resolve the open half of `design.md` Open Question 1 — the shallow
      comparison, the `display_order` default being settled there already.
      `Record` holds a production `StepDefinition`, so it is the one type whose
      field values are production objects. Confirm the shallow comparison is right here — two references to
      the same `StepDefinition` compare equal by identity, and recursing would
      compare production against itself. If shallow turns out to be wrong here,
      say so and stop rather than deepening it silently.
- [x] 5.4 Add `Record` as a **plain class** — all 30 declarations are plain, so
      there is no form split here — with its protocol and `_conforms`;
      instrument, verify, settle, verify; record the not-migrated.

      **The record: 29 of 30.** 30 files changed. The proof found no
      disagreement across the 29.

      Not migrated: `test_launch_report_step_facts.py`, per 5.2 — it is the one
      declaration with no `display_order` field, so the shared default of `10`
      would move an exercised production read from `0` silently.

      5.2a resolved in the shared type's favour:
      `test_check_step_handlers_reads_the_authored_set.py` declares only
      `definition` and `display_order`, and gains the eight provenance fields as
      `None`. `src/` reads those only as direct attributes on ORM rows, never
      off a double — and a double lacking them that reached such a read would
      already raise today, so the green suite is the evidence that none does.
      It migrated, and the proof passed on it.

## 6. `TaskMapping` — 19 declarations, expectation 19

The clearest case for Decision 3's subset rule: 2 bodies, the shorter a strict
prefix of the longer, no disagreement anywhere.

- [ ] 6.1 Add `TaskMapping` as a **`@dataclass`** (all 19 declarations are, none
      frozen) with all seven fields, `retained_*` defaulting to `None` and
      `last_observed_closed` to `False`.
- [ ] 6.2 Same-value check: `clickup_sync.py:514-515` reads `retained_name` and
      `retained_body`, and `:536` reads `retained_assignees`, each through
      `getattr(mapped, name, None)`. The 7 short-form declarations produce
      `None` there today, so the shared defaults must be `None` — which they
      are. Record the check; it is one line and it is the whole risk.
- [ ] 6.3 Instrument, verify, settle, verify; record the not-migrated.

## 7. `PendingRow` — 16 declarations, expectation 9

The one name whose earlier expectation was arithmetic rather than measurement.
Measured, the 16 are six groups:

| count | form | fields |
|---|---|---|
| 7 | `@dataclass` | `product_id, step_id, handler, proposed_outcome, result_text, produced_at, state, delivered_at, decided_by, decided_at` |
| 2 | `@dataclass` | the same, less `decided_by` and `decided_at` |
| 2 | `@dataclass` | the canonical ten **plus `extra: dict[str, Any]`** |
| 2 | `@dataclass` | the canonical ten **plus `id`, declared first** |
| 2 | plain | seven fields |
| 1 | plain | six fields |

- [ ] 7.1 The shared type is a **`@dataclass`** carrying the canonical ten, with
      `state='pending'` and `delivered_at` / `decided_by` / `decided_at`
      defaulting to `None`. State every default explicitly, as 5.1, 6.1 and 8.2
      do.
- [ ] 7.2 That takes **9 of 16** — the 7 canonical and the 2 subsets. The 3
      plain declarations are out under clause (b). The 4 remaining dataclass
      declarations are supersets, and each needs a recorded decision rather than
      an assumption:

      - the 2 adding `extra` migrate only if the shared type carries
        `extra: dict[str, Any] = field(default_factory=dict)`, which would hand
        the other 11 an attribute they never had. Run the `src/` shape search
        first; if nothing reads `extra`, adding it raises this name to 11.
      - the 2 adding `id` **declare it first**, so every positional construction
        in those files means something different against the canonical field
        order. That is a clause-(c) failure, not a clause-(a) one: an adapter
        subclass fixes it, or they stay local. **Do not reorder the shared
        type's fields to accommodate them** — that breaks the 9.
- [ ] 7.3 Check the `automation_pass.py` probes against this type before fixing
      defaults — `("noted_kind", "outcome_kind", "outcome", "kind",
      "noted_outcome")` at :209, `("noted_at", "when")` at :217 and
      `("reported_at", "reported", "has_been_reported")` at :225. If the shared
      type adds any spelling those probes read earlier than the one the locals
      populated, the same-value invariant applies and is recorded here. **If it
      does not, say so explicitly** — an unstated absence reads the same as an
      unchecked one.
- [ ] 7.4 Add the type, protocol and `_conforms`; instrument, verify, settle,
      verify; record the not-migrated and the outcome of 7.2's two decisions.

## 8. `FakeTask` — 15 declarations, expectation 15

Carries `design.md` Decision 6, the invariant's sharper instance.

- [ ] 8.1 Add `FakeTask` as a **`@dataclass`** (all 15 are, none frozen), with
      **`description` defaulting to `None`**. Measured:
      `clickup_sync.py:517` reads `getattr(task, "description", None)`, and of
      the 15 locals 5 carry neither spelling, 5 carry `body` only, 4 carry
      `description` only and 1 carries both — so 10 of 15 exercise
      `task_body = None` today and a populated default would change them
      silently, with `mypy`, the AST check and the suite all still green.
- [ ] 8.2 State `FakeTask`'s **full field list and every default**, not only
      `description`'s. Two of them are governed by production reads and are not
      free choices:

      | field | default | why |
      |---|---|---|
      | `description` | `None` | 8.1 — `clickup_sync.py:517` |
      | `assignees` | `()` | `clickup_sync.py:537` reads `getattr(task, "assignees", ())`, and 9 of the 15 locals do not declare it |
      | `body` | its own | nothing in `src/` reads `task.body`; `retained_body` on the *mapping* is what production compares against |

      For every remaining field, record the default and the search that shows
      whether `src/` reads it by shape. A field added without that search is the
      defect `design.md` risk 2 names.
- [ ] 8.3 Instrument, verify, settle, verify — **the instrument commit runs the
      integration tier too**, for the declaration at
      `test_eager_convergence_atomicity_live.py:271`. Record the not-migrated. One
      declaration carries a behaviour method; if it cannot be reproduced by the
      shared dataclass it stays local and the expectation drops to 14.

## 9. `CreatedTask` — 14 declarations, expectation 14

- [ ] 9.1 One body across 14 declarations, modulo a docstring on one, and all 14
      are `@dataclass(frozen=True)` — so the shared type is too. Add the type,
      protocol and `_conforms`; instrument, verify, settle, verify — **the
      instrument commit runs the integration tier too**, for the declaration at
      `test_eager_convergence_atomicity_live.py:282`. If this name does not land
      at 14, something is wrong with the procedure rather than with the name —
      stop and say so.

## 10. Records and completion

- [ ] 10.1 Correct `docs/deferred-work.md`'s tolerance table — **by re-running
      the shape measurement, not by copying `design.md`'s table.** Every previous
      version of that entry was assembled by grepping a spelling, which is why it
      has now been stale three times; the measurement that supersedes it is
      structural (a `getattr` over a loop variable ranging across a tuple of
      string literals, whatever the loop variable is named) and finds **ten**
      probes, six of them the member-shape probe. `playbook_admin.py:321`,
      `activation_readiness.py:204`, `roles.py:729`, `gate_decisions.py:105` and
      `automation_pass.py:209/217/225` appear in no version of the entry.
      **Do not report the three recorded line numbers as stale**: they anchor on
      the enclosing `def` (`clickup_sync.py:139`, `playbook_authoring.py:266`,
      `gate_progression_job.py:267`) where this change's tables anchor on the
      `for`, and all three are exactly where the entry puts them. The finding is
      the seven omissions, and it carries the argument on its own.
      **Record the method beside the result**,
      so the next correction starts from a method rather than from a list. Note
      that all 52 member doubles now expose `identifier`, so the second and third
      branches of all six member probes are dead. **Do not delete any probe** —
      that is `unify-launch-adapter-dependencies`.

      **The shape measurement adds to that table; it does not replace it.** It
      finds `getattr` over a tuple of string literals and nothing else, so it
      cannot see two entries that still stand: `gate_progression_job.py:256`
      (`_crossed`, a `getattr` with a default) and `clickup_sync.py:128`
      (`_members`, which probes three *reader shapes* — `list_members()`, a
      callable, a plain iterable — not three attribute spellings). Both must
      survive the correction; dropping a live tolerance while correcting a stale
      table would be a worse outcome than the staleness.

      Correct the entry's closing sentence too. It currently says the tolerance
      "closes behind **`share-the-test-doubles`** … and
      `unify-launch-adapter-dependencies`", naming a change that 10.2 splits out
      of existence. It should name `share-the-value-doubles` and
      `share-the-stateful-fakes`, and say that those two make deletion *safe*
      while the deletion itself belongs to
      `unify-launch-adapter-dependencies`.
- [ ] 10.2 Update `docs/proposed-change-order.md` — **two edits, not one.**

      First, §4: `share-the-test-doubles` becomes two entries,
      `share-the-value-doubles` and `share-the-stateful-fakes`, with the
      composition reason for the ordering and the note that the stateful slice
      inherits the shared leaves. **The two new entries must not copy forward
      §4's two superseded claims**: that the equivalence proof "caught **five**
      real defects", where `proposal.md` reduces the warrant to at least two
      attributable to the proof itself; and that the tolerance entry "closes
      behind this change", where deletion belongs to
      `unify-launch-adapter-dependencies` and these slices only make it safe.

      Second: confirm task **1.5**'s ordering edit is still in place —
      `unify-launch-adapter-dependencies` recorded as following
      `share-the-value-doubles`, and placed accordingly. It is done first
      deliberately, so the constraint exists while this change is in flight
      rather than after it. Renumber per that file's own rule and keep
      cross-references by name.
- [ ] 10.3 Correct the two `tests/support/` docstrings that this change makes
      false. `__init__.py` says "**The shared fakes are not here yet**" and gives
      the identity-`==` reason for the whole population; `protocols.py` opens
      "Intentionally empty, and not an accident … none were deleted -- they were
      never written". Both must now distinguish the value doubles (landed here)
      from the stateful fakes (still deferred), and `__init__.py`'s reason must
      narrow to the population it is actually true of. Leave `protocols.py`'s
      statement that the protocols are temporary, and `__init__.py`'s
      never-re-exported rule, exactly as they stand. This is the same class of
      finding the parent change's own `/code-review` raised four times (archived
      `tasks.md` 8.5) — docs describing deferred work in the present tense.
- [ ] 10.4 Record `Member` / `MemberValue` as a known follow-up: two shared types
      for one concept, differing only in equality semantics, hashability and one
      default, collapsing when `unify-launch-adapter-dependencies` lands
      production's own type. `design.md` risk 5 has the reasoning; the record is
      so it is not rediscovered as a defect.
- [ ] 10.5 Update `AGENTS.md`'s "The shared harness" section. Its four fake
      rules are written as binding on "whoever writes the first one, since there
      is no instance in the tree to copy yet" — after this change there is.
      Point at the instances, and keep `tests/unit/support/` described as
      arriving with the *stateful* slice, which is still true.

      Narrow the section's other over-general sentence too — "the fakes were cut
      to a follow-up because their `==` is identity, which makes the equality
      proof the value builders were migrated under inexpressible for them". That
      is the same over-generalisation 10.3 fixes next door in
      `tests/support/__init__.py`, and this change's central claim is that it is
      false for 400 of the 1,199: the proof *was* expressible for the value
      doubles, as field comparison, and is what they migrated under.
- [ ] 10.6 Record every file left unmigrated, per name, with its reason, in the
      final commit message. A file skipped because its variant resisted the
      shared type is a finding, not a silence.
- [ ] 10.7 Full verification across all three tiers, integration with
      `COMMERCE_OPS_REQUIRE_DATABASE=1`. **Collected counts must equal task
      1.1's exactly, with no exclusion** — this slice adds no test of its own
      (`design.md` Decision 9), so the strong form of the invariant is available
      and is what is used. Report line reduction against the plan commit and
      wall time; wall time is a report, not a claim.
- [ ] 10.8 Run `/code-review` over the full diff before calling the change done
      (`AGENTS.md` — Independent review before completion). Not
      `openspec-change-reviewer`, which reviews plans and explicitly not the code
      that follows them.
