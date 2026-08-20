<!-- ai-toolkit:project-foundation -->

## What it is

commerce-ops is internal ops tooling for a company that sells products through online marketplaces.

## Problem

It consolidates and automates currently manual, fragmented marketplace-operations workflows.

## Audience

The company's internal operations/support team.

## Scope

Initial scope covers four domains, AI-assisted where noted:

- AI-assisted listing/catalog management — agents that help create, optimize, and manage product listings.
- Order & inventory sync across marketplaces — centralizing order and stock data across marketplace accounts.
- AI customer support / messaging automation — agents that handle or assist with customer inquiries, reviews, messages.
- Analytics & reporting — cross-marketplace performance dashboards and insight generation.

Marketplace integration: Amazon is the first concrete marketplace integration; the integration layer is designed to be marketplace-agnostic/extensible for marketplaces beyond Amazon.

Slack integration: Slack is an initial-scope interaction channel, used both ways — the ops team converses directly with the domain agents in Slack (asks questions, gives instructions, gets answers), and the system pushes notifications and approval requests (e.g. "approve this listing change?") there. It stands alongside the FastAPI HTTP API as a primary interface, not a secondary notification-only add-on.

## Non-Goals

- No customer-facing product — stays an internal tool; no external/customer-facing UI or app in this phase.
- No own storefront/checkout — not building a direct-to-consumer storefront; marketplaces remain the sales channel.
- No mobile app — interaction happens via web/API and Slack for now, no native mobile client.

## Technology

Python, FastAPI (HTTP API layer), LangGraph (AI agent orchestration) — supplied directly by the project owner, not proposed. Slack Bolt / Slack Web API SDK is added as the Slack interface's technology, consistent with the owner's direction to make Slack an active interaction channel. Postgres is the shared relational datastore backing each module's repositories (named in Architecture below).

## Architecture

Modular monolith: one FastAPI app organized into domain modules (catalog, orders/inventory, support, analytics) as DDD bounded contexts — each with its own name space, model, and ubiquitous language, boundaries kept clear even though they share one deployable and one Postgres database.

Each module follows a lightweight ports-and-adapters shape so the domain layer stays explicit without mandating full tactical DDD everywhere:
- **Domain layer** (center): entities, value objects, and domain services expressed in that module's own language — no framework or I/O dependencies.
- **Application layer**: use cases and orchestration, including the module's LangGraph agent graphs, calling into the domain layer.
- **Infrastructure layer** (edges): "driving" adapters that call into the application layer — the FastAPI HTTP routes and the Slack adapter (conversational + notifications/approvals) — and "driven" adapters the application layer calls out to — the marketplace-adapter layer (Amazon first, built to an adapter interface so future marketplaces can be added without reworking the domain modules) and Postgres repositories. Slack is one shared app/entry point (a single Slack Bolt process) that dispatches each incoming event to the relevant module's application layer, rather than a separate adapter instantiated per module — the same relationship the single FastAPI app already has to its per-module routes.

Aggregates, repositories-as-interfaces, and domain events are adopted per module only once that module's logic actually needs them (e.g. an aggregate to enforce an invariant, a domain event to decouple two modules) — not mandated across every module from day one. The explicit domain/application/infrastructure split is the one DDD commitment that applies everywhere; the heavier tactical patterns are opt-in per module.

Chosen over microservices-from-the-start to avoid premature distributed-systems complexity for a single team, while keeping domains separable behind clear module and layer boundaries if any of them later need to split out.

<!-- /ai-toolkit:project-foundation -->
