## Why

`thread-launch-slack-notifications` (archived 2026-08-31) moved every per-launch Slack message into a per-launch thread and gave each message a tag naming whoever is meant to act on it. Three defects shipped with it. All three are invisible to the test suite, which is why they are grouped here: each one is a case of a value being carried across a boundary in the wrong form, and the tests derived from the delta specs assert on the *presence* of a value rather than on what the value has to be.

### 1. A tagged confirmer is tagged with an identifier Slack cannot resolve

`resolve_mention_target` (`launch/application/thread_establishment.py:100-102`) returns two values from two different identity namespaces through one return type:

```python
if step is not None and step.confirmer:
    return step.confirmer      # a roster identifier
return launch.submitter        # a Slack identity
```

Its own docstring states the contract the callers rely on — *"The returned value is a Slack identity (user ID) that can be used in `<@identity>` mention syntax"* — and only the second branch honours it.

`launch.submitter` is genuinely a Slack identity: `slack_entry.py` records `body["user"]["id"]` at launch start. `step.confirmer` is not. It references a roster person **by the roster's own generated identifier** — `launch_playbook.py:337-342` says so, and `access/application/roster.py:169-172` generates it as `str(uuid.uuid4())`. `Person` carries `slack_identity` as a separate field entirely (`access/domain/principals.py:55-57`), and `automated_decisions.py:194` settles the question by comparing `step.confirmer` against `person_identifier(person)` — never against `slack_identity`.

Both callers that pass a step interpolate the result directly:

- `automation_confirmation.py:171` — `mention_tag = f" <@{mention}> "` on the pending-result ask
- `automation_pass.py:601` — the same on the stuck-step report

So both render `<@3f7c1a92-…>`, which Slack leaves as inert literal text. Nobody is notified, on precisely the two message kinds whose entire purpose is to notify a named person: the decision a step's confirmer alone may make, and the report telling someone a step has stopped moving.

The gate ask is **not** affected. `gate_confirmation.py:256` passes `step=None` deliberately — a gate carries no confirmer of its own (`launch-gate-progression`:113) — so it takes the submitter branch, which is correct.

The roster→service-identity translation this needs already exists one module over: `clickup_sync._clickup_users` resolves a step's assignees from roster identifiers to `clickup_user_id` through an injected roster reader, reporting rather than silently dropping a person the roster cannot resolve. The thread-mention path simply never acquired the equivalent.

### 2. A value object is rendered by its `repr` into a message that is never re-posted

`automation_confirmation.py:166` and `automation_pass.py:595` both compose the anchor's product name as:

```python
product.name if product else str(launch.product_id)
```

`ProductId` is a `@dataclass(frozen=True, slots=True)` (`shared/domain/identity.py:26-34`), so `str()` on it yields `ProductId(value='…')`. `gate_confirmation.py:253` writes the same fallback correctly, as `product_id.value`.

This is worse than an ordinary cosmetic slip because of where the value lands. `launch-instance`:513 requires the thread reference to be established once and **never re-created** — *"a later delivery for the same launch SHALL reuse the existing reference rather than posting a second anchor message"*. So a launch whose first-ever per-product message happens to be a pending-result ask or a stuck-step report, at a moment when the catalog read returned nothing, gets `ProductId(value='…')` as the permanent human-readable heading of its thread. Nothing later corrects it.

The system has already ruled on this class of fault. `subcategory-advisor` carries the requirement *"The marketplace the advisor is given SHALL be the identifier itself, as the catalog holds it and as a reader of the prompt would recognise it — never a rendering of the object carrying it,"* and extends it: *"The same SHALL hold of every other value the advisor passes on from the product it was given."* That requirement exists because the identical mistake was made once already, on `MarketplaceId`. It is scoped to one capability, so it did nothing to prevent these two.

### 3. A launch can be started and confirmed to nobody

Before this change, `slack_entry.py` confirmed a started launch unconditionally, straight to the submitter:

```python
await _post(client, submitter, _confirmation_text(submission))
```

Today (`slack_entry.py:564-582`) the confirmation is posted **only** as a thread reply, inside a `try` whose `except Exception` logs and continues, with the reasoning *"thread establishment failure means thread wasn't needed."* That does not follow: the thread was needed precisely in order to say the launch started. A DB blip, a Slack 5xx, or an absent `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` now leaves the product registered, the launch persisted, and the submitting user told nothing whatsoever.

`launch-entry`:10 requires that the system *"SHALL confirm the outcome"*. Relocating that confirmation into the thread is what the requirement now says and is not in question here; losing it silently is. Note the asymmetry this creates: the *failure* path (`_failure_text`) still reaches the submitter directly and always, so a launch that fails is reported and a launch that succeeds may not be.

