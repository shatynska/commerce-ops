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

- **The repository** owns the playbook *definition*: the gate sequence, the step definitions, and which step belongs to which gate, authored as versioned YAML (per `launch-playbook`'s "Playbooks are versioned") and loaded by `playbook_loader.py`.
- **Postgres** owns each product's *position* in that playbook and its per-step completion state — per-product, mutable, and with no business in a versioned definition file.
- **ClickUp** owns *human completion*. The ops team marks work done where they already work, and ClickUp reports completion back so gate-opening logic can evaluate against it.

Making Postgres the sole owner of completion would require the team to stop completing work where they complete it — a process change imposed by an implementation detail. Making ClickUp the owner of structure would require gate sequencing, blocking-step rules and timing anchors to be expressed in ClickUp's data model, which cannot express them: `launch_playbook.py` already encodes coherence rules (a `prohibited-tactic` step can never block a gate; an `automated` step must carry a rule policy) that no task tracker enforces.

The split carries one obligation: webhook delivery is not guaranteed, so completion state in Postgres can silently drift from ClickUp. That needs a periodic reconciliation pass — a known, bounded problem, named here so whatever implements the synchronization inherits it rather than discovering it.

### Module boundaries

Each module's `application/__init__.py` is the only surface another module may import — a `__all__` re-export of that module's public use cases; nothing outside a module imports its `domain`, `infrastructure`, or an unlisted `application` internal directly, enforced by `import-linter` rather than left to convention alone. `shared` is the one exception, and a narrow one: it's a Shared Kernel, not a peer bounded context, so a module's own layer may reach the same-or-lower corresponding layer within `shared` (`domain` → `shared.domain`; `application` → `shared.domain`/`shared.application`; `infrastructure` → all three of `shared`'s layers) — but `shared` itself never imports a business module, regardless of which of `shared`'s own layers is asking.

For a genuine, stable cross-module business dependency, the default is a direct import of the producer's `application` public surface; escalate to a consumer-owned `Protocol` port only when the dependency needs mocking in tests or a real circularity risk exists — not mandated for every dependency, matching the incremental tactical-pattern adoption above. A module may nest one level (`<module>/<child>/{domain,application,infrastructure}`) for an internal sub-capability; the child's surface stays visible only to its siblings and to the parent's own `application/__init__.py`, never directly from outside the parent — a second level of nesting is a signal the concept belongs as a sibling top-level module instead.

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

`tests/integration/products/` (and any future integration test touching Postgres) needs a real database. Bring up the same `postgres` service `docker-compose.yml` deploys, standalone:

```
POSTGRES_PASSWORD=local-dev docker compose up postgres -d
```

Then point `DATABASE_URL` at it and apply migrations before running the integration tier:

```
export DATABASE_URL=postgresql+asyncpg://commerce_ops:local-dev@localhost:5432/commerce_ops
uv run alembic upgrade head
uv run pytest tests/integration
```

Without `DATABASE_URL` set, `tests/integration/products/` skips rather than failing.
