## Why

`thread-launch-slack-notifications` (archived 2026-08-31) moved every per-launch Slack message into a per-launch thread and gave each message a tag naming whoever is meant to act on it. Four defects shipped with it. What groups them is not one fault but one blind spot: every one of them is invisible to that change's own test suite, and each is silent in production — nobody is notified, nothing is posted, or nothing is said, and in no case does anything fail loudly enough to be noticed. Three are a value carried across a boundary in the wrong form, where the tests assert on the *presence* of a value rather than on what the value has to be, so each test supplies the form the code wants and never the form the real caller sends; the fourth is an error path that was removed rather than relocated. Fixing them one at a time would mean four passes over the same four files and the same four tests.

The fourth was found while designing the fix for the first, and it changes what the first one means: the pending-result ask is not merely mis-tagged, it is never posted at all. Its mention defect is real but currently unreachable, and stays that way until delivery works.

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

So both would render `<@3f7c1a92-…>`, which Slack leaves as inert literal text. Nobody is notified, on precisely the two message kinds whose entire purpose is to notify a named person: the decision a step's confirmer alone may make, and the report telling someone a step has stopped moving. The stuck-step report renders it today; the pending-result ask does not get that far, for the reason defect 4 gives.

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

### 4. No pending result is ever delivered

`deliver_pending_result` (`automation_confirmation.py:151-155`) opens by demanding a value object:

```python
product_id = getattr(result, "product_id", None)
if not isinstance(product_id, ProductId):
    raise TypeError(f"product_id must be ProductId, got {type(product_id)}")
```

Its only caller hands it something else. `_deliver_waiting` (`automation_pass.py:325-339`) iterates `await results.undelivered()`, which returns ORM rows (`automated_results.py:136-145`), and passes each row straight through as `result=row`. `AutomatedStepResult.product_id` is `Mapped[uuid.UUID]` (`models.py:509-517`). The check therefore fails on every row, on every pass:

```
$ uv run python - # a real AutomatedStepResult row through deliver_pending_result
row.product_id type: <class 'uuid.UUID'>
RAISED TypeError: product_id must be ProductId, got <class 'uuid.UUID'>
```

`_deliver_waiting` catches it with the same `except Exception` that exists for a Slack outage, logs *"could not deliver the pending result … it still stands and will be delivered again"*, and leaves `delivered_at` unstamped. So the row is retried on the next pass, and the next, forever. `launch-step-automation`'s *"The system SHALL deliver each pending result to Slack"* is met by nothing: a step needing confirmation is proposed, held, and never asked about. The retry machinery built for a transient failure is what hides a permanent one.

The two lines that read the identifier disagree about its form within the same function, which is what makes this the same fault as the three above rather than an unrelated bug. `deliver_pending_result` demands a `ProductId`; `_decision_value` (`automation_confirmation.py:194`), composing the accept/reject button payload from the *same* object, writes `str(getattr(result, "product_id", ""))` — correct for the `uuid.UUID` a real row carries, and defect 2 all over again for the `ProductId` the function above it insists on. Exactly one of the two can be right about any given caller, and the test stub (`test_automation_confirmation_to_thread_reply.py:128`, `product_id: ProductId = PRODUCT_ID`) supplies the form that satisfies the check and quietly corrupts the button.

`_deliver_waiting` already holds the converted value — it builds `ProductId(str(row.product_id))` one line earlier to read the catalog — so nothing is missing but the decision about which side of the seam owns the conversion.

## What Changes

