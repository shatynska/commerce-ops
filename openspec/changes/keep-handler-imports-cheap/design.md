## Context

See `proposal.md` — Why. What makes this a design question rather than a tidy-up:

- Registration is an import side effect (`@register_step_handler`, `handler_registry.py:79-88`), and `registrations.py` is the one list that causes those imports in `main.py:69` and `worker.py`. There is no way for a process to read the registry without importing every handler; that is the design, and it is a good one — whoever registers a handler is not whoever decides a step is ready.
- The consequence is that a handler's *import* cost is borne by processes that will never invoke it. Measured locally: the advisor handler alone is 1,988 modules and 0.89s; the four job modules together are 1,110 modules and 0.42s; `check_step_handlers` in total is 0.31s today.
- `subcategory_advisor/application/graph.py` already defers *construction* — `_graph()` is `lru_cache`d, and `handler.py:41-44` says why: "Built on first use, never at import: constructing the model reads credentials, and importing this module must not require them." The reasoning for deferring the import is the same reasoning, one step earlier; it simply was not carried that far.
- `docs/deferred-work.md:204-222` records a start chain that reaches healthy at ~26.5s on the host, a 60s window, one deploy already broken by chain length, and a post-merge measurement still not taken.

## Goals / Non-Goals

**Goals:**

- Importing a handler module registers its name and loads nothing else.
- State that as a requirement, so it does not regress the next time a top-level import is convenient.
- A test that would fail today, so the property is observed rather than asserted.

**Non-Goals:**

- Speeding up the web process. It is unaffected — see Decision 3.
- Changing what the advisor does, how it is tested, or the `build_graph` / `build_production_graph` split that `tests/agents/` depends on.
- Removing any dependency. Everything imported today is still imported; later.
- Applying the rule to `omni_agent`, or to any module that is not a step handler. See Open Questions.

## Decisions

### 1. Defer the imports; do not restructure the module

Four import statements move into the functions that use them, and one annotation moves under `TYPE_CHECKING`. Nothing else changes: not the state schema, not the node, not the two build functions, not `__all__`.

Function-local imports are ordinarily worth avoiding — they hide a dependency from the reader at the top of the file and cost a dict lookup per call. Both objections are answered here. The dependency stays visible because the rule that produced it is written down (Decision 2) and the imports sit in the two functions actually named after building a graph. The per-call cost is irrelevant: `build_production_graph` runs once per process behind an `lru_cache`, and the node's import is a `sys.modules` hit against a model call.

Alternatives considered:

- **A lazy module proxy** (`importlib.util.LazyLoader`, or `__getattr__` at module level). Rejected: it buys the same property with machinery nobody reading the file would expect, and it fails confusingly when the deferred import is broken — at first attribute access, in whatever code touched it.
- **Split the handler from the graph**, registering in a cheap module that imports the expensive one lazily. Rejected: it splits a 200-line module in two to solve a problem four import statements solve, and `group-step-handlers` is separately arguing that this handler does not earn a package.
- **Do nothing, and accept the cost in the start chain.** Rejected: it is the option that leaves `let-the-handler-report-see-handlers` making an unmeasured bet against a chain that has already broken a deploy. It also does not survive the second handler.

### 2. The rule is a requirement, not a comment

A comment in `graph.py` would be read by whoever edits `graph.py`. The property is violated by whoever writes the *next* handler — a different person, in a different file, with a working top-level import and no reason to suspect a rule exists.

So it goes in `launch-step-automation`, as a property of what registration costs, phrased in terms of what a process holds rather than in terms of Python import mechanics. The requirement deliberately does not say "import at function scope": that is one way to satisfy it, and a future handler might satisfy it differently.

The test is written at the level the requirement is stated: import the handler module in a fresh interpreter, assert the model client is absent from `sys.modules`. That is a process-level observation, and it is the only level at which this property is observable at all — within one interpreter, another test may already have imported LangGraph.

### 3. This does not make the web process faster, and the proposal says so

It would be easy to claim the deploy-time win here, and it would be wrong. `main.py` pulls LangGraph by two independent paths: the omni_agent Slack router (`main.py:34` → `omni_agent/infrastructure/driving/slack.py`) and the advisor handler via `registrations`. Closing one leaves the other, and `import commerce_ops.main` will cost what it costs today.

Where this change is load-bearing is the process that imports `registrations` **without** mounting any router — which today means `check_step_handlers` after `let-the-handler-report-see-handlers`, and tomorrow means any process that wants to read the registry cheaply.

The omni_agent half is the one with the deploy payoff, and it is deliberately not folded in: it is a different module, a different graph, and a hypothesis (`deferred-work.md:216`) that deserves measuring rather than assuming. See Open Questions.

## Risks / Trade-offs

- **The property regresses silently.** A future edit adds `from langchain_openai import ChatOpenAI` at the top of a handler and nothing visibly breaks. → The test in Decision 2 is the guard, and it fails loudly. It is the deliverable; the import move without it is worth little.
- **The test is fragile in the wrong direction.** It asserts a module is *absent* from `sys.modules`, which is a negative and depends on running in a fresh interpreter. → Mitigated by using the subprocess pattern `tests/unit/test_registrations_across_processes.py` already establishes for exactly this class of property, rather than inventing one.
- **Function-local imports read as a code smell to a reviewer who does not know why.** → Mitigated by the requirement and by a comment at each site pointing to it. Accepted: the alternative is a lazy-loading mechanism that reads worse.
- **A handler author reads the rule as "defer everything".** Deferring a cheap import buys nothing and costs clarity. → The requirement is scoped to "the resources the handler uses when it runs", not to imports in general.

## Migration Plan

A source change in one pull request: four import statements, one `TYPE_CHECKING` block, one test, one spec delta. No dependency change, no configuration, no schema, no `Dockerfile`.

Rollback is a revert; nothing outside the repository is affected, and no deployed behaviour changes in either direction.

Sequencing: land **before** `let-the-handler-report-see-handlers`, whose Decision 2 assumes it. Against `group-step-handlers` the order is free — both edit this file, and this is the smaller diff, so landing it first is marginally kinder to the other.

## Open Questions

- **Does `omni_agent`'s graph carry the same rule, and would deferring it measurably shorten the host's start chain?** `main.py:34` imports the omni_agent Slack router, which pulls LangGraph before uvicorn can serve, and `deferred-work.md:216` names precisely this as the unverified hypothesis for the host's 14× factor. Answering it needs a host measurement, not a local one, and the answer changes nothing about this change — which is why it is recorded here rather than resolved. If the answer is yes, the requirement added here is the natural thing to generalise.
