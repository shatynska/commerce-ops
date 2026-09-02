<!-- ai-toolkit:project-foundation -->

## What it is

commerce-ops is internal ops tooling for a company that sells products through online marketplaces.

## Problem

It consolidates and automates currently manual, fragmented marketplace-operations workflows.

## Audience

The company's internal operations/support team.

## Scope

**Product Launch is the MVP subdomain and the first deliverable.** Taking a new product from "worth developing" through to a live, ranking listing — a gated sequence of launch work, driven from Slack and tracked in ClickUp. It is first because it is the one subdomain that can be built to completion with the integrations available today, while marketplace access is being obtained externally.

Launch is not one of the four domains below and does not replace one; it cuts across listing/catalog management and analytics. Those four remain the surrounding scope, sequenced behind it:

- AI-assisted listing/catalog management — agents that help create, optimize, and manage product listings.
- Order & inventory sync across marketplaces — centralizing order and stock data across marketplace accounts.
- AI customer support / messaging automation — agents that handle or assist with customer inquiries, reviews, messages.
- Analytics & reporting — cross-marketplace performance dashboards and insight generation.

Further subdomains — customer support among them — follow after, and are not yet specified in any detail. The module structure already accommodates them as sibling bounded contexts, so this ordering constrains nothing about them.

Marketplace integration: Amazon is the first concrete marketplace integration; the integration layer is designed to be marketplace-agnostic/extensible for marketplaces beyond Amazon. **This is deferred, not descoped.** Marketplace access is being obtained externally and is not available to build against, so no marketplace adapter is built and no change is sequenced as depending on one until it is granted. Everything in the scope above that reads marketplace data — the analytics, order-sync and monitoring work in particular — is blocked behind that, which is why Launch comes first.

Slack integration: Slack is an initial-scope interaction channel, used both ways — the ops team converses directly with the domain agents in Slack (asks questions, gives instructions, gets answers), and the system pushes notifications and approval requests (e.g. "approve this listing change?") there. It stands alongside the FastAPI HTTP API as a primary interface, not a secondary notification-only add-on.

## Non-Goals

- No customer-facing product — stays an internal tool; no external/customer-facing UI or app in this phase.
- No own storefront/checkout — not building a direct-to-consumer storefront; marketplaces remain the sales channel.
- No mobile app — interaction happens via web/API and Slack for now, no native mobile client.

## Technology

Python, FastAPI (HTTP API layer), LangGraph (AI agent orchestration) — supplied directly by the project owner, not proposed. Slack Bolt / Slack Web API SDK is added as the Slack interface's technology, consistent with the owner's direction to make Slack an active interaction channel. Postgres is the shared relational datastore backing each module's repositories (see Architecture below). `pydantic-settings` declares the runtime's configuration in one place, checked at container start before the migration runs.

**LangGraph's scope is narrowed to where a language model is genuinely required**: interpretation, generation, and conversation. It is not the default unit of work. Most of the Launch subdomain's logic is deterministic — a gate opens when its blocking steps are done, a step becomes due at a fixed offset from the launch date, and `launch_playbook.py` already enforces its own coherence rules as ordinary domain code. Routing that through a language model would make it slower, costlier and non-reproducible for logic that is none of those things.

## Architecture

Modular monolith: one FastAPI app organized into domain modules as DDD bounded contexts — each with its own name space, model, and ubiquitous language, boundaries kept clear even though they share one deployable and one Postgres database. Module boundaries are established incrementally as domain work actually begins, not fixed upfront from the initial product scope above.

Each module follows a lightweight ports-and-adapters shape so the domain layer stays explicit without mandating full tactical DDD everywhere:
- **Domain layer** (center): entities, value objects, and domain services expressed in that module's own language — no framework or I/O dependencies.
- **Application layer**: use cases and orchestration, including the module's LangGraph agent graphs, calling into the domain layer.
- **Infrastructure layer** (edges): "driving" adapters that call into the application layer — the FastAPI HTTP routes and the Slack adapter (conversational + notifications/approvals) — and "driven" adapters the application layer calls out to — the marketplace-adapter layer (Amazon first, built to an adapter interface so future marketplaces can be added without reworking the domain modules) and Postgres repositories. Each module owns its own driving adapters — including its own Slack event route and credentials — in its own `infrastructure/driving` layer; `main.py` is the single composition root wiring every module's driving adapters, FastAPI routes and Slack alike, into one shared app and one shared deployable, the same relationship it already has with per-module HTTP routes.

Aggregates, repositories-as-interfaces, and domain events are adopted per module only once that module's logic actually needs them (e.g. an aggregate to enforce an invariant, a domain event to decouple two modules) — not mandated across every module from day one. The explicit domain/application/infrastructure split is the one DDD commitment that applies everywhere; the heavier tactical patterns are opt-in per module.

### Launch state ownership

Launch state is owned three ways, and the split is deliberate — neither system can do the other's job:

