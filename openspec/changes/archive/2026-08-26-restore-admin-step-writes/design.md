## Context

See `proposal.md` — *Why* for the fault and how it was reproduced.

Three constraints shape every option below.

**The injected collaborator has to stay the store.** `playbook_admin.roster` is read by two things: `_require_admin`, which passes it to `access`'s `verify_admin_session(roster: RosterStore, …)`, and the page's writes, which pass it to the authoring use cases as a *reader*. Those are two different contracts on one global. Swapping the injected object for a reader would break the guard; the page therefore has to adapt rather than the composition root re-inject.

**`launch` may only reach `access` through its application surface.** `.importlinter`'s `products-infrastructure-boundary` already exempts the `access.application -> access.domain` chain precisely so the admin page can call `verify_admin_session`, and `playbook_admin` already imports `list_people` beside it. `launch.application` carries no such exemption, so `playbook_authoring` cannot resolve the roster itself — which is exactly why it duck-types the collaborator, and how it came to accept three shapes and miss the real one.

**The adaptation already exists, one function away from the bug.** `playbook_admin._roster_people()` reads the store through `access`'s `list_people` and answers a tuple of people. The read path calls it; the write path does not.

## Goals / Non-Goals

**Goals:**

- The five write routes evaluate their roster preconditions against the same roster the page renders from.
- A collaborator that cannot answer the roster question fails by name at the call, not as a `TypeError` from inside a write.
- No write on **the playbook admin surface** can fail without the admin being told. The roster admin surface is out of scope and needs nothing: it boosts nothing, so its failures already reach the browser.

**Non-Goals:**

- Unifying the two other duck-typed roster readers in `launch` — `clickup_sync._roster_people` and `activation_readiness._people_of` (see `proposal.md` — *Non-goals*). `playbook_authoring`'s own reader is narrowed here; those two are not.
- Any change to the preconditions themselves, to the steps they are scoped over, or to any coherence rule. This change makes an existing rule reachable; it does not alter it.
- Retrofitting the admin surface with a general client-side error framework. The requirement is that a failed write is visible, not that it is diagnosable from the browser.

## Decisions

### The page adapts the store; `main.py` is not touched

`playbook_admin` gains one small reader that delegates to the existing `_roster_people()`, and the five write routes pass *that* to the use cases instead of the raw `roster` global.

*Alternative considered: a second injected global,* `playbook_admin.read_people`, *set by `main.py`* — the shape `clickup_sync_job.read_people` uses, fed by `worker.py`'s `_RosterReader`. Rejected here because the parallel is weaker than it looks: `clickup_sync_job` needs the injection because it has no `access` import of its own, while `playbook_admin` already imports `list_people` and already performs this exact adaptation for its reads. A second global would add a wiring step that a future composition root can forget — which is the failure mode this change exists to fix — in exchange for nothing the page cannot do itself.

*Alternative considered: teach `playbook_authoring._read_people` to accept a store* (`rows, _ = await roster.load()`). Rejected: `access`'s stored row is a `PersonRecord` that nests `person: Person`, so `launch.application` would have to learn `access`'s row shape to unwrap it — importing that module's internals by duck-typing rather than by `import`, which is the boundary the contract exists to hold.

### The roster collaborator gets one shape, and mypy gets to see it

`playbook_authoring` narrows to a single `RosterReader` protocol — `async def list_people() -> Sequence[...]` — and the five write use cases type their `roster` parameter as `RosterReader | None` instead of `Any`. A collaborator that does not satisfy it is refused with a message naming what was passed and what was expected.

Two things make this cheap. Every existing roster double in `tests/unit/launch/` already exposes `list_people()`, so no test is invalidated by dropping the callable and iterable branches. And typing the parameter is what would have caught this at the call site in the first place: `roster: Any` is why `create_step(roster=PostgresRoster())` type-checked.

*Alternative considered: keep the three shapes and fix only the caller.* Rejected — it leaves the trap armed for the next caller, and this is the second reader in the module to be fed the wrong shape.

### A mis-shaped collaborator is raised, not added to the fault list

"Fault" is a term of art in both existing specs: an entry in a rejected write's fault list, which `playbook-admin` renders in full with the submitted values retained and, where attributable, marked on the field it concerns. A mis-wired collaborator must **not** enter that list. It is not a judgement about the playbook the admin submitted, and rendering it as one would show an operator defect in an author's form — at 200, where nothing but the browser could tell a broken deployment from a rejected edit.

So the refusal is raised. It reaches the admin through the notice the second half of this change installs, and it reaches the deploy's health signals as the error it is.

*Alternative considered: report it as a fault, reusing the surface's existing rendering.* Rejected for the reason above; it is also the cheaper option only until the first time somebody has to work out why a deployment looks healthy while every write is refused.

### The roster stays optional, and the reason is recorded

`roster=None` remains permitted and keeps its meaning: "these two preconditions are not being evaluated here". It is retained rather than chosen afresh — the five use cases already default it, and callers that legitimately judge a write without a roster exist — but the delta now states it as one of three distinct cases rather than leaving it implicit, and states that an unreadable collaborator can never collapse into it.

*Alternative considered: make the roster required.* It would close the remaining way to skip the preconditions by accident — forgetting an argument rather than passing the wrong object. Rejected as scope: it changes the signature of five use cases and every call site that omits the argument today, for a hazard nothing has yet hit. Worth its own change if a caller ever does hit it.

