## Context

See `proposal.md` — *Why*. What this section adds is the state of the code the screen drops into.

`subcategory-advisor` is the only step handler with judgement in it today, and it is the only worked example of the shape. It arrived at that shape by failing twice in production, and both failures are recorded in archived changes this design treats as settled ground rather than reopening:

- `fix-subcategory-advisor-structured-output` (2026-09-01) — a top-level `Supported | Unsupported` union was rejected by `langchain_openai`'s conversion before the model was ever called, making the handler inert at 100% of invocations. A `BaseModel` wrapping a *discriminated* union would have passed every offline check and failed at the API instead, because pydantic emits `oneOf` for a tagged union and OpenAI's strict structured outputs accept only `anyOf`. The fix was a deliberately flat object of nullable scalars.
- `await-the-subcategory-advisors-graph` (2026-09-02) — the graph was reached through the synchronous entry point, pinning the event loop for the length of each model call. The compiled graph is now async-only, and `invoke` on it raises by construction rather than by convention.

Both are pure shape lessons, and both apply unchanged to a second handler. This design's job is to say where this screen differs, not to re-derive what they established.

What the screen is given is fixed by `launch-step-automation`: a frozen `StepContext` carrying `step`, `launch`, `product` and `as_of`. Two of those matter here. `context.product` supplies the product's name — the substance of what is screened. `context.step` supplies the `StepDefinition`, whose `description` is `str | None` and is where the categories come from.

`.importlinter`'s `step-handler-boundary` contract names `commerce_ops.step_handlers` as a whole, so a new discipline package beneath it needs no contract edit and inherits the prohibition on reaching past `launch.application`.

## Goals / Non-Goals

**Goals.** A second handler that a reader of the first recognises immediately — same graph split, same async discipline, same registration path, same flat wire schema — differing only where this step's question genuinely differs from the advisor's.

**Non-goals, beyond the proposal's.**

- **No shared handler library.** `step_handlers/` "holds handlers and nothing else. It never grows a `domain/`, `application/` or `infrastructure/` layer of its own." Where this screen repeats a shape from `subcategory_advisor`, it repeats it locally. Factoring the common parts out is a legitimate future change once there are three handlers and the actual commonality is observable; doing it at two, across disciplines, would invent an abstraction from one example.
- **No change to the automation pass.** Everything this handler needs — invocation, cool-offs, holding a terminal proposal for a confirmer, recording a non-terminal one directly — `launch-step-automation` already provides.

## Decisions

### The category list is read from `context.step.description`

**Chosen** over a module-level constant in the handler, and over a runtime-configuration variable.

The spec states the behaviour and its consequence; the reasoning about the alternatives belongs here.

A constant in Python is the obvious implementation and the wrong one. The step's description is already the list — it is the sentence a member opens the step to read, and `playbook-authoring` already validates and owns edits to it, recording the updating principal and the date. A second copy in code has nothing keeping the two in step, and the divergence is silent in the worst direction: the member reads one list, the screen tests another, and the evidence recorded on the launch cites the sentence that was *not* used.

**There is a direct precedent, and it is stronger than the argument above.** `playbook-authoring`'s *Authoring never touches the framework* already establishes that operative content lives in a step's description and is edited by whoever may edit the step: "A threshold a gate turns on is therefore editable, as the description of the step that establishes it." A screening list is the same kind of content under the same rule. This design is not introducing a coupling; it is using one the project has already decided in favour of.

A configuration variable is worse still. `runtime-configuration` requires a declared variable for anything configured per deployment, and adding one means four coordinated edits (Environment secret, `deploy.yml`, the settings model, the declared set in the settings test) for a value that is not per-deployment at all — it is per-step, and there is already a per-step field holding it.

The cost is real and is stated in the spec: an admin rewording the description reworks the screen. It is accepted because the same admin editing the same field already changes what every member is asked to do, which is a strictly larger power over the same step, and because the coupling is made **visible** rather than merely accepted — see the next decision.

`description` is `str | None`, so the absent case is not hypothetical. It routes to a non-terminal outcome with its own reason, **before any model call** — never to a fallback list, which would make the screen silently authoritative about something nobody authored, and never to a prompt naming no categories, which a model would answer anyway.

### The produced text cites the categories, rendered by the handler

The coupling above is only safe if a narrowed screen is detectable after the fact. So the text the screen produces states the categories it read, and the handler renders that from `context.step.description` rather than taking it from the model's `comment`.

Taking it from the comment is the tempting shortcut, and this change's own rules close it off: the verdict requirement forbids code from inspecting the comment's content, so a citation carried there could not be relied on, could not be asserted by any test, and would be exactly the free-text-parsing dependency the project retired. Rendering it makes the mitigation real, and gives the member reading the result the list the screen actually used — which is where a narrowed screen would in practice be caught.