- **The repository** owns the playbook *framework*: the gate sequence, the opening modes, the authored metric conditions, and every coherence rule, as code in `launch_playbook.py`. The *step definitions* moved to Postgres as a live set (`move-playbook-steps-to-postgres`, 2026-08): seeded once from the authored YAML, then edited only through the `playbook-authoring` write use cases, each write validated as the whole playbook it would produce — so the database can hold nothing the repository's rulebook would reject. A launch records the served version identifier as an audit stamp; no read branches on it.

  A step declares a **name** (one line, what a person scans in a list of work) and an optional multi-line **description**, the gate it precedes, its discipline, scope, timing anchor and blocking flag, its **assignees** (roster people, by identifier), its **kind** — `human` or `automated` — and, separately, whether the result **needs confirmation** by a person, plus a lifecycle **status**: `draft`, `in-development`, `active` or `retired`. Only `active` steps are served to a launch, hold a gate, or reach ClickUp; the rest are visible to authors alone, which is what lets work be written down before it is ready. An `automated` step carries an **automation brief** (owed once it leaves `draft`) and a **handler** naming the use case that resolves it (owed to become `active`) (`redesign-step-fields`, 2026-08). Registering a handler makes its name resolvable and loads nothing the handler needs in order to run: every process that consults the registry registers every handler in order to consult it at all, so a handler's model client, graph or HTTP session is obtained when it resolves a step, never when it is registered (`keep-handler-imports-cheap`, 2026-08).
- **Postgres** also owns each product's *position* in that playbook and its per-step completion state — per-product and mutable, like the step set itself.
- **ClickUp** owns *human completion*. The ops team marks work done where they already work, and ClickUp reports completion back so gate-opening logic can evaluate against it.

Making Postgres the sole owner of completion would require the team to stop completing work where they complete it — a process change imposed by an implementation detail. Making ClickUp the owner of structure would require gate sequencing, blocking-step rules and timing anchors to be expressed in ClickUp's data model, which cannot express them: `launch_playbook.py` already encodes coherence rules (a `prohibited-tactic` step can never block a gate; an `automated` step past `draft` must carry an automation brief, and one that is `active` must name a handler) that no task tracker enforces.

The split carries one obligation: webhook delivery is not guaranteed, so completion state in Postgres can silently drift from ClickUp. That needs a periodic reconciliation pass — a known, bounded problem, named here so whatever implements the synchronization inherits it rather than discovering it.

### Module boundaries

