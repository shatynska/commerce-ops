## 1. Carry the four facts on the launch report

- [ ] 1.1 Add `name` and `gate` to `ReportedStep` and populate both in `_report_for` (`launch/application/use_cases.py`), from the `StepDefinition`s it already iterates (`design.md` — Decision 4). No new query, no join, no second read.
- [ ] 1.2 Name the gate sequence on `LaunchReport`, from the playbook the use case already holds (`design.md` — Decision 6). Do **not** export `GATE_SEQUENCE` from `launch.application` instead: the point is that a consumer needs neither the gate framework nor the playbook, and an export would hand it both.
- [ ] 1.3 Update every construction site and test fixture that builds a `ReportedStep` or a `LaunchReport`. The proposal's claim that construction sits inside `launch.application` covers the source; fixtures across `tests/unit`, `tests/agents` and `tests/integration` are the part that claim does not cover, and a frozen dataclass gaining two fields breaks each of them.
- [ ] 1.4 Write no code for `blocking`, `overdue`, per-served-step coverage or entry order — the report carries all four already. Their delta requirements close spec gaps; their tasks are the tests in 7.2, not changes here. Confirm rather than implement, and if any turns out not to hold, stop: that is a different change.

## 2. The read model

- [ ] 2.1 Define frozen dataclasses for each rendered thing — a list row, the detail page, a step line, and (**blocked on `add-launch-journal`, with 4.8**) a journal line — in the new driving module (`design.md` — Decision 2). Typed, not `dict[str, Any]`: `playbook_admin.py:719`'s `_row(...) -> dict[str, Any]` is the shape this exists to avoid, and mypy cannot check what a template reads out of a dict.
- [ ] 2.2 Keep construction of these separate from rendering, so shaping is testable without a template. This is the whole reason the layer is being introduced, and it is not enforced by any requirement — if it is skipped, the change silently reverts to `playbook_admin.py`'s shape.

## 3. The launch list

- [ ] 3.1 **Gated by 6.1** — confirm the import-linter contract before this task, not after it. Add `launch/infrastructure/driving/launch_admin.py` with the list route at `/admin/launches`, riding the same admin-session guard `roster_admin.py` and `playbook_admin.py` ride; refusal is the app's own 404.
- [ ] 3.2 Resolve the caller's `AccessScope` from the session principal via `resolve_scope`, and pass it to every read (`design.md` — Decision 3). Do **not** pass `AccessScope.unrestricted()` directly: it is observationally identical today and silently wrong the moment product-level scoping exists.
- [ ] 3.3 Pass the render date as the reports' `as_of` (`design.md` — Decision 7). `read_launches` takes it; a defaulted or fixed date satisfies most tests and is the failure R1 names.
- [ ] 3.4 Join product identity from `catalog.application`'s `list_products` — one read for the page, not one per row. Render a launch whose product does not resolve by its raw identifier, and render **every** row that way if the read fails wholesale (`design.md` — Decision 1). Failing the page is the one outcome forbidden.
- [ ] 3.5 Filter the default view by the catalog stage: launches whose product is steady-state or retired do not render. Treat an unresolvable product as in play. Derive the mark from the stage — steady-state versus retired — never from the launch's gate, since a product can reach steady state without this launch graduating.
- [ ] 3.5a Render each row with its product, its current gate, its launch date **or an explicit statement that it has none**, its at-risk state and its awaiting-confirmation state. The last two are rendered marks, not merely inputs to the ordering in 3.6 — a row that sorts into the at-risk band without saying it is at risk satisfies the sort and fails the requirement. The undated case is spelled out because a blank cell is the anti-default R1 exists to forbid.
- [ ] 3.5b Confirm neither page offers any control that records an outcome, approves a gate, decides an automated result or moves a launch date. A negative guarantee, tasked for the same reason 1.4 is: it is the property that makes this surface safe to open on a live launch, and nothing else in the build would notice its loss.

- [ ] 3.6 Order by attention band (at-risk, then awaiting-confirmation, then the rest), a launch in both appearing once in the first. Within a band: launch date ascending, undated last, ties by product identifier. Render revealed rows **set apart** from the bands, most recent first, undated last, ties by product identifier — never interleaved.
- [ ] 3.7 Implement narrowing by gate and by needs-attention, carried in query parameters as `playbook_admin.py` carries its own. A narrowing applies to revealed rows as it does to rows in play, each set narrowing within itself, and preserves the relative order the rows had unnarrowed. The reveal control is not itself a narrowing.
- [ ] 3.8 Implement all four empty states distinguishably: no launch position at all; a default view emptied by the filter; a narrowing that matched nothing, which governs when both apply and offers to clear itself; and revealing when nothing is out of play.
- [ ] 3.9 Give every rendered row a link to its detail page, working without scripting and independent of narrowing or row count.

## 4. The launch detail page