The rendered text is therefore three parts: the cited categories, the verdict, and the model's comment.

**The description's text is carried through unaltered, and nothing is extracted from it.** No parsing into category names, no selecting the part that looks like a list. The temptation is real — the seeded description reads as a sentence with a parenthetical of eight examples in it, which looks parseable — and it is the wrong instinct twice over. A parser keeps what matches its shape and silently drops the rest, so a description naming both a referenced list and inline examples would be cited as the examples alone, understating the screen while every assertion written against those examples passed. And a screen that parsed prose to say what it screened against would be doing, in its own citation, exactly what this change forbids it doing to the model's answer. The prompt and the citation carry the same unaltered text, which is also what makes them checkable against each other.

### A model failure propagates; the handler catches nothing

`launch-step-automation` already reports a raising handler naming the launch, step and handler, records nothing against the step, and continues the pass. The correct behaviour is obtained by **doing nothing** — no `try` around the model call.

What the requirement adds is the prohibition on someone later adding one. With `include_raw=True` the boundary between "the response mapped to no verdict" and "the call failed" is subtle, and the unreadable-verdict route sits immediately adjacent to it; a broad `except` landing there would record an outage on every launch as the screen's judgement about a product, and would suppress the operator-facing fault at the same time.

Routing a failure to a fourth non-terminal reason was considered and rejected: `launch-step-automation` states directly that a failure is not recorded as any outcome, `Blocked` included, so it would contradict an existing specification. Retrying inside the handler is outside scope — the pass already retries by invoking again next time.

### One enum discriminant for three states, not two booleans

**Chosen** over `determinable: bool` + `clear: bool`, and over a fourth nullable `error` string.

The screen has three answers where the advisor had two, and the three are mutually exclusive. Two booleans can express `determinable=false, clear=true`, which means nothing, and every such combination would need a defined destination in the wire conversion — paying the advisor's `_from_wire` totality cost for states the domain does not have. One enum field of three literal values cannot express them at all.

A separate `error` field is the advisor's shape, and it is what created that handler's `Contradiction` case: `ok=true` carrying an error is a state the reported variants forbid but the wire schema permits. Here `undetermined` **is** the structured home for "I cannot answer", so a model with nothing to assert has a slot to put it in and no reason to reach for a contradicting one.

**Schema shape.** A flat `BaseModel` — one `Literal["clear", "flagged", "undetermined"]` field and one nullable string `comment`. Pydantic emits a plain object with a string property carrying `enum`, which is inside OpenAI strict structured outputs' accepted subset and is not `oneOf`. No union appears anywhere in it, at the top level or nested.

That last claim is exactly the kind that read as true before `fix-subcategory-advisor-structured-output` and was not, so it is asserted by a test at the adapter's own conversion boundary rather than by reasoning — see below.

### The conversion guard is replicated, not shared

`tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py` runs the real `langchain_openai` conversion over the advisor's schema, with a fake model that refuses to generate, asserting no socket is opened and no credential is present. It exists because "every existing test of this handler scripts `with_structured_output(...)` directly, so the real conversion was never invoked by anything" — which is how a 100%-failure regression shipped.

This screen introduces a **new schema with a construct the advisor's does not have** — a string enum. Reasoning that an enum is inside the strict subset is precisely the reasoning that failed last time. So the screen gets its own conversion guard against its own schema, in the unit tier for the same reason the advisor's is there: it asserts a library contract over a schema object, not graph behaviour.

Not shared with the advisor's, and not parameterised over both: the value of the test is that it converts *the schema the call site passes*, and a shared harness invited to take a schema as a parameter is one refactor away from testing a schema no call site uses.

### The contradiction veto is local and screen-specific

The advisor's `_ADVISOR_REFUSES` regex matches a first-person subject refusing to name *a node, sub-category, placement or classification*. Reused verbatim here it would miss the statement this screen needs to catch ("I cannot screen this product without knowing whether it contains a battery") and would fire on prose about a category the product was cleared against.

So: a local regex, same construction — a refusing subject plus a refusal verb plus this screen's own objects (*screen, classify, determine, assess*). The duplication is deliberate. The two vetoes match different sentences about different things, and the only thing genuinely common between them is a technique.

Its scope is narrow by design. With `undetermined` available as a structured verdict, a well-behaved model has no reason to write a refusal under a `clear` verdict at all; the veto exists for the badly-behaved case, where a false `clear` reaching a confirmer would put a sourcing decision one unread paragraph from being committed.

### Graph, registration and imports mirror the advisor exactly

