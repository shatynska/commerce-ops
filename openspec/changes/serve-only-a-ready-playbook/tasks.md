## 1. Domain: split readiness out of coherence

- [ ] 1.1 Remove `_gate_holding_faults` from `LaunchPlaybook.__post_init__`'s fault list, keeping the other three sources unchanged, so a set leaving a gate unheld loads
- [ ] 1.2 Expose the unheld gates as a derived read on `LaunchPlaybook` — the gates with no `active` blocking step, in gate-sequence order — plus a readiness predicate over it, computed on every read and never stored
- [ ] 1.3 Add `PlaybookNotReadyError`, carrying the unheld gate identifiers **and the playbook it was constructed from**, as its own type and **not** a subclass of `InvalidPlaybookError`, so a consumer can tell an unfinished playbook from a broken one — and can still ask what the set contains while declining to act on it
- [ ] 1.4 Add the one-directional gate-holding check as a domain-level predicate over a *prior* set and a *candidate* set, so the ratchet is a domain rule rather than something the application layer improvises

## 2. Application: the ratchet on the write path

- [ ] 2.1 Have `_accept` evaluate the ratchet — refuse a write that leaves a gate unheld only when the set it loaded was itself ready — and gather its fault alongside the existing ones so a rejection still reports everything at once. **Keep the fault's existing wording**: `playbook_admin._CROSSINGS` (`playbook_admin.py:593`) matches the substring `has no active blocking step attached`, and the fault-attribution sweep asserts the rule is recognised at page level rather than falling through unmatched
- [ ] 2.2 Leave `reorder_step` on its direct `_validate` call and record why in a comment: a reorder changes only `display_order`, so it can never move a ready set to not-ready, and routing it through `_accept` would newly subject the moved step to `_precondition_faults` — refusing reorders of migrated unowned `active` `human` steps, which `playbook-authoring`'s reorder requirement does not contemplate
- [ ] 2.3 Confirm every other write path (create, update, status change, retire, un-retire) reaches `_accept`

## 3. Infrastructure: enforce readiness at the serving read

- [ ] 3.1 Make `PlaybookRepository.get()` raise `PlaybookNotReadyError` when the constructed playbook is not ready; leave `load()` untouched
- [ ] 3.2 Confirm the absent-playbook failure (`_version()` raising when no `playbook_step_set` row exists) is unchanged and is not reported as not-ready

## 4. Consumers

- [ ] 4.1 `slack_entry` — refuse a launch start against a not-ready playbook, reporting to the submitting user with the unheld gates named, persisting neither product nor launch
- [ ] 4.2 `clickup_sync_job` — stand the projection/reconciliation pass down, log the stand-down and the unheld gates, and let the run record as succeeded
- [ ] 4.3 `clickup_webhook` — **move only the readiness check ahead of `mapping.observe(...)`** (today the observation at `clickup_webhook.py:181` commits before the playbook read at `:183`), then acknowledge and record nothing. Whether the retained observed state is left alone depends on the step: leave it untouched where the playbook **serves** the step (so reconciliation can recover the completion), and advance it exactly as today where it does **not** (so the closure is consumed and never replayed). The served set comes from the playbook the refusal carries — take no second read. The membership check that follows the playbook read must **stay after** the observation, so that a delivery for a step outside the launch's obligations is still observed and never replayed later. Note what that check actually tests: `clickup_webhook.py:184` matches against `playbook.steps`, which is the **authored** set (`authored_steps` is `steps` verbatim), so a retired step passes it and is then refused downstream by `_defined_step`, which iterates `served_steps` (`launch_run.py:574`). Do not change that check's set as part of this task — the mismatch predates this change, and narrowing it to `served_steps` would alter an externally observable response on a path this change does not otherwise touch
- [ ] 4.4 Add a briefing-owned condition type on `briefing.application` — a sibling of `BriefingError` in `briefing.domain.attention` — carrying opaque identifier strings, meaning "the launch source cannot supply reports". Document it on `briefing/application/ports.py` beside `LaunchReports`, since it is part of what satisfying that port now means
- [ ] 4.5 `worker` — translate `PlaybookNotReadyError` from its launch-reports reader into that briefing-owned condition, carrying the unheld gate identifiers. `worker.py` is outside every `.importlinter` container, which is what lets it name both sides
- [ ] 4.6 `daily_briefing_job` — handle the briefing-owned condition **ahead of** the generic assembly-failure branch: post one message naming the carried identifiers through the existing `_attempt_post` (so a delivery failure is logged and does not fail the run), record the run as succeeded, assemble nothing, and do not take the failed-run path
- [ ] 4.7 `check_step_handlers` — read the authored set through `load()` + `authored_definitions` instead of `get()`, so `report_unregistered_handlers` still runs and still reports at startup when the playbook is not ready. Update its module docstring, which currently claims the startup read exercises load-time coherence checking
- [ ] 4.8 Confirm `playbook_admin` needs no change, reading through `load()`, and that a gate with zero active steps renders without error now that it is reachable

