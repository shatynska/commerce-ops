## 1. The two fields on a step definition

- [x] 1.1 Add `starts_at_gate: str | None = None` and `after_steps: tuple[str, ...] = ()` to `StepDefinition`, normalising `after_steps` to a tuple in `__post_init__` exactly as `assignees` is, so a caller handing a list still gets value semantics on a frozen dataclass
- [x] 1.2 Add `starts_at_gate` (nullable `String`) and `after_steps` (`JSONB`, non-null, `default=list`) to the `PlaybookStep` model, mirroring how `assignees` is carried
- [x] 1.3 Write the Alembic schema revision adding both columns; both defaults reproduce today's behaviour, so the revision is inert on its own
- [x] 1.4 Carry both fields through the playbook repository in each direction, and through `playbook_authoring`'s `StepRecord`, `_as_record`, `_copy_record` and `_write_fields`

## 2. Load-time coherence

- [x] 2.1 Reject a `starts_at_gate` naming no framework gate, with a fault naming the step and the value
- [x] 2.2 Reject a `starts_at_gate` whose position is later than the step's own `gate`, with a fault naming the step, its gate and its start gate
- [x] 2.3 Reject a `starts_at_gate` naming the final gate, for every step including those belonging to it — every consumer stands down there, so such a step is released into a state where nothing acts on it, and a blocking one makes graduation impossible
- [x] 2.4 Write the single `after_steps` graph traversal over `authored_steps`, reporting cycles (a self-reference included) and, for `blocking` steps, any transitively depended-on step whose start gate is later than the blocking step's own gate — one walk, two fault kinds
- [x] 2.5 Have the traversal follow an edge whatever the target's status and never stop at a non-`active` step — not a fault here, but not absent either, or a cycle would become loadable by retiring one step in it. The load rules are deliberately stricter than the release predicate on this point
- [x] 2.6 Wire all of the above into `_step_faults` so they are reported alongside every other fault of one load attempt, never one at a time

## 3. The release predicate

- [x] 3.1 Add the predicate to `Launch`, beside `unsatisfied_conditions`: released when `pos(current_gate) >= pos(starts_at_gate or first gate)` and every `active` step named in `after_steps` is resolved
- [x] 3.2 Judge a named step's resolution by its own hazard's permitted terminal outcomes, reusing the reading `_resolved` already applies rather than a second one — except for a `prohibited-tactic` step, which 3.3 excuses as policy — sequencing work behind a refusal is the wrong shape for a dependency — and not for want of a recordable outcome, since an automated one's handler can propose `Refused` terminally
- [x] 3.3 Treat a named step that is absent, not `active`, or classified `prohibited-tactic` as satisfied — the vacuous-satisfaction rule; without the third case a step re-authored `prohibited-tactic` freezes its dependents on every launch, silently
- [x] 3.4 Verify by inspection that the predicate takes no `date`, `datetime` or clock argument and performs no I/O — it reads the launch's gate, its recorded progress, and the definitions of the steps a dependency names, and nothing else

## 4. The two passes

- [x] 4.1 Have `converge_launch` skip a step the launch has not released, so no task and no mapping is created for it; leave the `graduated` early return as it is, being a separate fact
- [x] 4.2 Confirm `converge_launch` still leaves an existing task standing when its step stops being released — release governs creation, never withdrawal
- [x] 4.3 Have `_walk_launch` skip a step the launch has not released before the backoff read **and before the handler is resolved**, so an unreleased step costs no read, produces no stuck-step report, and is not reported for an unregistered handler every pass until its gate arrives
- [x] 4.4 Leave `reconcile_launch` ungated, and record the reason in a comment where a later reader would otherwise ask: completing work early is still work done
- [x] 4.5 Confirm `unsatisfied_conditions` and `advance_gate` are untouched by the predicate — a gate's conditions turn on recorded outcomes alone, and gating one on release would open a gate over work merely not asked for yet

## 5. Write-time validation and the admin form

