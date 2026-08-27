## Why

Every accept and reject control on an automated result is broken in production, and has been since `introduce-automation-runtime` shipped. Pressing either button answers `That decision was refused: the roster does not know that Slack identity, so the decision was not recorded` — for **every** Slack identity, including active admins the roster plainly carries. No outcome is recorded and the result stays pending, so the automation runtime can produce results but nothing can ever be decided on them.

The cause is one seam, and it is the same seam `restore-admin-step-writes` closed one call site over. `main.py:140` injects `PostgresRoster` — a store exposing `load()` and `save()` — into `automation_confirmation.read_people`, and the decision handler passes that object straight to the accept/reject use cases as their `roster=` collaborator. `automated_decisions._person_for` probes three spellings (`person_for_slack_identity`, `list_people`, `people`), the store answers to none of them, and the function falls through to `return None`. The caller cannot distinguish "this collaborator cannot answer the question" from "the answer is nobody", so it reports the second.

That collapse is the defect worth naming separately from the mis-wiring. The two prior instances of this seam — `playbook_authoring._read_people` and the write path `_PageRosterReader` now adapts — both failed **loudly**, with a `TypeError` naming the object. This one fails into a well-formed business refusal that accuses the decider of not being on the roster. An operator reading it has no reason to suspect the wiring, and every reason to go looking at roster data that is entirely correct.

## What Changes

- The decision handler SHALL pass the accept/reject use cases a roster **reader**, adapted from the injected store through `access`'s public `list_people`, exactly as `worker.py` already adapts the same store for the ClickUp pass.
- A deployment where the collaborator was never injected at all SHALL answer the decider the same way, rather than failing without an answer behind an already-acknowledged button press.
- The roster collaborator those use cases take SHALL have **one** stated shape. A collaborator that cannot answer it SHALL be refused as a *wiring* defect: a named error identifying what was supplied and what was expected, raised before any decision is judged — never a refusal returned to the decider, and never attributable to the identity that pressed the button.
- A refusal the decider is shown SHALL only ever be a statement about the decision that was made. "The roster does not know that Slack identity" SHALL be reachable only when the roster was actually read and actually did not carry it.
- The seam SHALL be covered by a test that hands a real `RosterStore`-shaped collaborator to a decision — the one arrangement no existing test exercises, because `_FakeRoster` in `test_automated_result_decisions.py` deliberately answers to every spelling at once.
- One test SHALL observe the collaborator the composition root actually injects, rather than a rebuild of it. A double of the right shape cannot fail when the wiring regresses, which is exactly how this fault reached production past a test suite that covered every rule it breaks.

Non-goals, recorded so scope does not drift:

- No new read on `access`'s public surface. `list_people` already answers everyone the roster carries, deactivated included, which is exactly what the "known **and** active" rule needs to evaluate both halves itself. Adding a `person_for_slack_identity` port would move that judgement into `access` and is not proposed.
- `clickup_sync._roster_people` and `activation_readiness._people_of` keep their duck-typed reads. Both are fed a correctly shaped reader today and neither is the mis-wired one; unifying every roster read in `launch` behind one typed port remains a separate change, and both were recorded as non-goals by `restore-admin-step-writes` for the same reason. This change does not narrow that list.
- No change to *who* may decide, to what accepting or rejecting records, or to any other requirement of `launch-step-automation`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-step-automation`: the roster collaborator a decision is judged against gains a stated contract — one shape, a collaborator that cannot answer it refused by name as a mis-wiring rather than silently resolving to "no such person", and a guarantee that a refusal shown to a decider is never the product of an unreadable collaborator.

## Impact

- `src/commerce_ops/main.py` — line 140's injection. Unlike `restore-admin-step-writes`, the composition root **is** the place to fix this one: `automation_confirmation` has no second contract needing a store (its only use of the collaborator is this read), so it takes a reader and nothing else.
- `src/commerce_ops/launch/application/automated_decisions.py` — `_person_for`, and the `roster` parameter of `accept_automated_result` / `reject_automated_result`.
- `src/commerce_ops/launch/application/__init__.py` — `RosterReader` and `UnreadableRosterError` join the module's public surface, because an infrastructure adapter may reach application names only through it and this change puts both in one.
- `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py` — the `read_people` global and its docstring; `_roster_or_fail`, whose absence error changes type so that it too can be answered rather than escaping the Slack listener; and `_handle_decision`, which gains the catch that turns a wiring fault into a reply.
- Tests: `tests/unit/launch/application/test_automated_result_decisions.py` (the store-shaped collaborator, and `_FakeRoster`'s over-generosity) and `tests/unit/launch/infrastructure/driving/` for the adapter seam.
- No data migration, and no lost work. Every refused decision recorded nothing and settled nothing, so each pending result still stands and stays decidable. The Slack messages already posted carry `product_id` and `step_id` in their button values and are resolved fresh on each press, so they become functional as they are once this ships — no re-delivery is needed.
