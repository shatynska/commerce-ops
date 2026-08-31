## Context

See proposal.md for motivation. Three constraints shape everything below:

- `subcategory_advisor`'s graph is built with `build_graph(model)` / `build_production_graph()` specifically so `tests/agents/` can drive it with a stubbed model and no network or database (`AGENTS.md`'s Testing Strategy names `tests/agents/<subject>/` as carrying "no network/IO cost"). Any change here has to keep that seam.
- `.importlinter`'s `step-handler-boundary` contract forbids `commerce_ops.step_handlers` from importing `commerce_ops.catalog` at all, with its own stated reason: a handler reaching into the catalog itself "would defeat the contract that has the pass resolve the product once and hand it over." `subcategory_advisor.py` cannot call a catalog use case directly, full stop.
- The same cross-module problem was already solved once, for the graduation stamp: `launch.application` never imports `commerce_ops.catalog.infrastructure`; it depends on a `Protocol` shaped like the catalog use case it needs minus the store (`launch/application/ports.py`'s `SteadyStateStamper`), satisfied by a partial application of `catalog.application.change_stage` wired at the composition root. `.importlinter` explicitly exempts `launch.application.** -> catalog.application` for exactly this.

## Goals / Non-Goals

**Goals:**
- `subcategory_advisor` gets a schema-validated structured response from the model instead of a hand-parsed `Verdict:` line vetoed by regex.
- The proposed sub-category node is written onto the resolving product the moment the advisor's graph runs — provisional, not gated on the step's own Slack confirmation.
- The `Success[T]`/`Failure[E]` result shape is generic enough that a second automated handler can reuse it without redesigning it.
- The write itself happens through the same port pattern the graduation stamp already established, so `step-handler-boundary` stays intact and `subcategory_advisor` stays exercisable without a database.

**Non-Goals:**
- Capturing the *main* category anywhere in commerce-ops. It isn't held anywhere today (no automated step, no product field, no attestation path) — introducing that is a separate, larger change (see Open Questions).
- Reconciling a rejected Slack decision with an already-written product field. The write is explicitly provisional; making it consistent with a later rejection is out of scope here (see Risks).
- A fully generic "any handler writes any product field" dispatch mechanism. Only `subcategory_advisor` → `sub_category` is being wired; a second handler wanting the same pattern adds its own port, following this one as precedent, rather than this change inventing a registry for a need that doesn't exist yet.
- Changing whether `lp.listing.007` needs confirmation. It still does; only the product write moves ahead of that decision.

## Decisions

### 1. `Success[T]` / `Failure[E]` live in `shared.domain`, universal down to their fields — `comment` included

```python
# shared/domain/result.py
@dataclass(frozen=True, slots=True)
class Success(Generic[T]):
    value: T  # laconic — exactly what gets recorded
    comment: str | None = (
        None  # optional — additional information, for a person or for tuning
    )


@dataclass(frozen=True, slots=True)
class Failure(Generic[E]):
    error: E  # laconic — why nothing was recorded
    comment: str | None = None


Result = Success[T] | Failure[E]
```

This widens the shape from an earlier draft that put `comment` only on this one handler's own LLM-facing schema. Moving it onto `Success`/`Failure` themselves is the point the user corrected: **any** generic code that later touches a `finding` — not just this handler's own rendering — must never need to know a field is called `sub_category` or `compliance_demands`. `value`/`comment` are the whole vocabulary; every future automated handler's finding is shaped the same two ways, whatever domain-specific meaning `T` (and `value`'s content) carries for that handler.

`shared` is the one module every other module may depend on (`shared-boundary` forbids the reverse), so this is where a type meant for reuse across future handlers belongs — not inside `launch` or inside `step_handlers`.

`StepResolution` (`launch/application/handler_contract.py`) gains one new, optional field:

```python
@dataclass(frozen=True, slots=True)
class StepResolution:
    outcome: StepOutcomeValue
    result: str
    finding: Result[Any, Any] | None = None  # NEW, defaults to None
```

`outcome` and `result` keep meaning exactly what they mean today — the launch's own outcome vocabulary and its evidence text. `finding` is additive: a handler that has nothing to hand downstream (every handler today, and most future ones) simply never sets it, and nothing about existing behavior changes. `subcategory_advisor` is the first handler to populate it: `Success(value=sub_category, comment=...)` on a supported result, `Failure(error=reason, comment=...)` on an unsupported one.

