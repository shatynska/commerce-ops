# Test manifest — add-playbook-admin-ui

Written by the test-writer pass, before any implementation of this change
exists. Derived strictly from this change's delta specs; no implementation
source was read (existing tests under `tests/**/test_*.py`, the prior
change's archived manifest, and the main specs under `openspec/specs/`
were the only other inputs). **This manifest is not an artifact the
OpenSpec schema knows about**: it will not appear among
`openspec instructions apply`'s context files and must be read
deliberately by whoever implements the change.

## Baseline

Recorded before any new test was written:

- `uv run pytest tests/unit tests/agents` — **621 passed, 0 failed**
  (scoped to the commit-time tiers; scope per `AGENTS.md`).
- `tests/integration` was **not run**: it needs a live Postgres and
  `DATABASE_URL` is unset in this environment. Every claim below about
  integration tests is therefore about their expected behavior, not an
  observed run.

First-run results of the new tests (observed after writing):

- `tests/unit/launch/application/test_playbook_reorder.py` — collection
  fails: `ImportError: cannot import name 'reorder_step'` — the
  absent-target state. Notably `StaleStepSetError` imported fine, so
  `design.md`'s claim that it is already exported holds.
- `tests/unit/launch/domain/test_within_gate_order_commitment_neutrality.py`
  — **4 passed**. Target-exists case, documented in the file: the
  commitment machinery already ignores same-gate step sequence; these
  pin that invariant so implementing the authored order cannot break it.
- `tests/unit/access/application/test_admin_capability.py` — collection
  fails: `ImportError: cannot import name 'resolve_admin_capability'`.
- `tests/unit/access/application/test_admin_session_use_cases.py` —
  collection fails: `ImportError: cannot import name
  'exchange_link_token'` (mint/verify equally absent).
- `tests/unit/access/infrastructure/test_admin_link_exchange_route.py` —
  collection fails: `ImportError: cannot import name 'mint_admin_link'`;
  the `admin_link` driving module is equally absent.
- `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`
  — collection fails: `ImportError: cannot import name 'playbook_admin'`.
- `tests/integration/launch/test_playbook_ordering_live.py` — not
  executed (no `DATABASE_URL`); fails at import regardless
  (`reorder_step`) until the use case exists.

After writing: `uv run pytest tests/unit tests/agents -q
--continue-on-collection-errors` — **625 passed, 5 errors** (the five
absent-target files above). Every pre-existing test still passes.
`uv run ruff check` and `uv run ruff format` are clean over the seven
new files. `mypy` was not run: it fails on the deliberately absent
imports, which is the same absent-target fact pytest already reports.

