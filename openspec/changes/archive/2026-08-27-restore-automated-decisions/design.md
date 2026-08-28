## Context

See `proposal.md` — *Why* for the fault and its symptom. What matters here is the arrangement that produced it, because the same arrangement is present at five call sites and only two of them are safe.

`launch` may not import `access`'s **store**. `.importlinter`'s `products-application-boundary` and `products-infrastructure-boundary` forbid `access.domain` and `access.infrastructure`, and permit `access.application` — which `playbook_admin.py:53` already imports `list_people` and `RosterStore` from. So `launch` can *read* the roster through `access`'s public surface; what it cannot do is construct the store that surface reads from. Every roster collaborator in `launch` is therefore injected by a composition root, and five sites do this today:

| Site | Injected by | What is injected | Static protection |
|---|---|---|---|
| `clickup_sync_job.read_people` | `worker.py:119` | `_RosterReader()` adapter | none — its `RosterReader` is `Any` (`clickup_sync.py:115`) |
| `playbook_admin.roster` | `main.py:132` | `PostgresRoster` store, adapted internally by `_PageRosterReader` | **typed as the store it is** (`playbook_admin.py:271`), so handing it to a reader parameter does not type-check |
| `playbook_authoring`'s `roster=` parameter | its callers | a reader | **a real `Protocol`**, plus a named refusal |
| `activation_readiness`'s `roster=` parameter | its callers | a reader | none — `roster: Any = None`, read by a duck-typed `_people_of` |
| `automation_confirmation.read_people` | `main.py:140` | **`PostgresRoster` store, unadapted** | none — the global is `Any` |

Two names spelled `RosterReader` exist in `launch` and mean different things: `launch.application.playbook_authoring.RosterReader` is a one-member `Protocol`, and `launch.infrastructure.driven.clickup_sync.RosterReader` is `RosterReader = Any` (clickup_sync.py:115). Reading the second as though it were the first is why `clickup_sync_job.py:98` can declare `read_people: RosterReader = None` and pass `mypy --strict`. The alias is not this change's to fix, but the design must not lean on it.

`restore-admin-step-writes` closed the third row and named the first and fourth as stated non-goals. This change closes the fifth, and does so by giving it what the third has rather than by inventing a new mechanism.

## Goals / Non-Goals

**Goals:**

- The decision path reads a roster that is actually readable, so the accept/reject controls work for every active person.
- A wrong collaborator at this seam becomes a `mypy` error at the injection line, in CI, before a deploy — not a runtime refusal, and not a runtime error either.
- If one does reach runtime anyway, it is named as a mis-wiring and never spoken to the decider as a fact about their identity.

**Non-Goals:**

- Unifying all five rows of the table behind one port. `clickup_sync_job` and `activation_readiness` keep their permissive reads — both are fed correctly shaped readers today, and `restore-admin-step-writes` already recorded both as non-goals for the same reason. The `RosterReader = Any` alias in `clickup_sync.py:115` is a separate cleanup with its own blast radius.
- Any new member on `access`'s public surface (see `proposal.md` — Non-goals).
- Changing what a decision refusal *means* in the cases that already work: unknown and inactive are unchanged, wording included.

## Decisions

### 1. The composition root injects a reader; the adapter does not live in `automation_confirmation`

`playbook_admin` keeps the store and adapts it internally because it holds **one** collaborator serving **two** contracts — `verify_admin_session(roster, …)` is typed `RosterStore` and genuinely needs a store. `automation_confirmation` has no such second contract: the collaborator's only use is resolving a Slack identity. So it takes a reader and nothing else, which is `worker.py:119`'s shape rather than `playbook_admin`'s.

The reader is defined in `main.py`, closing over `access`'s public `list_people` and the module-level `PostgresRoster` the root already holds. This near-duplicates `worker.py._RosterReader`, and the duplication is accepted: the two composition roots are separate processes, neither may import the other, and each is the only place in its process permitted to construct `access`'s store. Factoring the pair into a shared helper would require somewhere for that helper to live that is outside both `.importlinter` containers, which is what a composition root *is*.

*Alternative considered:* an adapter class inside `automation_confirmation`, mirroring `_PageRosterReader`. This is **legal** — `launch` may import `access.application`, so the module could call `list_people` itself over an injected store — and it is what `playbook_admin` does. It is rejected here on the single-contract argument above and on decision 3: `playbook_admin` adapts internally because it must hold a store for its guard, and it pays for that by typing the global as `RosterStore` so the mistake is still caught. `automation_confirmation` has no guard to serve, so holding a store would mean declaring a type it has no use for, and adapting it back on every call, to reach the same protection the direct reader gets for free.