**Alternative considered:** restructure `outcome`/`result` themselves around `Success`/`Failure` instead of adding a field. Rejected — `outcome` answers "what happens to the step" (the six-value `launch-playbook` vocabulary; `Satisfied` carries no payload by design) and `finding` answers "what did the handler discover, if anything, that something else should read" — two different questions that happen to correlate for this handler but won't for every future one (a handler might resolve `Satisfied` with nothing worth writing anywhere).

### 2. The advisor's structured output mirrors `Success`/`Failure` exactly — one recorded value, one comment

`build_graph`'s `recommend` node currently sends one prompt and parses free text with `_split_verdict` / `_ADVISOR_REFUSES`. It moves to `model.with_structured_output(AdvisorResult, include_raw=True)`, where the LLM-facing schema is the same two-field shape as Decision 1's domain type, not a bespoke one:

```python
class Supported(BaseModel):
    ok: Literal[True]
    value: str  # the sub-category node, as a full path — becomes Success.value
    comment: str | None = None  # everything else — becomes Success.comment


class Unsupported(BaseModel):
    ok: Literal[False]
    error: str  # non-empty — becomes Failure.error
    comment: str | None = None


AdvisorResult = Supported | Unsupported
```

The compliance demands and rejected alternative the existing `subcategory-advisor` requirement still requires ("gives its reader nothing to disagree with") do not get their own fields any more — the advisor is **prompted** to put them in `comment`. What `subcategory-advisor`'s own spec actually enforces in code is narrower and deliberately so: only that `comment` is **non-empty** for a `Supported` response. It does not, and per the spec explicitly SHALL NOT, check *what* the comment contains — an empty comment is a shortfall code can detect without reading prose; whether a non-empty comment actually names the rejected alternative is exactly the kind of content judgment that made the old `_ADVISOR_REFUSES` regex fragile, and checking for it here would reintroduce the same failure mode one field over. The system already trusts the model this same way for the node choice itself — nothing verifies `value` names a real taxonomy path either. This is what actually answers the user's concern: the *generic* shape stays at two fields for every handler, and the one thing a specific handler's spec is allowed to add on top is a non-emptiness requirement, not a content-inspection rule that would need per-handler parsing logic.

**The free-text veto narrows to `comment`; it does not disappear.** The current spec vetoes a `Supported` proposal whose prose admits it can't actually choose — that protection exists because a false `Satisfied` reaching a person is worse than a false `Blocked`, and nothing about moving to structured output removes that asymmetry. `comment` is now where all of the advisor's narrative lives (compliance demands, rejected alternative, and any aside), so it is also the one place a model could still write "actually I'm not sure" despite setting `ok: true` — `_advisor_refuses` survives, narrowed to scan only `comment`, instead of the whole rendered response. `value` itself carries no prose to misread — it is just the node path.

**Alternative considered:** keep the `Verdict:` line, only reshape what follows it. Rejected — the whole reason for this change is that a regex reading prose for a refusal is exactly the fragility the advisor's own spec already calls out ("the recommendation's wording... nothing constrains"); a schema the model must satisfy removes that class of failure rather than making it harder to trigger.

**Alternative considered:** keep `sub_category`, `compliance_demands`, and `rejected_alternative` as three separate required fields (an earlier draft of this design). Rejected on the user's explicit correction: a bespoke, step-specific schema is exactly what a reusable pattern for future automated handlers should not be — the template to copy needs to stay at "one recorded value, one optional comment" so that nothing generic downstream ever needs per-handler field knowledge.

**Compliance note carried into the spec delta:** `subcategory-advisor`'s existing "No tool invocation" requirement forbids the advisor from invoking "any external tool, function, or marketplace API" while producing its recommendation. Structured output is typically implemented via the same function-calling mechanism as a tool call, even though nothing external is invoked and no side effect occurs. The spec delta narrows the requirement's wording to "no external, side-effecting call" so this is unambiguously compliant rather than an accidental violation of a rule written before structured output was in scope.

### 3. The write happens through a port, not inside the handler

New port on `launch/application/ports.py`, shaped exactly like `SteadyStateStamper`:

```python
class SubCategoryRecorder(Protocol):
    """Records a product's sub-category finding — `record_sub_category`'s
    shape minus the store, so the launch module never sees catalog
    internals."""

    async def __call__(self, product_id: ProductId, sub_category: str) -> object: ...
```