- **Mention resolution goes through the roster.** `resolve_mention_target` resolves a step's `confirmer` from the roster identifier it holds to that person's Slack identity, and returns something every caller may interpolate into `<@…>` without further translation. A confirmer counts as resolvable only where the roster carries them, with a Slack identity, and **still active** — the active condition being the one that occurs *durably*, since `roster` preserves a deactivated person's Slack identity while `launch-step-automation`:225 accepts a decision only from an active confirmer. The roster not carrying the confirmer at all is reachable too, by one sanctioned route; carrying them without a Slack identity is forbidden outright. `design.md` ranks all three, because they are not equally reachable and the code should say so. `launch` may not construct `access`'s store, so the reader arrives injected from the composition roots, by the same route `read_people` already takes in `automation_confirmation.py` and `gate_confirmation.py`.
- **The two message kinds degrade differently, because only one of them is governed by an authorization rule.** Where the confirmer cannot be resolved, the pending-result ask is delivered **untagged**: only that confirmer may decide it, so tagging anyone else summons a person whose accept and reject are certain to be refused. The stuck-step report is delivered tagging the **submitter**, with its text naming that the confirmer could not be resolved: nothing governs who may act on a stuck step, its stated purpose is that *a person* can supply what the handler is missing, and an untagged report reaching nobody defeats it. Either way the gap is **reported**, never silently dropped, matching the trade `_clickup_users` already makes for an assignee with no ClickUp account — and either way "the step names no confirmer" stays distinguishable from "the step's confirmer cannot be reached".
- **The mention's contract is stated where it can be checked.** `resolve_mention_target` returns a Slack identity or nothing — never an identifier from another namespace — and the tests assert that property rather than that some constant appears in the text.
- **The pending-result delivery seam agrees with itself.** `_deliver_waiting` already converts the stored row's identifier for its catalog read; it passes that `ProductId` on as an explicit argument, and `deliver_pending_result` takes it as a typed parameter instead of digging one out of the row and rejecting what it finds. `_decision_value` composes the button payload from that same parameter, so the identifier the controls carry is the one the result was stored against and a decision on them resolves it. One form, named once, at the seam that owns the conversion.
- **The two `str(product_id)` sites are corrected** to read `.value`, matching `gate_confirmation.py`'s correct line.
- **The prohibition on rendering a value object is lifted out of `subcategory-advisor` and stated once, for every module,** in `shared-vocabulary`, in two halves: a value object carrying a single value *renders as* that value, and no message, prompt, log line or persisted record composes one by rendering the object. The first half is what makes the second checkable rather than merely forbidden — the mistake has now been made four times in three modules, each time silently, and a rule that can only be obeyed by remembering it will be broken a fifth. `shared-vocabulary` is the capability that owns what these objects are, so it is where the textual form belongs.
- **The launch confirmation regains a delivery of last resort.** Where the threaded confirmation cannot be delivered, the submitter is told directly that the launch started, by the same path `_failure_text` already uses. The thread reply stays the specified delivery; this is what happens when it fails, not an alternative to it.
- Explicitly **not** in scope: the anchor's own composition and the fact that four call sites each assemble it from whatever product they happen to hold — that is `inject-the-thread-anchor-poster`'s subject, and it will retire the two `str(product_id)` fallbacks corrected here by removing caller-supplied composition altogether. Fixing them now is deliberate duplication of effort: the defect is live, and the two changes are independently mergeable in either order.
- Explicitly **not** in scope: `resolve_mention_target`'s `step`/no-`step` rule where the confirmer resolves (a step's confirmer if it names one, the launch's submitter otherwise), which is correct and unchanged — what each caller does when it does *not* resolve is new, and is specified per path; the gate-ask path, which is already correct and which keeps needing no edit because the function's return type does not change; and which messages are threaded at all.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-step-automation`: the requirements that a pending result and a stuck-step report tag the step's named confirmer (lines 199, 206, 522, 539-544) are made precise about what "tags" means — the message carries a mention that identifies that person **to Slack**, resolved from the roster, rather than carrying the step's stored reference to them — and state what happens when the roster cannot resolve them. Today's wording is satisfied by a mention nobody receives, which is why the shipped implementation passes its own tests. The delivery requirement additionally gains the round-trip that defect 4 breaks: a delivered ask's controls name the launch and step the result was stored against, which is a property no test asserts today and which the current stub-supplied form silently inverts.
- `launch-entry`: the requirement that a started launch's outcome is confirmed (line 10) gains what happens when the threaded delivery fails — the submitter is told directly rather than not at all. The specified delivery is unchanged.
- `shared-vocabulary`: gains a requirement that a value object carrying a single value renders as that value, and that no human-readable or machine-consumed text is composed from a rendering of the object. This generalises a rule `subcategory-advisor` already states for one handler; that capability's own wording is left in place, since it also carries the handler-specific reasoning about a silent prompt fault.

## Impact

- `src/commerce_ops/launch/application/thread_establishment.py` — `resolve_mention_target` gains a roster reader and the identity translation; its docstring's claim becomes true.
- `src/commerce_ops/launch/infrastructure/driven/launch_thread_delivery.py` — `establish_thread_and_resolve_mention` supplies the roster reader to `resolve_mention_target`, being the infrastructure half that is allowed to.
- `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py` — `deliver_pending_result` takes `product_id: ProductId` as a parameter and drops the `isinstance` rejection; `_decision_value` and `compose_blocks` take it too; `automation_pass.py:333` passes the `ProductId` it already builds.
- `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py:166`, `automation_pass.py:595` — `str(...)` → `.value`.
- `src/commerce_ops/shared/domain/identity.py`, `discipline.py`, `severity.py` — the seven single-valued vocabulary values gain the textual form the new `shared-vocabulary` requirement states. Lifecycle stages and the access scope are excluded, having no single value to render as; the prohibition half still binds them.
- `src/commerce_ops/launch/application/use_cases.py:342` — the one site the audit found that wants the debugging form, switched to `{product_id!r}` so it keeps saying what it meant.
- Message composition on the two affected paths: `deliver_pending_result` drops its tag where the confirmer does not resolve, and `_stuck_step_message` gains a line naming an unresolved confirmer. `resolve_mention_target` gains only the injected reader, and the return type it shares with `establish_thread_and_resolve_mention` is unchanged — that, and the helper's unchanged surface, is what keeps the other two call sites out of the diff.
- `src/commerce_ops/launch/infrastructure/driving/slack_entry.py:564-582` — the fallback confirmation.
- `src/commerce_ops/main.py`, `src/commerce_ops/worker.py` — the roster reader reaches `launch_thread_delivery`; both roots already construct one (`_RosterReader`), so this is a wiring line each, not a new collaborator. It is one more global assignment in a pattern `unify-launch-adapter-dependencies` proposes to retire; that sequencing is deliberate and noted there.
- `src/commerce_ops/launch/infrastructure/driving/gate_confirmation.py` — unchanged, and unchanged in the literal sense rather than the "adapts mechanically" one: it passes `step=None`, already reads `product_id.value`, and the shared helper's return type is deliberately left alone so that neither it nor `slack_entry.py`'s mention use needs an edit. Included here only so a reader can see it was checked.
- Tests: `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py` and `test_stuck_step_report_to_thread_reply.py` currently pass a `CONFIRMER_ID` constant through and assert it appears — they must instead establish that a roster identifier does *not* reach the message and that the person's Slack identity does. `tests/unit/launch/application/test_thread_establishment_race.py:282-300` holds the direct tests of `resolve_mention_target` and gains the namespace cases. Defect 4 needs coverage no unit stub can give — the whole point is that the stub carries a form the store does not — so it is pinned in the integration tier, against a real stored row read back through `undelivered()`.
- No migration, no new runtime variable, no schema change — audited rather than assumed: the sweep over every `str()` call, f-string, `%s` interpolation and admin-page template site for the seven affected types found four sites needing attention, none of them a persisted record or a parsed payload, and eleven template sites that already receive unwrapped values (`design.md`). `step.confirmer`'s stored form is unchanged — this is about how it is read, not what it holds.
- One-time effect at deploy: fixing defect 4 releases every pending result that has accumulated undelivered since 2026-08-31, roughly a day's worth. Deliberately delivered rather than suppressed — a result nobody has ever been asked about is exactly what *"An undelivered result is delivered again later"* exists for — with the count established before deploy rather than discovered in the channel.