- [x] 5.1 Add an `after_steps` precondition alongside `assignee_faults` and `_registration_faults`, refusing a reference to a step that is not `active`, that no step in the set carries, or that is classified `prohibited-tactic`, with one fault per offending identifier
- [x] 5.2 Evaluate the dependency precondition on every write whatever the caller supplies as a roster — it is a step-set rule and must not be skipped along the roster-guarded path
- [x] 5.3 Keep it scoped to the steps a write touches, as the other preconditions are; do not widen it into a set-wide check, and confirm retiring a depended-on step is therefore still accepted
- [x] 5.4 Add a `starts_at_gate` select to `_fields.html` offering the framework gates other than the final one, plus an explicit "starts immediately"
- [x] 5.5 Add an `after_steps` multiple-select offering the `active` steps only, grouped by gate with `optgroup`, each shown as `identifier — name`, excluding the step being edited — the write refuses every other kind, so offering them invites a refusal
- [x] 5.6 Attribute every new fault kind in `playbook_admin` **by the declaration it turns on**, never one fixed control per fault kind: an unknown start gate and a final-gate start gate mark the start-gate control; a start gate later than the step's own gate marks the gate control and the start-gate control both, being a combination fault; the three dependency refusals mark the dependency control; and a cycle or transitive deadlock marks every control on the edited step's form carrying a declaration it turns on — dependency, start gate, gate and blocking flag — so that an author who provoked a deadlock by ticking "blocks its gate" is not shown an unmarked form

## 6. The launch report

- [x] 6.1 Carry release on each step entry of the launch report, with the start gate where the launch has not reached it and the identifiers of the unresolved `after_steps` dependencies
- [x] 6.2 Exclude a step **whose start gate the launch has not reached** from the report's overdue judgement and from the at-risk evaluation — never a step held only by an unresolved dependency, which 6.4 confirms stays in both. The exclusion turns on the start gate alone, so the report, the daily briefing and the admin page cannot disagree about one step
- [x] 6.3 Confirm a blocking step at the gate the launch stands at still puts the date at risk — the exclusion must not hide a real delay
- [x] 6.4 Confirm a blocking step whose start gate the launch has reached but which waits on an unresolved dependency is still reported overdue and still puts the date at risk: the exclusion turns on the start gate alone, never on dependencies, or a stalled launch reports healthy

## 7. The detail page

- [x] 7.1 Render from the report, never derived on the page: `launch_admin` reads release, the start gate and the unresolved dependencies off the step entry
- [x] 7.2 Render a start mark on an unreleased step's table row in `launch.html`, alongside where "Blocks its gate" is rendered, worded from *starting* and never from *blocked*
- [x] 7.3 Confirm the overdue mark is absent for a step whose start gate the launch has not reached because the report says so, not because the page suppressed it — and that a step held only by a dependency renders both marks together
- [x] 7.4 Confirm the rendered page distinguishes unrecorded-and-released from unrecorded-and-unreleased, and add the mark's styling to the shared admin vocabulary rather than to this page

## 8. Backfilling the stored set

- [x] 8.1 Write the backfill Alembic revision, setting `starts_at_gate` to each stored step's own gate **whatever its status**, applied only where the column is null and keyed on step identifier, skipping a row it does not find
- [x] 8.2 Give the three `stock-ready` steps anchored at T-30 a start gate of `order`: `lp.inventory.019` (first-order sizing), `lp.inventory.008` (pre-shipment inspection), `lp.inventory.018` (barcode TOS) — `stock-ready` cannot be reached before T-7, and goods must be ordered before they can be stocked
- [x] 8.3 Give the three `live` steps anchored T-14 a start gate of `listable`: `lp.ppc.001` (naming convention), `lp.ppc.002` (keyword bucketing), `lp.ppc.004` (search-volume ceiling) — campaign preparation deliberately precedes going live, and `listable` is reachable by T-60, comfortably ahead of T-14
- [x] 8.4 Give `lp.ppc.003` (never-keywords list, T-60) a start gate of `order`, not `listable`: `listable` is itself reachable only by T-60, so releasing it there would leave the step zero margin against its own anchor, while `order` is reachable by T-90. Same cluster as 8.3, different gate, and the reason is the margin rather than the discipline
- [x] 8.5 Give every step belonging to the final gate a start gate of `ignition` — `graduated` is refused as a start gate, so the plain default would produce a set the loader rejects, and `lp.strategy.030` is blocking there, so leaving it at its own gate would also make graduation impossible. `ignition` rather than `phase-one-complete` because gate progression advances a launch as far as its state permits within one pass, so a single-gate window can be crossed between two runs of the passes that act on steps. Two gates is a margin rather than a guarantee: it takes two coincidences instead of one
- [x] 8.6 Apply the anchor exceptions to the seven identifiers named in 8.2, 8.3 and 8.4 and to no others — phrased over those identifiers rather than over status, since the same seven are `draft` in the vendored file and `active` in the stored set. Do **not** derive further exceptions for the remaining drafts: they take the mechanical default. The same measure finds 23 anchor-conflicting steps across the 352-step set, but the 16 that are drafts have never been reviewed against their anchors, and a too-late value on one fails silently — an unreleased step is passed over without a report and is not marked overdue. Record them as an authoring task for whoever activates each step, not as a migration's judgement
- [x] 8.7 Re-derive the active exception set against the live `playbook_steps` table before running the backfill rather than trusting either vendored YAML, and reconcile any step authored since; `alembic/data/playbook_reference.yaml` is the live vendored set, `alembic/data/playbook_v1.yaml` is read only by migration `d2f8b3c64e17` and describes the set as it was in August 2026
- [x] 8.8 Confirm a `draft` step carries a start gate after the backfill, so that activating it later does not make it eligible in every launch at once
- [x] 8.9 Verify the downgrade returns every `starts_at_gate` to null, which is "starts immediately", so a rollback cannot strand a launch