Satisfied by a partial application of the new `catalog.application.record_sub_category` over the catalog store, wired at the composition root the same way `stamp_steady_state` is. Where a handler's `StepResolution.finding` is a `Success`, and the runtime that invoked it (`launch-step-automation`'s pass) knows a recorder port was supplied for that step, it calls the port with the finding's value immediately after the handler returns — before, and independent of, whether the step's own outcome is held for Slack confirmation. This keeps `subcategory_advisor.py`'s graph exactly as testable as it is today: `tests/agents/` still drives it with a stubbed model and asserts on the returned `Supported`/`Unsupported` value, with no catalog and no database involved.

**Alternative considered (and the one flagged to and rejected by the user):** let `step_handlers` depend on `catalog.application` directly. Rejected because `step-handler-boundary` forbids it for a reason that applies exactly here — a handler with its own path into another module's data is the failure mode the rule exists to prevent, and loosening the rule to fit one handler would loosen it for every handler after it too.

### 4. `product-catalog` gains one field, recorded independently of stage

```python
# catalog/domain/product.py
def record_sub_category(self, sub_category: str) -> None:
    self.sub_category = sub_category
```

Mirrors `record_asin` exactly (`catalog/application/use_cases.py:46`) — a standalone fact, not part of the stage machine, overwritable, no confirmer tracked on the product itself (unlike a stage change, this isn't a state-machine transition; it's closer to recording an ASIN, which also carries no confirmer). The comment a model produces (Decision 1) is **not** stored on `Product` — it stays where the advisor's other narrative text already lives, in the launch's step-outcome evidence, so `Product` keeps carrying facts rather than accumulating per-handler audit prose.

### 5. What the advisor reports back, once it has written

`StepResolution.result` (the Slack message and the recorded evidence) stops being the model's unconstrained prose and becomes a rendering of exactly the two fields Decision 1/2 carry: the recorded value (the node) and the comment — which, for a supported result, is required to be non-empty and is *prompted* to carry the compliance demands and the rejected alternative, not code-verified to (Decision 2's disclaimer applies here identically: the same substance a reader needs today, just written by the model into one field instead of assembled into free paragraphs across three, and trusted rather than checked). On the unsupported path, nothing is written and `result` states why, from `Failure.error`, with `Failure.comment` appended if present.

## Risks / Trade-offs

- **A rejected Slack decision leaves `Product.sub_category` disagreeing with the step's recorded outcome.** The write is provisional by explicit choice (see proposal.md), so this is an accepted, known state, not a bug this change fixes. → Mitigation: none implemented here; a future change can decide whether rejection should clear or flag the field once this pattern has a second real handler to generalize from.
- **`Success`/`Failure` is unused by every other handler on day one.** A generic type introduced for exactly one caller risks looking premature. → Mitigation: it's genuinely load-bearing for this one handler today (`finding` is how the port gets its value), and its cost if never reused again is one small dataclass pair in `shared.domain` — cheap enough to justify against the user's explicit "build the pattern once" goal.
- **Structured-output support varies by model/provider.** `build_production_graph` is pinned to `gpt-4o-mini` already; if that model's structured-output mode has edge cases (e.g. refusing to satisfy the schema), that surfaces as a model failure per the existing "Model failure is surfaced, not masked" requirement — no new masking risk, but worth exercising in the test-writing pass.

## Migration Plan

- New Alembic migration adding `sub_category` (nullable) to the product table. No backfill — every existing product simply has no sub-category recorded until the advisor next resolves `lp.listing.007` for it.
- No data migration for in-flight pending results: an `Unsupported` in-flight Slack decision settles exactly as it does today: the outcome side is untouched, and nothing was written to the product. A `Supported` pending result produced by the *old* prose-based code and still awaiting a decision at deploy time is a narrower, accepted gap: a pending result's stored row carries the outcome, the produced text, the handler and the timestamp — never a finding — so if it is later accepted, the step correctly settles `Satisfied` but no `sub_category` is ever recorded for it, and nothing about this change causes that to self-correct (the step is not re-invoked once `Satisfied`). This is a one-time transitional cost, bounded to whatever pending results exist at the exact moment of deploy, and is accepted for the same reason the rejected-decision/provisional-write disagreement above is: reconciling it is out of scope here.
- Rollback: dropping the column and reverting the code is safe — nothing else reads `Product.sub_category` yet.

## Open Questions

- Whether and how the *main* category should ever be captured in commerce-ops is explicitly out of scope here, but is the natural next question once this pattern exists — it doesn't change this change's specs, approach, or tasks, so it's deferred rather than blocking.