`build_graph(model)` / `build_production_graph()`, so `tests/agents/` drives it with a stubbed model. One async node, so the compiled graph answers `ainvoke` and raises on `invoke` — the enforcement, not the convention, for `launch-step-automation`'s *a handler's waiting does not stop the process*. `langgraph` and `langchain_openai` imported **inside** the functions that build a graph, and the production graph `lru_cache`d, so that importing the module registers a name and loads nothing the run needs. `registrations.py` gains the import and the tuple entry, so both composition roots hold it and cannot disagree about whether the handler exists.

None of this is a fresh decision. It is named so that a reviewer can check it was not quietly dropped.

### Model: the same one the advisor uses

`gpt-4o-mini`, matching `build_production_graph()` next door.

The argument for a stronger model is real — this screen leans on recall of Amazon's prohibited and high-compliance categories, where the advisor leans on taxonomy structure. The argument against changing it now: the safeguard on this step is not model strength, it is that `undetermined` is a first-class verdict and that satisfaction is held for a named confirmer. A weaker model failing on this step produces more `undetermined` verdicts, which is the designed-for outcome, not a wrong answer.

Starting matched keeps one variable out of the first comparison between two handlers. It is a one-line change if the verdict distribution in practice argues for it.

## Risks / Trade-offs

**An admin rewords the step description and silently narrows the screen.** → Accepted, and stated in the spec. Mitigated by the handler rendering the categories it read into the produced text, so a narrowed screen is visible in the record of any launch it ran on — a built obligation with a test behind it, not an assumed property of the model's prose. `playbook-authoring` additionally records who edited the description and when, so the record and the edit can be reconciled.

**A correct flag reaches a member only indirectly.** → A flagged verdict is non-terminal, so `launch-step-automation` records it directly rather than holding it for the confirmer, and it holds no gate because the step is authored `blocking: false`. It surfaces through *A step whose handler has stopped making progress is reported once*, framed as a handler making no progress though its text does carry the flag. This is the change's primary success path and it is adequate under the existing machinery, but it is worth naming: the flag is not a notification, it is a record plus a stuck-step report. Making it louder would mean changing `launch-step-automation`, which this change does not.

**The model asserts `clear` for a product whose classification actually turns on an undisclosed material.** → The step names a confirmer, so `clear` is held for a member's acceptance and never records itself. This is the primary safeguard and the reason the activation recommendation below is not optional.

**A string enum turns out to be outside the provider's strict subset.** → The conversion guard fails offline, before the handler is ever activated. This is the whole reason that test is a task and not a nicety.

**`undetermined` becomes the answer almost every time, and the automation is theatre.** → Visible immediately: the step's recorded outcomes are all non-terminal with the undetermined reason. The response is to give the screen more of the product than its name, which is a catalog change and deliberately outside this one. Worth measuring on the first handful of launches before building anything on top.

**Two handlers now duplicate a shape.** → Accepted at two, revisited at three. Named as a non-goal above so that a reviewer reads it as a decision rather than an oversight.

## Migration Plan

No schema change, no migration, no new configuration. Deployment is the ordinary path: branch → PR → merge to `main` → deploy.

Activation is a separate, manual step afterwards, through `playbook-authoring` against the live set:

1. **Confirm the step's hazard permits `Satisfied`.** `launch-playbook` permits only `Refused` as terminal for a `prohibited-tactic` step, so a `clear` verdict on such a step is a handler fault every pass — recorded nowhere, reported forever, and the handler permanently inert. The seeded definition of `lp.strategy.006` declares no hazard and so takes the default of `none`, which permits `Satisfied` and `NotApplicable`; but the live set is in Postgres and the seed is not evidence about it, so this is checked at activation rather than assumed here. `compliance-obligation` also permits `Satisfied` and is equally fine; only `prohibited-tactic` is not.
2. Set `lp.strategy.006` to `kind: automated`.
3. Name `strategy.compliance_screen` as its `handler`.
4. **Name a confirmer.** A step with no confirmer has its terminal proposals recorded directly, which would let the screen record `Satisfied` on a compliance question with nobody reading it. Every risk above rests on this being set.
5. Leave `blocking: false` as authored.

Rollback is authoring, not deployment: clear the handler and set the step back to `human`. The step returns to human attestation with its recorded outcomes intact, and the registered handler simply stops being invoked.

The startup handler report names the handler once the code is deployed, so step 3 can be validated against a registry that already knows it.

## Open Questions

- **Should the screen eventually write its verdict to the product?** Not needed by anything today, and the proposal excludes it. Worth revisiting once a second consumer exists — `lp.strategy.001` plausibly wants to know the product was flagged before it spends a SERP call on it.
- **Does `lp.strategy.006` want an `after_steps` edge?** It screens before sourcing and depends on nothing else in the `commit` gate, so probably not. Raised only because the same review of the gate found `lp.strategy.001` genuinely does need one, and the two questions are easy to conflate.