## 9. The vendored set delivers the field too

- [x] 9.1 Add `starts_at_gate` to every step in `alembic/data/playbook_reference.yaml`, on the same rule the backfill uses — the step's own gate, `ignition` for final-gate steps, and the earlier gate the anchor implies for the seven identifiers named in 8.2, 8.3 and 8.4
- [x] 9.2 Read `starts_at_gate` in `seed_playbook.vendored_definitions` and fail on a vendored step that does not carry one, rather than letting the dataclass default apply; a shape fault here is a fault in a file this repository ships and is reported as one
- [x] 9.3 Leave `after_steps` absent from the vendored file, omission being the empty set — the asymmetry with `starts_at_gate` is recorded in `design.md` and wants no per-step value
- [x] 9.4 Regenerate rather than hand-edit if `alembic/data/generate_playbook_reference.py` is what produces the file, and carry the new field through the generator
- [x] 9.5 Add a unit-tier test over the vendored file asserting every step states a start gate, so a generator or hand-edit slip fails at commit time rather than as an unhealthy container after merge
- [x] 9.6 Confirm the ordering holds: migrations run before `seed_playbook` in the container start chain, so the backfill covers what exists and the vendored file covers what is added afterwards, with no row falling between them

## 10. The two scenarios the test pass predates

- [ ] 10.1 `launch-playbook`'s MODIFIED *Gate sequence orders the launch* was added after `openspec-test-writer` ran, so its two new scenarios — *A dependency does not change when a gate opens* and *A dependency does not move a step's obligations* — are absent from `test-manifest.md`. Have them written from the delta by someone other than whoever implements the predicate, as every other scenario here was, rather than folded in by the implementer

## 11. Verification

- [x] 11.1 Run `uv run pytest` over `tests/unit` and `tests/agents`
- [ ] 11.2 Run `uv run pytest tests/integration`, the migration revisions being the point of this one
- [x] 11.3 Run `ruff check`, `ruff format --check` and `mypy`
- [x] 11.4 Run `import-linter` and confirm no new contract violation — the predicate is domain code and must not have reached for a repository
- [x] 11.5 Apply both revisions against a scratch database and confirm a launch at `commit` projects only its released steps, then advances and projects the rest

## 12. Documentation

- [ ] 12.1 Remove `docs/deferred-work.md`'s "A step cannot say when it may start, so gate-8 work runs during gate 1" entry as part of the archive commit
- [ ] 12.2 Record in `docs/deferred-work.md` the ClickUp dependency projection this change deliberately left out, with what was established about it: `POST /api/v2/task/{id}/dependency`, the existing list read already returning each task's `dependencies`, and ClickUp's dependencies warning on early completion rather than preventing it
- [ ] 12.3 Record in `docs/deferred-work.md` that `alembic/data/playbook_v1.yaml` reads as the current step set and is not one — it is read only by migration `d2f8b3c64e17`, whose docstring records why the copy is vendored, so it cannot be deleted and wants a header saying what it is; `alembic/data/playbook_reference.yaml` is the live vendored set