Each module's `application/__init__.py` is the only surface another module may import — a `__all__` re-export of that module's public use cases; nothing outside a module imports its `domain`, `infrastructure`, or an unlisted `application` internal directly, enforced by `import-linter` rather than left to convention alone. `shared` is the one exception, and a narrow one: it's a Shared Kernel, not a peer bounded context, so a module's own layer may reach the same-or-lower corresponding layer within `shared` (`domain` → `shared.domain`; `application` → `shared.domain`/`shared.application`; `infrastructure` → all three of `shared`'s layers) — but `shared` itself never imports a business module, regardless of which of `shared`'s own layers is asking.

For a genuine, stable cross-module business dependency, the default is a direct import of the producer's `application` public surface; escalate to a consumer-owned `Protocol` port only when the dependency needs mocking in tests or a real circularity risk exists — not mandated for every dependency, matching the incremental tactical-pattern adoption above. A module may nest one level (`<module>/<child>/{domain,application,infrastructure}`) for an internal sub-capability; the child's surface stays visible only to its siblings and to the parent's own `application/__init__.py`, never directly from outside the parent — a second level of nesting is a signal the concept belongs as a sibling top-level module instead.

`step_handlers/` is the third kind of top-level package, after the bounded contexts and `shared`, and the one-level-nesting rule above does not reach into it. That rule is about bounded contexts: a second level of nesting inside one signals a concept that wants promoting to a sibling. `step_handlers` is not a bounded context — it has no model, no ubiquitous language and no invariants of its own. It is a container of adapters into `launch`'s automation port, holding every step handler the deployment answers for, grouped by the discipline its registered name starts with, so `listing.subcategory_advisor` reads as `step_handlers/listing/subcategory_advisor`. That grouping is a convention and deliberately not enforced: the registry keys on a free string, and validating that a handler's location, its name's first segment and the discipline of the steps naming it all agree would couple a code path to a domain enum and make a file move a data migration. A handler that grows a real model and its own invariants is a bounded context wearing a handler's clothes, and *that* is the signal to promote it — the original rule, applied to the right unit.

Handlers sit here rather than inside `launch/application` because that placement would not grant what it appears to. A handler inside `launch.application` still cannot import `launch/infrastructure` — the layers contract forbids it — while it *would* gain reach into `launch.domain`, `catalog.application` and `access.application`, which is exactly the reach the handler contract exists to deny; a handler that read the catalog itself would defeat the rule that has the automation pass resolve the product once and hand it over. What a handler needs from outside it already has: the product is injected into its context by the pass, settings are application-layer and importable anywhere, and an external API client is a library dependency. Where one ever needs a real project-side collaborator, the sanctioned path is module-level injection at the composition root, the way `worker.py` supplies every other collaborator — not an import, and not a layer.

A handler's internal shape is free: a module until it earns being a package, and a package until it earns layers. Python resolves `foo.py` and `foo/__init__.py` behind an identical import statement, so growing a handler from a file into a package is invisible to `registrations.py`, to `.importlinter` and to the registry. The one obligation that freedom carries: **a handler that is a package re-exports its registration from `__init__.py`**, because `@register_step_handler` only runs if the module holding it is imported. Omit it and the package imports cleanly with the handler simply absent from the registry — the same asymmetric failure `registrations.py` documents for job modules, one level down. (And a shape change is a move, never a copy: where `foo.py` and `foo/` both exist, the package wins silently.)

`omni_agent` is the stated direction for a future cross-module coordinator — a process-manager/saga role sequencing peer modules through their own public APIs, not a peer module itself — though its current slice (a single Slack Q&A graph) is far from that yet. Peer domain modules never call each other directly for orchestration purposes; only for the narrow, stable business dependency described above.

Chosen over microservices-from-the-start to avoid premature distributed-systems complexity for a single team, while keeping domains separable behind clear module and layer boundaries if any of them later need to split out.

<!-- /ai-toolkit:project-foundation -->

## Setup

```
uv sync
uv run pre-commit install                     # installs the pre-commit and commit-msg hooks (ruff, mypy, unit/agent tests, gitlint)
uv run pre-commit install --hook-type pre-push  # installs the pre-push hook (integration tests)
```

Both install commands are required — the first covers commit-time checks, the second covers the separate pre-push integration-test gate.

## Local Postgres

`tests/integration/` needs a real database. Bring up the same `postgres` service `docker-compose.yml` deploys, standalone:

```
POSTGRES_PASSWORD=local-dev docker compose up postgres -d
```

Apply the migrations once, then run the tier — no `export` needed, because `tests/integration/conftest.py` finds the database itself:

```
uv run alembic upgrade head
uv run pytest tests/integration
```

It looks in three places, in order: the `DATABASE_URL` environment variable, then `.env.test`, then `.env`. An explicit variable always wins, so exporting one still overrides everything below it.

**Reading the tier against your own database?** It writes `mg.*` steps into whatever database it finds, and `test_playbook_seed.py` asserts a "before any authored edit" premise that a hand-edit through the admin UI would break. To keep it out of the database you work in, create a `.env.test` holding a `DATABASE_URL` and nothing else:

```
createdb commerce_ops_test          # once
export DATABASE_URL=postgresql+asyncpg://commerce_ops:local-dev@localhost:5432/commerce_ops_test
uv run alembic upgrade head                      # once — the schema
uv run python -m commerce_ops.seed_playbook      # once — and the seed
echo "DATABASE_URL=$DATABASE_URL" > .env.test
```

**Both commands, not just the first.** The migration writes the rows it always
did; the rest of the step set comes from `seed_playbook`, which every container
runs on start (see the `Dockerfile`'s CMD chain) and which no migration performs.
A database carrying only the schema fails four tests, and they say so in their own
assertion messages.

**The name's `_test` must come last.** Two modules rewrite the stored step set and
refuse any database whose name does not end `_test`, so `commerce_ops_x_test` runs
them and `commerce_ops_test_x` does not. It is a suffix check, not the literal name
`commerce_ops_test` — and a worktree wanting its own database should use the suffix
rather than share this one, since the tier writes freely and two sessions against
one database produce failures that read as defects.

`.gitignore` already covers `.env.*`. Only `DATABASE_URL` is read from either file — never the Slack, OpenAI or ClickUp values beside it, because every test that needs one sets its own, and inheriting an ambient credential would let a test that forgot pass anyway.

With no database configured anywhere, tests needing one skip and say so. **With `.env` present and Postgres stopped they fail instead**, because a URL resolves and the connection does not — so `pre-push` now needs the service running, not merely configured. That is a change: this section used to promise a skip in that case. The skip survives only where nothing is configured at all.

Note the pre-push hook exists only if you ran the second install command above; without it, none of this runs before a push. CI runs the tier unconditionally against its own Postgres, where an absent or unreachable database fails the job rather than skipping.

Once the database *is* reachable, the roster needs a first admin. In a deployed container this happens on its own: the start chain runs `preflight`, then `alembic upgrade head`, then the seeding step, then the server, and the step makes the Slack identity `BOOTSTRAP_ADMIN_IDENTITY` names an active admin. If the roster has no admin and the variable is unset, that step fails and the server never starts — a deployment nobody can administer stops at a named step rather than crash-looping.

Running `uvicorn` directly skips that chain, so a fresh local database has no admin until you run the step yourself — the same shape as needing `alembic upgrade head`:

```
export BOOTSTRAP_ADMIN_IDENTITY=U078TC45LHM
uv run python -m commerce_ops.seed_admin
```

It is inert once the roster holds an admin of its own. The integration tier needs the variable for the same reason a deployment does.

## Deferred work

`docs/deferred-work.md` records what this project has deliberately not done, and why — decisions awaiting a team call, items belonging to the `/infrastructure` repository, and technical work postponed with its reasoning.

Each entry points at the change artifacts that argue it rather than repeating them. It exists because a deferral recorded only inside a change moves to `openspec/changes/archive/` when that change ships, and stops being findable.