## What Changes

- **Mention resolution goes through the roster.** `resolve_mention_target` resolves a step's `confirmer` from the roster identifier it holds to that person's Slack identity, and returns something every caller may interpolate into `<@…>` without further translation. Where the roster does not carry the named confirmer, or carries them without a Slack identity, the message is still delivered — untagged or falling back to the submitter, to be settled in `design.md` — and the gap is **reported**, never silently dropped, matching the trade `_clickup_users` already makes for an assignee with no ClickUp account. `launch` may not construct `access`'s store, so the reader arrives injected from the composition roots, by the same route `read_people` already takes in `automation_confirmation.py` and `gate_confirmation.py`.
- **The mention's contract is stated where it can be checked.** `resolve_mention_target` returns a Slack identity or nothing — never an identifier from another namespace — and the tests assert that property rather than that some constant appears in the text.
- **The two `str(product_id)` sites are corrected** to read `.value`, matching `gate_confirmation.py`'s correct line.
- **The prohibition on rendering a value object is lifted out of `subcategory-advisor` and stated once, for every module,** in `shared-vocabulary`: a value object's textual form is its value, and no message, prompt, log line or persisted record composes it by rendering the object. Stated as a general requirement because the mistake has now been made three times in three modules, each time silently, and because `shared-vocabulary` is the capability that owns what these objects are.
- **The launch confirmation regains a delivery of last resort.** Where the threaded confirmation cannot be delivered, the submitter is told directly that the launch started, by the same path `_failure_text` already uses. The thread reply stays the specified delivery; this is what happens when it fails, not an alternative to it.
- Explicitly **not** in scope: the anchor's own composition and the fact that four call sites each assemble it from whatever product they happen to hold — that is `inject-the-thread-anchor-poster`'s subject, and it will retire the two `str(product_id)` fallbacks corrected here by removing caller-supplied composition altogether. Fixing them now is deliberate duplication of effort: the defect is live, and the two changes are independently mergeable in either order.
- Explicitly **not** in scope: `resolve_mention_target`'s `step`/no-`step` rule itself (a step's confirmer where it names one, the launch's submitter otherwise), which is correct and unchanged; the gate-ask path, which is already correct; and which messages are threaded at all.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-step-automation`: the requirements that a pending result and a stuck-step report tag the step's named confirmer (lines 199, 206, 522, 539-544) are made precise about what "tags" means — the message carries a mention that identifies that person **to Slack**, resolved from the roster, rather than carrying the step's stored reference to them. Today's wording is satisfied by a mention nobody receives, which is why the shipped implementation passes its own tests.
- `launch-entry`: the requirement that a started launch's outcome is confirmed (line 10) gains what happens when the threaded delivery fails — the submitter is told directly rather than not at all. The specified delivery is unchanged.
- `shared-vocabulary`: gains a requirement that a value object is carried into any human-readable or machine-consumed text by its value and never by a rendering of the object. This generalises a rule `subcategory-advisor` already states for one handler; that capability's own wording is left in place, since it also carries the handler-specific reasoning about a silent prompt fault.

## Impact

- `src/commerce_ops/launch/application/thread_establishment.py` — `resolve_mention_target` gains a roster reader and the identity translation; its docstring's claim becomes true.
- `src/commerce_ops/launch/infrastructure/driven/launch_thread_delivery.py` — `establish_thread_and_resolve_mention` supplies the roster reader to `resolve_mention_target`, being the infrastructure half that is allowed to.
- `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py:166`, `automation_pass.py:595` — `str(...)` → `.value`.
- `src/commerce_ops/launch/infrastructure/driving/slack_entry.py:564-582` — the fallback confirmation.
- `src/commerce_ops/main.py`, `src/commerce_ops/worker.py` — the roster reader reaches `launch_thread_delivery`; both roots already construct one (`_RosterReader`), so this is a wiring line each, not a new collaborator. It is one more global assignment in a pattern `unify-launch-adapter-dependencies` proposes to retire; that sequencing is deliberate and noted there.
- `src/commerce_ops/launch/infrastructure/driving/gate_confirmation.py` — unchanged. It passes `step=None`, already reads `product_id.value`, and is included here only so a reader can see it was checked.
- Tests: `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py` and `test_stuck_step_report_to_thread_reply.py` currently pass a `CONFIRMER_ID` constant through and assert it appears — they must instead establish that a roster identifier does *not* reach the message and that the person's Slack identity does. `tests/unit/launch/application/test_thread_establishment_race.py:282-300` holds the direct tests of `resolve_mention_target` and gains the namespace cases.
- No migration, no new runtime variable, no schema change. `step.confirmer`'s stored form is unchanged — this is about how it is read, not what it holds.
