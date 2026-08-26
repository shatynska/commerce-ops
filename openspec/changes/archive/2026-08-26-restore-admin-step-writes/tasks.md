## 1. Pin the fault before changing anything

These two are **reproduction probes**, not the change's test suite. They exist to hold the diagnosis still while the code moves, and they were derived from a live reproduction rather than from the delta specs. The specification-derived suite is a separate step: `AGENTS.md` — *Test design before implementation* binds it to a test author working strictly from the approved deltas, which is what sections 4 and 5 below reference.

- [x] 1.1 Record the baseline: run `uv run pytest` and note the pass/skip/fail counts, so a later claim that this change fixed something is measured against a number rather than a memory.
- [x] 1.2 Reproduction probe: hand an authoring write a roster collaborator shaped as the real `RosterStore` is — `load()` / `save()` and nothing else — and assert it is refused by name rather than raising `TypeError`. This is the arrangement no existing test makes; every roster double in `tests/unit/launch/` exposes `list_people()`.
- [x] 1.3 Reproduction probe: drive a write route with the page's roster global set to a store-shaped collaborator, and assert the write lands. Today this reproduces the production 500.

## 2. Name the roster collaborator's shape

- [x] 2.1 Introduce the `RosterReader` protocol in `launch.application` — `async def list_people()` — and export it on the module's public surface if the driving adapter needs to name it.
- [x] 2.2 Narrow `playbook_authoring._read_people` to that one shape, dropping the callable and iterable branches. Refuse a collaborator that does not satisfy it by **raising** a named error identifying what was supplied and what was expected — not by adding to the write's fault list, per `design.md` — *A mis-shaped collaborator is raised, not added to the fault list*.
- [x] 2.3 Confirm `_roster_identifiers`, the one caller of `_read_people`, needs no duck-typing of its own once the shape is named, and that it carries the `RosterReader | None` type rather than `Any`. If it reads the collaborator independently, narrow it the same way.
- [x] 2.4 Type the `roster` parameter of `create_step`, `update_step`, `retire_step`, `unretire_step` and `change_step_status` as `RosterReader | None` instead of `Any`, keeping the optionality and its meaning per `design.md` — *The roster stays optional*. Confirm `uv run mypy` now rejects passing a store.
- [x] 2.5 Confirm no existing roster double is invalidated — every one in `tests/unit/launch/` already exposes `list_people()`; if any does not, correct the double rather than widening the protocol back.
- [x] 2.6 Cover the third case the delta names: a write made with **no** roster proceeds and evaluates every rule except the two the roster decides. Add this rather than assume it — it is the case a narrowed protocol is most likely to break by accident.

## 3. Give the page's writes the roster it reads

- [x] 3.1 Add the reader to `playbook_admin`, delegating to the existing `_roster_people()`, so the write path and the read path resolve the roster by the same route.
- [x] 3.2 Pass that reader as `roster=` from all five write routes — `create`, `save_edit`, `retire`, `unretire`, `change_status` — leaving the injected `roster` global as the store, which `_require_admin` still needs for `verify_admin_session`.
- [x] 3.3 Update the module docstring's account of the `roster` collaborator: it is a store the page adapts for two different contracts, and the comment currently records only one of them.
- [x] 3.4 Confirm 1.2 and 1.3 now pass, and that `uv run pytest tests/unit/launch` is green.

## 4. Make a failed write visible

- [x] 4.1 Add the listener to `_admin_header.html`, bound to **`htmx:responseError`, `htmx:sendError` and `htmx:timeout`** — a response the page cannot render, no response, and no response in time. Binding only the first leaves the deploy-restart case as silent as the fault this change removes (`design.md` — *A failed write is surfaced on the client*).
- [x] 4.2 Put the notice container in `_admin_header.html` too, beside the listener, so the listener cannot be shipped without a target to render into.
- [x] 4.3 Mark the notice container `write-failure-notice` for its role — present on every admin page — and let `write-failed` appear only once a failure has been reported into it, so a marker naming an occurrence never outruns the occurrence.
- [x] 4.4 Word the notice to what the page can establish: the write did not complete, what is shown may no longer describe the step set, reload to see it as it stands. It must not claim nothing was saved.
- [x] 4.5 Distinguish the guard's own refusal — an ended session — **client-side**, from the route the page just posted to, and offer the way back. Add no server-side marker: `design.md` — *An ended session is called by its name* records why marking it would weaken the guard's indistinguishability.
- [x] 4.6 Confirm the listener is inert on the two surfaces that boost nothing (`new.html`, the roster admin page) and disturbs neither.
- [x] 4.7 Confirm the server still answers its real status code; the notice is additional to the status, never a substitute for it.

## 5. Close the seam the suite could not see

- [x] 5.1 Add a case to `tests/integration/launch/test_playbook_authoring_live.py` passing a real roster collaborator — **in addition to** the existing `roster=None` cases, not replacing them, since those are the suite's only coverage of the permitted no-roster path.
- [x] 5.2 Verify against a roster that holds active people, not the empty local one — `design.md` — *Risks* records why an empty roster makes the fixed path look like a different failure.
- [x] 5.3 Assert the server-observable half of the failure report in `tests/unit/launch/infrastructure/driving/`: that a rendered admin page carries the listener and a container marked `write-failure-notice`, and that it carries `write-failed` only when a failure has been reported into it. The browser-side half — no response, no response in time, an un-boosted submission — has no test tier in this project (`AGENTS.md` — *Testing Strategy* names three Python tiers) and is confirmed by hand at 6.3 and 6.4 instead.
- [x] 5.4 Assert the surface side of the authoring delta's case 3: a mis-wired collaborator's refusal is **not** rendered among the page's coherence faults and does not re-render the form as a rejected submission.
- [x] 5.5 Assert the server half of *The guard's refusal stays indistinguishable*: an unauthorised POST to a write route answers exactly as a request to an unregistered route does, so the client-side session reading buys nothing at the guard's expense.

## 6. Verify and ship

- [x] 6.1 Run the full verification the project requires: `uv run pytest`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check`, and `lint-imports` for the boundary contracts.
- [x] 6.2 Drive the running admin page by hand — create a step, edit one, change a status, retire and un-retire — and confirm each lands and each is visible in the list.
- [x] 6.3 Confirm the failure path by hand: provoke a failed response and check the page says so; stop the server mid-write and check the no-response path says so too.
- [x] 6.4 Confirm the no-JavaScript degradation the delta requires — with scripting off, a failed write still reaches the admin, even if only as the browser's own error page.
- [x] 6.5 Archive the change (`openspec archive restore-admin-step-writes --yes`) as the last commit before the PR, per `AGENTS.md`.