### 2. `_person_for` demands one shape and refuses anything else by name

The three-spelling probe is deleted. The function calls `list_people()` and nothing else; a collaborator without it raises `UnreadableRosterError` naming the type supplied and the shape expected, before the decision is judged.

`UnreadableRosterError` and `RosterReader` are reused from `playbook_authoring` rather than redefined — same package, same layer, same meaning, and the error's existing docstring already reasons about exactly this mistake.

The two names are reached differently by the two consumers, and the difference is the module-boundary contract rather than a preference. `automated_decisions` is a sibling inside `launch.application` and imports them directly from `playbook_authoring`. `automation_confirmation` is infrastructure, so it may reach application names **only** through `launch.application`'s `__all__`-exported surface — `playbook_admin.py:58` is the precedent — and both names must therefore be added to that surface. They are not on it today, and decision 3 makes `RosterReader` part of an infrastructure module's declared type, so exporting it is not optional.

The evaluation stays in `launch`, not in the collaborator: `list_people` answers everyone the roster carries **including deactivated entries**, which is what lets this rule decide "known" and "active" as two separate answers with two separate refusals. A `person_for_slack_identity`-shaped port would have to collapse them or return a tri-state, and the roster is not the right place to hold this rule.

*Alternative considered:* keep the probe but make the fall-through raise instead of returning `None`. Rejected — a probe that accepts several shapes still lets a fifth call site be wired against whichever spelling it guesses, and the probe's real cost was never the fall-through alone but that no reader of the code could tell which shape production supplies.

### 3. The module's injection point is typed, which is what actually prevents the recurrence

`read_people: Any` is what let `main.py:140` assign a store to a name meaning reader with nothing objecting. Declaring `read_people: RosterReader | None = None` — the real `Protocol` — makes that assignment an error mypy reports at the assigning line:

```
main.py:140: error: Incompatible types in assignment (expression has type
  "PostgresRoster", variable has type "RosterReader | None")  [assignment]
```

Verified against this repository's `mypy --strict` settings on an isolated reproduction of the two types before this design was written. This is the durable half of the change: decisions 1 and 2 fix and diagnose the fault, decision 3 is what stops a sixth call site repeating it. `_roster_or_fail` narrows the `| None` for callers, and its absence error becomes `UnreadableRosterError` per decision 4, message unchanged.

Note the type must be `playbook_authoring`'s `Protocol` and not `clickup_sync`'s alias; importing the wrong one compiles and protects nothing.

### 4. The mis-wiring is caught at the adapter, logged, and answered without blaming the decider

`UnreadableRosterError` raised inside the use case must not propagate out of the Bolt action handler: Bolt would swallow it after the `ack()`, and the decider would see nothing at all — the one outcome the requirement forbids as loudly as a false refusal. So `_handle_decision` catches it, logs it at `exception` level (this is the "reported where operators see faults" half of the spec), and returns a sentence saying the decision could not be processed and that the fault has been reported — with no clause about the decider's identity, their roster entry, or their authority.

It is caught as its own type, not by a bare `except Exception`. Every other refusal in this path is a returned `Decision`, so a broad catch here would fold genuine bugs into a message claiming the deployment is mis-wired.

**Both wiring faults raise the same type.** `_roster_or_fail` today raises a bare `RuntimeError` when nothing was injected at all, and that error is caught by nothing: it would escape the Bolt listener after `ack()` and leave the decider with a button that does nothing — the exact outcome this decision rules out for the mis-shaped case, reached by the sibling case. So `_roster_or_fail` raises `UnreadableRosterError` instead, naming "nothing was injected" as what was supplied. Its message is preserved; only its type changes. The two faults are then one catch, one reply and one scenario, which is right, because they are one mistake made in two places and a decider cannot act differently on them.

*Alternative considered:* have `_roster_or_fail` check the *shape* too, so a mis-shaped collaborator never enters the use case. Rejected as the *only* mechanism — the guarantee belongs to the use case, which is where the rule is tested and where any future caller arrives. As an additional check it is harmless but redundant, so it is not added; `_roster_or_fail` keeps checking only for absence, which is the one thing the use case cannot check for itself.

### 5. The test double stops answering to everything