### A failed write is surfaced on the client, and the server keeps telling the truth

The server goes on answering its real status. The page gains a small listener that renders a notice when a submission does not complete.

**It binds three events, not one.** `htmx:responseError` covers a response the page cannot render. It does *not* cover a submission that gets no response — htmx raises `htmx:sendError` for that — nor one that never arrives, which raises `htmx:timeout`. Those are not exotic: every merge to `main` restarts the container (`AGENTS.md` — *Deployment*), so a write in flight during a deploy lands squarely in the second case. A listener bound only to `htmx:responseError` would ship the guarantee with a hole in the case this deployment model produces most often.

**What the notice says is bounded by what the page can know.** The page observes that a submission did not complete. It cannot observe whether anything was persisted: a failure raised *after* `steps.save` produces the same response class as one raised before it. So the notice says the write did not complete and that what is on screen may no longer describe the step set, and directs the admin to reload — it does not claim nothing was saved. The claim is cheap to make and wrong exactly when it matters, which is why the requirement now forbids it.

**An ended session is called by its name, and the client works it out alone.** The guard's refusal is the page's own 404, and it is the one failure in this class the admin can act on — treating it as unexplained would leave someone reloading a page that will keep refusing them. So the notice distinguishes it and offers the way back.

The distinction is drawn **client-side, from what the page already knows**: it posted to a route the server had just rendered for it, so a 404 answering that post is the guard refusing, not a route that does not exist. Nothing is marked on the server to make it recognisable — and that is the point. `playbook-admin`'s existing requirement *The presentation assets stay behind the admin guard and need no build step* has the guard answer "the app's own 404, identical to an unregistered route, revealing nothing about what exists"; a distinguishing marker on the write routes would make them probeable, trading a guarantee the surface already holds for a convenience the client does not need.

This also bounds the clause: it applies to submissions the page enhances. The create form is un-boosted by design, so its failures — an ended session among them — reach the admin as the browser's own error page. Less legible, never silent, and boosting it to fix that was rejected above for reasons that have not changed.

*Alternative considered: override `htmx.config.responseHandling` so `[45]..` swaps.* Rejected: that would swap FastAPI's default error body into the admin page's `body`, destroying the page to display a string.

*Alternative considered: catch unexpected exceptions server-side and re-render the form with a notice at 200.* Rejected: it preserves the "every fault, with the submitted values still in the form" shape, but answering 200 for a write that did not happen lies to everything that is not a browser — the deploy's health signals included.

*Alternative considered: un-boost the write forms, as the create form already is.* Rejected: it trades a silent failure for a raw browser error page and gives up the boost on every successful write to do it.

Where JavaScript does not run, a boosted form degrades to an ordinary form post and the browser shows the error itself — unhelpful, but never silent, which is the guarantee this change makes.

### The listener lives in the shared header partial

`page.html` and `edit.html` are the only two boosted admin templates, and both include `_admin_header.html`. The listener goes there, in one copy, for the reason that partial records for itself: it exists so the two admin surfaces cannot drift apart. Two copies of an error handler across two templates that boost is exactly the drift it was created to prevent.

**The container the notice renders into goes there too**, beside the listener, rather than the listener reaching for a slot each page happens to own. `page.html` has a notice slot; whether `edit.html` carries one in the same shape is not something the drift argument covers, and a listener that finds no target is a listener that fails silently — which is the whole defect being fixed. Shipping both halves in the partial makes the pairing true by construction instead of by inspection.

The roster admin page and the create surface include the same partial and boost nothing, so the listener is inert on both — correctly, since neither can produce the failure it exists to catch. The partial already carries `hx-boost="false"` attributes, so it is not being taught about htmx for the first time.

## Risks / Trade-offs

- **The notice tells the admin a write failed, not why.** → Accepted, with one exception carved out: an ended session is named, because it is the only case in this class the admin can resolve themselves. Everything else reaches the admin as "it did not complete, reload"; the named faults an authoring write reports keep their existing full-fidelity rendering, and the server-side log carries the diagnosis.
- **A failure raised after `steps.save` would report a write that did in fact land.** → Mitigated by what the notice is allowed to claim: it directs the admin to reload rather than asserting nothing was saved, so the worst outcome is a reload that shows the write succeeded. Asserting the opposite would have been actively misleading in exactly this case.
- **Narrowing the collaborator shape could break a caller outside `tests/unit/launch/`.** → Every call site was enumerated: the five admin write routes are the only ones that pass a roster to an authoring use case. `clickup_sync_job` and `activation_readiness` take their own readers and are out of scope.
- **The reproduction ran against the local development database, whose roster is empty.** → The `TypeError` precedes any roster content, so the diagnosis does not depend on it. But an empty roster is not a neutral state for the *fixed* path: once the preconditions actually run, an `active` `human` step can no longer be saved without an assignee the roster carries. Verification has to happen against a roster that holds people, or the fix will look like a different failure.

## Migration Plan

No data migration. Every failing write raised before `steps.save`, so nothing was half-written and the step-set version never moved — confirmed against the local database, where four probe writes left version `1465` unchanged.

Rollback is the revert: the surface returns to its current state, which is one where no write works.

## Open Questions

None. The one that stood here — where the failure notice belongs — was resolved against the surfaces themselves: the roster admin page turns out not to boost at all, so its writes already surface their own failures through the browser, and the question reduces to the two boosted playbook templates. See *The listener lives in the shared header partial*.