## 5. Tests

- [ ] 5.0 Re-point the existing tests whose subject is the floor as a *construction* rule — `tests/unit/launch/domain/test_gate_holding_floor.py` in full, and the gate-holding cases in `test_playbook_coherence_by_status.py` — so they assert construction succeeding and the refusal landing at the serving read (5.6). Task 1.1 inverts what they currently assert, so 6.1 runs red until this is done
- [ ] 5.1 Domain: an all-`draft` set loads; a set leaving one gate unheld loads; every other coherence rule still rejects
- [ ] 5.2 Domain: the unheld-gate read names exactly the gates with no active blocking step, and is empty for a ready set
- [ ] 5.3 Domain: `PlaybookNotReadyError` is distinguishable from `InvalidPlaybookError`
- [ ] 5.4 Application: the first activation against an all-draft set lands; a retire or un-activation of a gate's last blocking step is refused in a ready set and accepted in one that is not
- [ ] 5.5 Application: a reorder of an unowned `active` `human` step still lands, so the exemption recorded in 2.2 does not regress
- [ ] 5.6 Infrastructure: `get()` refuses a not-ready set naming the gates; `load()` returns it; an absent step set still reports absence
- [ ] 5.7 `clickup_webhook`: a verified delivery during a stand-down for a **served** step leaves `last_observed_closed` unchanged — asserted on the stored row, not only on the response
- [ ] 5.8 `clickup_webhook`: the same delivery for a step the playbook does **not** serve advances `last_observed_closed` while recording nothing, so *A closure during retirement is never replayed* holds through a stand-down
- [ ] 5.9 End-to-end over the sequence the "not lost" scenario names: task closed while not ready → delivery acknowledged, nothing recorded, retained state unchanged → playbook made ready → reconciliation records the completion
- [ ] 5.10 `briefing`: a launch source reporting it cannot supply reports posts a message naming the carried identifiers, on each of two consecutive runs, with the run succeeded and no assembly-failure message — written against the briefing-owned condition, so the test needs no launch import either
- [ ] 5.11 `clickup_webhook`: a delivery whose step is absent from the authored set still advances `last_observed_closed` while recording nothing — a guard on the *ordering* of the membership check relative to the observation, so moving the readiness check does not drag the membership check above it. Use a step the playbook does not carry at all; a retired one takes the downstream `_defined_step` path instead and is out of scope here
- [ ] 5.12 `check_step_handlers`: an `active` `automated` step whose handler is unregistered is still reported at startup while the playbook is not ready
- [ ] 5.13 `worker`: `_read_launch_reports` raises the briefing-owned condition, carrying the unheld gate identifiers, when its playbook read refuses. This translation is the only thing standing between a `launch.domain` exception and the `briefing` requirement — untested, a failure here reaches `daily_briefing`'s generic handler and produces a failed run plus the assembly-failure message, which three scenarios of the `briefing` delta forbid, with nothing in the suite going red
- [ ] 5.14 One test each for `slack_entry` and `clickup_sync_job` covering its decline path

## 6. Verification

- [ ] 6.1 `uv run pytest tests/unit tests/agents`
- [ ] 6.2 `uv run pytest tests/integration` against an isolated database (create `commerce_ops_test`, name it in `.env.test`) so the run does not write into `commerce_ops`
- [ ] 6.3 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`
- [ ] 6.4 `uv run lint-imports` — `worker.py` (4.5) and `check_step_handlers` (4.7) sit outside every container and may name both sides. The contracts that must still pass are `briefing-application-boundary` and `briefing-infrastructure-boundary`, which forbid `launch.domain` and `launch.infrastructure` only. That `briefing` names nothing from `launch` **at all** is briefing's own convention, not something the linter encodes — it is checked by review
- [ ] 6.5 Confirm against a local database that the current active set is ready and every consumer behaves exactly as before — the change is unobservable until a not-ready set exists