`_FakeRoster` in `test_automated_result_decisions.py` implements six read spellings at once, by deliberate design recorded in that file's own header: *"so the shape the implementation picks is satisfied."* That was the right call for a test written from delta specs before an implementation existed. It is the wrong call now that the shape is stated, because a double satisfying every shape cannot fail the way production fails.

It narrows to `list_people` alone, and a second double shaped like `RosterStore` — `load`/`save` only — carries the new wiring scenarios. This narrows a double; it does not weaken an assertion. Every existing test keeps its subject and its assertions, and the policy tests (unknown, inactive, already-decided, no-longer-served) are untouched.

### 6. One test observes the real injection, not a rebuild of it

The delta's fifth scenario says a person the roster carries can decide *through the wiring production supplies*. A test that constructs a reader "the way `main.py` builds it" cannot satisfy that: it is a second object of the same shape, and it goes on passing at the moment `main.py` regresses. That reasoning is precisely what the precedent change rejected — `tests/integration/launch/test_playbook_authoring_roster_live.py:15` records it as *"A double can be shaped wrongly and pass; the real adapter cannot"* — and it is the blind spot that let this fault ship in the first place, since `_FakeRoster` was correct about everything except which object production hands over.

So one test imports `commerce_ops.main` and drives a decision through `automation_confirmation.read_people` **as injected**, asserting a roster person is resolved. `tests/unit/launch/infrastructure/driving/test_main_monitoring_wiring.py` already imports `commerce_ops.main` at module scope in the unit tier with no database and no production secrets, so this needs no new tier and no new fixture; what is under test is the object at the assignment, not Postgres.

Where the substitution lands decides whether the test can fail at all, so it is part of the decision rather than an implementation detail. It goes at the **store** — `main.roster` — leaving the reader's own call into `access`'s real `list_people` intact. Substituting `main.list_people` instead would replace the reader's entire body, and a reader closed over the wrong store would pass: the same escape this decision exists to close, one level down. This requires the reader to resolve the `roster` global at call time rather than capture it at construction, which is why that is a task of its own rather than left to taste.

The `mypy` guarantee of decision 3 does not replace this and is not replaced by it. Decision 3 catches a collaborator of the wrong *type*; this catches a reader of the right type wired to the wrong thing — closed over nothing, or answering an empty roster — which is failure scenario 2 and the one shape of this bug that types cannot see.

## Risks / Trade-offs

- **Narrowing `_FakeRoster` touches a file the test-writer authored, in a change whose own tests the test-writer will author.** → The narrowing is stated here and carried as its own task, so the reviewer sees it as a deliberate design decision rather than an implementation liberty. No assertion changes; if any existing test fails after the narrowing, that is a finding to report, not to fix by re-widening the double.
- **`main.py` and `worker.py` now hold near-identical reader adapters.** → Accepted explicitly in decision 1. The alternative costs a module that exists outside both `.importlinter` containers, which is a larger architectural change than the bug warrants.
- **Decision 3 protects this seam only.** `clickup_sync_job.read_people` keeps its `Any` alias and stays mis-wireable. → Named as a non-goal rather than silently left; the alias is a one-line change with a blast radius across `clickup_sync`'s whole signature set, and belongs to whichever change next touches that module.
- **The seam test must not itself become a mock that proves nothing.** A test asserting "`UnreadableRosterError` is raised when I pass an object I built to lack `list_people`" is nearly tautological, and a positive test against a *rebuilt* reader is worse — it looks like coverage of the production wiring while being immune to the production wiring changing. → Decision 6: the positive scenario is carried by a test that reads the injected collaborator itself. The negative scenarios keep their hand-built doubles, which is appropriate, because there the double's shape *is* the input under test.
- **Importing `commerce_ops.main` in a unit test couples that test to the whole composition root.** A future import-time failure anywhere in `main.py` surfaces as a failure in a roster test. → Accepted, and already accepted once: `test_main_monitoring_wiring.py` makes the same trade deliberately, and its module docstring explains that catching import-time wiring faults in the unit tier is the point rather than a side effect.

## Migration Plan

No data migration, and no recovery step. Every refused decision recorded nothing and settled nothing, so each pending result still stands. The Slack messages already posted carry `product_id` and `step_id` in their button values and resolve them fresh on each press, so the existing backlog becomes decidable on deploy without re-delivery.

Rollback is reverting the merge: the prior state refuses every decision, which is what the current state already does, so no partially-decided data can exist to strand.