⚠ Pre-commit note: the commit-time pytest hook runs the whole
`tests/unit`+`tests/agents` tree, so commits will be blocked by the five
absent-target files until the implementation lands (same situation as
the previous change's pass).

## Properties the dispatcher can rely on

- **This pass is additive only**: no existing test file was edited,
  deleted, or disabled — under any delta operation. The only file
  written outside `tests/**/test_*.py` is this manifest.
- **No implementation was written**: no module, stub, or `__all__` entry
  was created to make the failing tests execute. Their failure is the
  expected, reported outcome.

## New test files

- `tests/unit/launch/application/test_playbook_reorder.py`
- `tests/unit/launch/domain/test_within_gate_order_commitment_neutrality.py`
- `tests/unit/access/application/test_admin_capability.py`
- `tests/unit/access/application/test_admin_session_use_cases.py`
- `tests/unit/access/infrastructure/test_admin_link_exchange_route.py`
- `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`
- `tests/integration/launch/test_playbook_ordering_live.py`

All test names below are runner-selectable
(`uv run pytest <file>::<test_name>`).

## Scenario accounting

Every `#### Scenario:` block of this change's delta specs, each
accounted exactly once. **37 scenarios total**: 3 (launch-playbook,
MODIFIED) + 7 (playbook-authoring) + 4 (access-scope) + 11
(admin-session) + 12 (playbook-admin). "Existing:" names a pre-existing
test that covers a scenario the MODIFIED delta restates without
behavioral change at that test's level.

### launch-playbook — Requirement: Gate sequence orders the launch (MODIFIED)

1. **Gates expose a stable order** — unchanged by the delta; existing:
   `tests/unit/launch/domain/test_launch_playbook.py::test_gates_expose_a_stable_order`
   stays authoritative.
2. **Steps at a gate are served in their authored order** —
   `tests/integration/launch/test_playbook_ordering_live.py::test_a_reorder_is_served_on_the_next_read`
   (the authored-order clause: an authored order is read back) and
   `::test_two_reads_with_no_intervening_write_serve_the_same_order`
   (the stability clause, over every gate). The write-side slot
   assignments feeding the serve are every test in
   `test_playbook_reorder.py`. **Deliberately not duplicated at the
   unit tier**: with no write involved, the only unit observation is
   the test file's own sort of its own fake records — a tautology
   (recorded in `test_playbook_reorder.py`'s trailing comment block).
3. **Steps at the same gate are unordered** (retained name, revised
   meaning: unordered to the commitment machinery) —
   `tests/unit/launch/domain/test_within_gate_order_commitment_neutrality.py::test_blocking_evaluation_is_identical_under_any_step_order`
   and `::test_step_completion_is_identical_under_any_step_order`
   (each parametrised over the two permutations — the permutation *is*
   the reorder at this level). The pre-change formulation's test is
   obsolete-candidate O-1 below.

### playbook-authoring — Requirement: A gate's steps can be reordered (ADDED)

4. **A moved step is served in its new slot** — split:
   `test_playbook_reorder.py::test_a_moved_step_is_served_in_its_new_slot`
   (slots, relative order, provenance) +
   `test_playbook_ordering_live.py::test_a_reorder_is_served_on_the_next_read`
   (the real adapter's next read).
5. **A stale reorder is rejected whole** —
   `test_playbook_reorder.py::test_a_stale_reorder_is_rejected_whole`.
   The superseding write is simulated at the conditional save
   (`StaleStepSetError`), the point `design.md` fixes for write
   serialization; a real interleaving is not deterministically
   observable through this seam (same accounting as the prior change's
   scenario 42).
6. **A reorder never leaves the step's own gate** —
   `test_playbook_reorder.py::test_a_reorder_never_leaves_the_steps_own_gate`.

### playbook-authoring — Requirement: Every live step holds a slot in its gate's order (ADDED)

7. **A created step appends to its gate** — split:
   `test_playbook_reorder.py::test_a_created_step_appends_to_its_gate` +
   `test_playbook_ordering_live.py::test_a_created_step_is_served_last_in_its_gate`.
8. **An un-retired step rejoins at the end** — split:
   `test_playbook_reorder.py::test_an_unretired_step_rejoins_at_the_end` +
   `test_playbook_ordering_live.py::test_an_unretired_step_is_served_last_whatever_slot_it_held`.
9. **A gate change appends to the new gate** —
   `test_playbook_reorder.py::test_a_gate_change_appends_to_the_new_gate`.
10. **Retirement closes the gap** —
    `test_playbook_reorder.py::test_retirement_closes_the_gap`; also
    exercised live inside
    `test_playbook_ordering_live.py::test_an_unretired_step_is_served_last_whatever_slot_it_held`.
    The requirement statement's initial-order clause ("SHALL keep the
    order it was being served in" at migration time) is **deliberately
    untested**: a migration-moment property, wrong to assert on any
    database whose steps have since been reordered (recorded in the
    integration file's docstring).

### access-scope — Requirement: A principal can be declared admin-capable (ADDED)

All in `tests/unit/access/application/test_admin_capability.py`:

11. **A declared entry resolves admin-capable** —
    `::test_a_declared_entry_resolves_admin_capable` (the entry's grant
    is the *empty* SKU list, pinning orthogonality). This is the
    discriminating test of the four — see the file's note on the other
    two possibly passing vacuously if the current loader ignores
    unknown keys.
12. **Visibility grants confer nothing** —
    `::test_visibility_grants_confer_nothing`.
13. **An unknown identity fails closed** —
    `::test_an_unknown_identity_fails_closed`.
14. **A malformed admin declaration is rejected at load** —
    `::test_a_malformed_admin_declaration_is_rejected_at_load`
    (parametrised: string, quoted-true, number).

### admin-session — Requirement: An admin-capable principal can request an admin link from Slack (ADDED)

15. **An admin-capable principal receives a link** — minting half:
    `test_admin_session_use_cases.py::test_minting_for_an_admin_capable_principal_binds_a_short_lived_token`
    (link, principal binding, ≤10-minute expiry from the requirement
    statement); the token-to-principal binding is also verified
    end-to-end by `::test_a_token_exchanges_once_for_a_bounded_session`.
    **Uncovered remainder, with reason**: the reply being ephemeral and
    visible only to the caller — no artifact names the Slack command's
    registration module or handler seam, so a handler-level test would
    be pure guesswork with no correction point; recorded for the
    implementation step to cover once `tasks.md` 2.4 fixes the seam.
16. **A visibility-only principal is refused like an unknown one** —
    `::test_a_visibility_only_caller_is_refused_exactly_like_an_unknown_one`:
    both caller kinds get one and the same use-case outcome (`None`,
    nothing minted), which structurally *prevents* the handler from
    distinguishing them. **Uncovered remainder**: the ephemeral refusal
    message's wording — same reason as 15.
17. **An unknown caller's refusal confirms nothing** — same test as 16;
    no token exists and no URL is answered, so nothing confirmable
    reaches the handler. Same uncovered remainder as 16.

### admin-session — Requirement: A link token is single-use and short-lived (ADDED)

18. **A token exchanges once** — split:
    `test_admin_session_use_cases.py::test_a_token_exchanges_once_for_a_bounded_session`
    (session for the token's principal; ≤12-hour bound) +
    `test_admin_link_exchange_route.py::test_a_fresh_token_exchange_establishes_a_session_cookie`
    (the route half: not the absence shape, cookie set, session stored
    before the response).
19. **A spent token is refused like nothing** — split:
    `test_admin_session_use_cases.py::test_a_spent_token_is_refused_like_one_that_never_existed`
    +
    `test_admin_link_exchange_route.py::test_a_spent_token_is_refused_like_a_route_that_does_not_exist`
    (shape equality against this very app's unregistered-route
    response). The requirement statement's never-minted case:
    `::test_a_token_the_system_never_minted_is_refused_identically`.
20. **An expired token is refused identically** — split:
    `test_admin_session_use_cases.py::test_an_expired_token_is_refused_identically`
    +
    `test_admin_link_exchange_route.py::test_an_expired_token_is_refused_identically`.

### admin-session — Requirement: A browser session is bounded and rides a hardened cookie (ADDED)

21. **A session outlives its usefulness and stops working** —
    verification half:
    `test_admin_session_use_cases.py::test_a_session_outlives_its_lifetime_and_stops_working`
    (refused exactly as an unknown session); response-shape half:
    generically by
    `test_playbook_admin_page.py::test_no_session_means_no_surface`
    (any verification-refused request takes the no-session shape).
    The 12-hour bound itself is asserted in scenario 18's use-case test.
22. **The cookie is hardened** —
    `test_admin_link_exchange_route.py::test_the_cookie_is_hardened_against_page_script`
    (HttpOnly, unconditional) and
    `::test_the_cookie_is_marked_secure_when_deployed` (Secure under
    the invented `deployed` switch — see Q10).
    **Deliberately untested**: the requirement statement's "SHALL NOT
    establish a session by any path other than the token exchange" — a
    universal negative; its strongest observable instances (no session
    from a refused exchange; no surface without a verified session) are
    covered above.

### admin-session — Requirement: Admin access fails closed and absence-shaped (ADDED)

23. **No session means no surface** —
    `test_playbook_admin_page.py::test_no_session_means_no_surface`:
    no-session and refused-session requests both equal the app's own
    unregistered-route response in status, body, and content type; a
    verified session sees the page, so the equality is not a dead
    router.
24. **Removal from the directory revokes access on the next request** —
    `test_admin_session_use_cases.py::test_removal_from_the_directory_revokes_on_the_next_request`
    (verification against the edited directory refuses the unexpired
    session); the refusal's response shape is covered generically by
    scenario 23 (one dependency produces the shape — `design.md`
    Decision 7).
25. **Withdrawing the admin declaration revokes access likewise** —
    `test_admin_session_use_cases.py::test_withdrawing_the_admin_declaration_revokes_likewise`
    (the entry remains, only the declaration is gone — discriminating
    capability re-resolution from membership re-checking).

### playbook-admin — all four requirements (ADDED)

All in
`tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`:

26. **The whole live set is one page** —
    `::test_the_whole_live_set_is_one_page` (every live step rendered;
    gates grouped in gate order; within-gate authored order that
    disagrees with identifier order).
27. **Filters narrow without altering** —
    `::test_filters_narrow_without_altering`.
28. **Search matches description text** —
    `::test_search_matches_description_text`.
29. **Retired steps are reachable but set apart** —
    `::test_retired_steps_are_reachable_but_set_apart` (the control is
    discovered from the page; a query-parameter fallback is documented).
30. **A clean edit lands** — `::test_a_clean_edit_lands`.
31. **A rejected edit shows every fault** —
    `::test_a_rejected_edit_shows_every_fault` (two coherence faults:
    a two-line description and a blocking lesson; both fault markers,
    submitted values still present, store untouched).
32. **A stale edit is surfaced, not silently dropped** —
    `::test_a_stale_edit_is_surfaced_not_silently_dropped`.
33. **A created step appears in its gate** —
    `::test_a_created_step_appears_in_its_gate` (generated `mg.*`
    identifier, no identifier input offered, last slot of its gate).
34. **A blocked retirement explains itself** —
    `::test_a_blocked_retirement_explains_itself`.
35. **A move sticks** — `::test_a_move_sticks` (one press of the upward
    control; immediate render and fresh-load agreement).
36. **A stale move leaves truth on the page** —
    `::test_a_stale_move_leaves_truth_on_the_page`.
37. **The identifier cannot be typed into** —
    `::test_the_identifier_cannot_be_typed_into` (no *editable* input
    named for identifier or discipline; hidden routing inputs
    excluded, per the spec's "render as text, not as inputs").

## Assertion classifications

Per `ai-toolkit:testing`, marked inline in each test (`SPECIFIED:` /
`DERIVED:` comments); the derived and deliberately-untested items in
one place:

**Derived (inferred; no stated requirement fixes them):**

- `test_playbook_reorder.py` — the `updated_by`/`updated_on` spelling
  for the moved step's provenance ("as an update's are" fixes the
  symmetry, not the spelling); non-contiguous slot values in fixtures.
- `test_admin_capability.py` — the three malformed-value shapes
  (string/quoted/number), following from the invented boolean spelling;
  the discrimination guard asserting `True` beside each `False`.
- `test_admin_session_use_cases.py` — that refusals are `None` (the
  delta fixes indistinguishability and fail-closure, not the value).
- `test_admin_link_exchange_route.py` — "shape" compared as status +
  body + content type; success asserted as "not the absence shape, and
  a cookie was set" rather than a pinned status code.
- `test_playbook_admin_page.py` — fault-wording markers
  ("description", "lesson"/"block", "changed"); the word "retired" as
  the visible marking; the control-discovery vocabulary and
  query-parameter names (Q11); locating steps by identifier substring
  (fixture descriptions deliberately carry the identifiers so a table
  rendering either is locatable).
- `test_within_gate_order_commitment_neutrality.py` — that the blocking
  rejection names the unsatisfied step (inherited from the existing
  gate-advance tests' reading of `LaunchError`).

**Deliberately untested (recorded, not omitted):**

- The Slack-presentation halves of scenarios 15–17 (ephemeral-only
  visibility, refusal wording) — no registration seam is fixed by any
  artifact; see scenario entries.
- "No session by any path other than the token exchange" (scenario 22's
  requirement statement) — universal negative.
- The migration backfill's "keeps the order it was being served in"
  (scenario 10's requirement statement) — migration-moment property.
- A pure-read unit assertion of serve order (scenario 2) — tautology
  through the fake; integration covers it.
- Design-level details no scenario states: token/session values hashed
  at rest, `SameSite=Lax`, the HTMX signed-out swap hook
  (`design.md` Risks), and real concurrent write interleavings (the
  conditional-save simulation stands in).

## Obsolete-test candidates

Input to a **destructive** action this pass will not take. Every entry
is a **candidate for human confirmation**, never a conclusion. Search
scope: `tests/**/test_*.py` (the dispatched glob), matched on imports
and asserted behavior, plus the prior manifest at
`openspec/changes/archive/2026-08-24-move-playbook-steps-to-postgres/test-manifest.md`
as the scenario-to-test map for the pre-change suite. This change
carries one MODIFIED delta (`launch-playbook`), so the list is
applicable.

- **O-1**
  `tests/unit/launch/domain/test_launch_playbook.py::test_steps_at_the_same_gate_carry_no_ordering`
  — superseded by the MODIFIED requirement *Gate sequence orders the
  launch*. Evidence: its docstring and the `ORDERING_ATTRIBUTE_NAMES`
  comment quote the removed sentences verbatim ("Step definitions
  attached to the same gate SHALL carry no ordering relative to one
  another"; "Gates SHALL be the only ordering primitive"), and its
  closing loop asserts `StepDefinition` exposes no attribute named
  `position`/`order`/`sequence`/`index`/`rank`/… — a universal the
  revision withdraws (steps now carry an authored order; gates remain
  the only *commitment* ordering primitive). Disposition depends on
  where the implementation homes the slot: if it stays in the serving
  layer (`design.md` Decision 1), the test still passes and the
  candidate action is *reframing* its premise to the revised scenario
  (which `test_within_gate_order_commitment_neutrality.py` now covers
  behaviorally) rather than deletion; if the slot reaches
  `StepDefinition`, the attribute probe fails and must be
  dispositioned by a human. Replacement coverage for the revised
  scenario: `test_within_gate_order_commitment_neutrality.py`.

No other bearing test was found: the search covered ordering-flavored
assertions across the glob (`unordered`, `no ordering`, `ordering
primitive`, `sorted`/`order` in the repository, seed, and
authoring-live files) and found no test asserting a serve order by
identifier or otherwise. Stated explicitly: none was found **by this
search**, which is not proof none exists.

## Invented interfaces / unresolved project questions

Each taken because no artifact or recorded convention answers it; the
tests depending on each are named. The correction point for every entry
is a single helper, fake, or constant, documented in the owning file's
docstring.

- **Q1 — `reorder_step` call shape and index base**:
  `reorder_step(steps=, principal=, step_id=, target_index=)`,
  0-based, following the implemented siblings rather than `design.md`
  Decision 3's illustrative signature (which lists `expected_version`
  and `today` that no implemented write carries). Depends:
  `test_playbook_reorder.py`, `test_playbook_ordering_live.py`.
- **Q2 — the record's order attribute**: `display_order` (int) on the
  stored record, serving order = `(display_order, identifier)` within
  a gate. Depends: the same two files and the page file's store fake.
- **Q3 — the admin declaration's YAML spelling**: `admin: true`;
  malformed = non-boolean. Depends: `test_admin_capability.py`,
  `test_admin_session_use_cases.py`,
  `test_admin_link_exchange_route.py`.
- **Q4 — `resolve_admin_capability(directory, identity=) -> bool`**,
  sync, exported from `commerce_ops.access.application`. Depends:
  `test_admin_capability.py`.
- **Q5 — the session use cases' call shapes**, ports-first:
  `mint_admin_link(directory, tokens, identity=, base_url=, now=)`,
  `exchange_link_token(tokens, sessions, token=, now=)`,
  `verify_admin_session(directory, sessions, session_id=, now=)`,
  each answering a value or `None`. **`now=` is the injected clock** —
  if the implementation reads a real clock internally, the expiry
  tests need a patch point instead. Depends:
  `test_admin_session_use_cases.py`, `test_admin_link_exchange_route.py`.
- **Q6 — the store protocols**: `LinkTokenStore.save(token_hash=,
  principal=, expires_at=)` / `.claim(token_hash, now=)` (atomically
  spends); `AdminSessionStore.save(session_hash=, principal=,
  expires_at=)` / `.find(session_hash, now=)`. Hashing lives inside
  the use cases; the tests never compute a hash. Depends: same two
  files.
- **Q7 — the token rides the link as its last `=`- or `/`-delimited
  segment** (`_token_of`). Depends: `test_admin_session_use_cases.py`;
  `test_admin_link_exchange_route.py` requests the minted link
  wholesale and only needs the delimiter for its forged-token test.
- **Q8 — the exchange driving module**:
  `commerce_ops.access.infrastructure.driving.admin_link` exposing
  `router`, with module-level `link_tokens`/`admin_sessions`
  collaborators (the `test_clickup_webhook.py` monkeypatch
  convention). Depends: `test_admin_link_exchange_route.py`.
- **Q9 — the page module**:
  `commerce_ops.launch.infrastructure.driving.playbook_admin` exposing
  `router`, a module-level `steps` store, and `verify_admin_session`
  imported from the access public surface; session cookie named
  `admin_session`. Depends: `test_playbook_admin_page.py`.
- **Q10 — the deployed-environment switch** for the Secure cookie
  flag: a module-level `deployed` flag, monkeypatched `raising=False`
  so a wrong guess fails at the Secure assertion, not silently.
  Depends: `test_admin_link_exchange_route.py::test_the_cookie_is_marked_secure_when_deployed`.
- **Q11 — the page's URL/control vocabulary**: query parameters
  `gate`/`discipline`/`q`/`retired` (the retired control is discovered
  from the page first); control URLs mentioning the step id plus
  `edit`/`retire`/`unretire`/`up`|`top`; forms discovered and
  submitted as parsed (fields addressed by name substring, failing
  loudly on a miss). Depends: every interaction test in
  `test_playbook_admin_page.py`.
- **Q12 — no stack skill exists in the library** for
  FastAPI/Jinja/HTMX/SQLAlchemy beyond `python` (loaded); the pass
  proceeded on `ai-toolkit:testing` + `python`, as the prior change's
  pass recorded for the same stack.

## What the implementation step must make pass

In `tasks.md` order:

1. `tests/unit/launch/application/test_playbook_reorder.py` — tasks
   1.1–1.5.
2. `tests/integration/launch/test_playbook_ordering_live.py` — tasks
   1.1–1.5 (needs a live Postgres with `alembic upgrade head`).
3. `tests/unit/access/application/test_admin_capability.py` — task 2.1.
4. `tests/unit/access/application/test_admin_session_use_cases.py` —
   tasks 2.2–2.3.
5. `tests/unit/access/infrastructure/test_admin_link_exchange_route.py`
   — task 2.5 (and the Slack-presentation gap of scenarios 15–17 to
   close under task 2.4 — see the scenario entries).
6. `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`
   — tasks 3.1–3.7.
7. Keep passing:
   `tests/unit/launch/domain/test_within_gate_order_commitment_neutrality.py`
   (currently green; pins the commitment-neutrality invariant the
   ordering must not break) and the entire pre-existing suite (625
   passing as of this pass).

Obsolete candidate O-1 must be dispositioned by a human, not by this
pass and not silently by the implementation step.