- [ ] 4.1 Add the detail route at `/admin/launches/{product_id}` on the same guard. Refuse — absence-shaped — when no launch position exists, when scope forbids it, and when the identifier names nothing. Refuse on the **launch position**, never on whether the catalog resolves the product.
- [ ] 4.2 Serve a launch whose product cannot be resolved, naming it by its raw identifier. This is the counterpart of 3.4 and the reason 4.1 keys on the position: the list offers every row in one action, so refusing here would put a dead end behind a row the list deliberately keeps.
- [ ] 4.3 Render the gate sequence from the report, marking the launch's current gate, and group steps by their gate in sequence order. Within a gate, render in the gate's authored order — `launch-playbook` obliges every consumer that lists a gate's steps to follow it, and 1.1/1.4 are what make it reachable. Do not sort by arrival.
- [ ] 4.4 Make the current gate's group the page's landing position.
- [ ] 4.5 Render each step's name, identifier, discipline, blocking flag, due period, recorded outcome with its provenance, and overdue mark — the last taken
  from the report, never derived on the page from the due period and the
  outcome. Deriving it is what the `launch-instance` overdue requirement
  exists to prevent: a `prohibited-tactic` step is resolved by `Refused`,
  so a page computing overdue itself would mark it overdue forever. Render a step with no recorded outcome distinguishably from one recorded not-started.
- [ ] 4.6 Pass the render date here too, per 3.3 — `read_launch` takes `as_of` as `read_launches` does.
- [ ] 4.7 State that a recorded outcome for a step the served playbook no longer holds is not rendered, and render the no-served-steps case as the gate sequence plus a statement, not as silently empty groups.
- [ ] 4.8 **Blocked on `add-launch-journal`.** Render the journal newest-first, each entry naming what occurred, when and what caused it, with an empty journal saying so. Before building it, confirm that change's read actually carries a cause — R5 requires it and nothing in `openspec/specs/` guarantees it yet.

## 5. The admin header, across three capabilities

- [ ] 5.1 Add the launch surface to `shared/infrastructure/driving/templates/_admin_header.html`. One partial, one edit; keep the outbound links un-boosted for the reason the partial already records.
- [ ] 5.2 Have both new pages carry the header and identify the launch surface as current, and take presentation from the shared admin stylesheet through the route no single surface owns — not through a route owned by another admin surface.
- [ ] 5.3 Add the header tests **where `playbook-admin` and `roster-admin` are tested**, not only under `launch-admin`. `design.md` — Decision 9 is explicit that a test derived from a single delta would not catch the asymmetry, which is the whole reason both were generalized.

## 6. Boundaries and sequencing

- [ ] 6.1 Confirm `.importlinter`'s `products-infrastructure-boundary` permits `launch.infrastructure → catalog.application` before writing the adapter. `design.md` marks this unverified. If it does not, add an exemption in the shape the contract already carries for the `access` edges — do not widen the contract further.
- [ ] 6.2 Do not archive this change before `add-launch-journal`. Archiving first folds R5 into `openspec/specs/` naming a capability with no spec, and `openspec validate` will not object.
- [ ] 6.3 Confirm `add-product-dossier-page` still carries no `roster-admin` or `playbook-admin` header delta before either change archives. A delta there written against the pre-generalization text would silently replace the generalized wording.

## 7. Verify against the specification

- [ ] 7.1 Run the tests derived from all four delta specs and confirm each scenario is observed. R5's two journal scenarios are observed once 4.8 unblocks — that is a sequencing note, not a licence to ship group 4 without them.
- [ ] 7.2 Confirm in particular the four `launch-instance` scenarios that pin existing behaviour — *A step entry states whether it blocks*, *An overdue non-blocking step is reported overdue*, *The report carries an entry for a step with no recorded outcome*, *Step entries arrive in the served playbook's order*. These fail only if 1.4's premise is wrong, which is exactly why they are written.
- [ ] 7.3 Exercise the restricted-scope and forbidden-launch scenarios with the **scope resolver alone** stubbed and the real enumeration behind it, asserting the rows rendered. Asserting only that the route passed the scope on establishes less than either scenario states.
- [ ] 7.4 Exercise the render-date scenario across two dates, so a defaulted date fails.
- [ ] 7.4a Exercise the row and detail shaping without rendering a template, so "data shaping separable from markup" (`design.md` — Goals) is demonstrated rather than asserted. No delta requires it, so nothing derived from the specs will notice if the read model collapses back into the templates.
- [ ] 7.5 Run `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the unit + agents tier; run the integration tier before pushing.

## 8. Confirm against the deployment

- [ ] 8.1 After merge and deploy, open `/admin/launches` from a fresh admin link and confirm the launches in play render with their gates, dates and attention marks, ordered by attention.
- [ ] 8.2 Open a launch from a row — by clicking, not by typing the URL — and confirm the detail page serves, grouped by gate, landing on the current one. Confirm the journal renders newest-first, and that a launch predating the journal shows the empty-journal statement rather than an absent section — the one part of this change integrating with another.
- [ ] 8.3 Confirm the reveal control shows launches no longer in play, marked and set apart, and that the header reaches the playbook and roster surfaces from both new pages and back.
- [ ] 8.4 Re-read `docs/deferred-work.md`'s *The admin stays server-rendered, in this repository*. Decision 2 closes the read-model half of that entry — "no read-model layer exists between the use cases and the templates" stops being true here. Correct or remove that paragraph; the file's own rule is that an entry which no longer holds is worse than no entry.
