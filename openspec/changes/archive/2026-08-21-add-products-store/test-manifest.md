# Test manifest — `add-products-store`

Written by `openspec-test-writer`, strictly before implementation. This file
is **not** part of the OpenSpec schema and will not appear among
`openspec instructions apply`'s context files — it must be read on purpose
before implementing this change. (See also the `ai-toolkit` `rules/`
fragment that directs it be read before implementation; that import path is
machine-local, so this manifest and the report accompanying it are the
reachable pointers to this document from wherever it's checked out.)

This is a **first pass**: `add-products-store` had no prior
`test-manifest.md`, so nothing here is a merge.

## Baseline

Full suite, before any file in this pass was written:

```
uv run pytest -q
80 passed in 1.87s
```

After adding `tests/integration/products/{__init__.py,conftest.py,test_product_repository.py}`:

```
uv run pytest -q --ignore=tests/integration/products
80 passed in 1.77s     # unchanged — nothing pre-existing was touched or broken

uv run pytest -q
ModuleNotFoundError: No module named
'commerce_ops.products.infrastructure.driven.product_repository'
(collection error, tests/integration/products)
```

The collection error is the **expected outcome**: this change is this
project's first-ever persistence layer (no DB driver, ORM model,
repository, or Alembic setup exists yet — see `proposal.md`'s Impact
section and `tasks.md` sections 1–3, none of which are implemented). Per
`ai-toolkit:testing`'s failure-state taxonomy, this establishes only that
the target is absent, nothing about whether the scenarios below are
well-formed. `ruff check` and `ruff format --check` both pass clean on the
new files; `mypy` reports the same absent-target imports
(`import-not-found` / `import-untyped`) and nothing else.

## Scenario accounting — `launch-instance` (ADDED capability, 10 scenarios)

All ten scenarios covered by new tests in
`tests/integration/products/test_product_repository.py`.

### Requirement: A product is persisted with its catalog identity

| Scenario | Test |
|---|---|
| A product is created with only the required fields | `test_creating_with_only_required_fields_persists_absent_optionals` |
| A product is created with every field | `test_creating_with_every_field_persists_all_five_values` |
| A duplicate SKU is rejected | `test_creating_with_a_duplicate_sku_is_rejected` |

### Requirement: A product's current gate is restricted to the launch-playbook gate sequence

| Scenario | Test |
|---|---|
| A new product defaults to the first gate | `test_a_new_product_defaults_to_the_first_gate` |
| An unrecognized gate is rejected | `test_creating_with_an_unrecognized_gate_is_rejected` (create half) **and** `test_updating_to_an_unrecognized_gate_is_rejected` (update half) — the scenario's WHEN covers both "created or updated"; both halves are tested since the THEN clause ("stored gate is unchanged") reads differently for each |

Extra, **not** a named scenario (DERIVED, recorded so it isn't mistaken for
one of the ten): `test_creating_with_each_of_the_eight_gate_ids_is_accepted`
— parametrized over all eight gate ids, checking the requirement's stated
bound ("one of the eight ... gate ids") in full rather than only via the
default and the one rejected case the two named scenarios exercise.

### Requirement: A product can be read back by identifier or by SKU

| Scenario | Test |
|---|---|
| A product is retrieved by its identifier | `test_a_product_is_retrieved_by_its_identifier` |
| A product is retrieved by its SKU | `test_a_product_is_retrieved_by_its_sku` |
| Reading an unknown product reports absence | `test_reading_an_unknown_product_reports_absence[by-unknown-identifier]` **and** `test_reading_an_unknown_product_reports_absence[by-unknown-sku]` |

### Requirement: A product's current gate can be updated

| Scenario | Test |
|---|---|
| A product's current gate is updated to a valid gate | `test_updating_current_gate_to_a_valid_gate_persists_the_change` |
| Updating a nonexistent product is rejected | `test_updating_a_nonexistent_product_is_rejected` |

## Scenario accounting — `deploy-pipeline` (MODIFIED capability, 2 new ADDED requirements, 4 scenarios)

All four scenarios are recorded **uncovered**, not tested by any new file.
Reasoning below; flagged as a judgment call for human confirmation (see
"Unresolved project questions" #6).

| Scenario | Status | Reason |
|---|---|---|
| Postgres data survives a redeploy | Uncovered | Requires actually running `docker compose pull \|\| up -d` twice against a live stack and observing volume persistence across the cycle — genuine Docker/orchestration behavior, not observable via static config parsing, and not practical as a fast/deterministic `pytest` test in this project's existing tiers (`tests/unit`, `tests/agents`, `tests/integration` — the last means "touches real I/O such as Postgres via the app's own DB layer," not "orchestrates a Compose stack lifecycle"). |
| Postgres is unreachable from the public-facing network | Uncovered | See "Unresolved project questions" #6 — this one *is* mechanically checkable via static YAML parsing (no Docker needed), but is left uncovered to follow this capability's established, if implicit, convention (below). |
| App does not start before Postgres is healthy | Uncovered | Runtime behavior of Docker Compose's own `depends_on: condition: service_healthy` engine feature; only the static declaration that produces it is inspectable without running Compose, and see #6 below for why even that isn't added here. |
| App serves no traffic until migrations complete | Uncovered | Container startup-ordering behavior (`alembic upgrade head` before `uvicorn`); only the static Dockerfile `CMD`/entrypoint structure is inspectable without actually starting the container, and see #6 below. |

**Why no pytest coverage was added for this capability at all:** every one
of `deploy-pipeline`'s five pre-existing requirements (`openspec/specs/deploy-pipeline/spec.md`)
— including "Serialized Deploys", whose entire content is a two-line
`concurrency:` block already present, verbatim, in the current
`docker-compose.yml`/`deploy.yml` — has **zero** `pytest` coverage anywhere
in this repository. That is direct, checked-in evidence of an established
(if unstated) project convention: this capability's requirements, even the
trivially statically-parseable ones, are not given `pytest` tests here.
Introducing static-YAML-parsing tests for this change's two new
requirements alone, with no such test existing for any of the other five,
would invent a testing convention for this capability that the project has
not adopted anywhere else — rather than silently doing that, it's recorded
here as an explicit, flagged judgment call. See "Unresolved project
questions" #6.

**Scenario count check:** 10 covered (launch-instance) + 4 uncovered
(deploy-pipeline) = 14 delta scenarios, all accounted for.

## Assertion classification

- **Specified** assertions (traced to the delta spec's scenario or
  requirement text) are marked `# SPECIFIED: ...` inline, next to the
  assertion, throughout `test_product_repository.py`.
- **Derived** assertions (inferred, no scenario states them directly) are
  marked `# DERIVED: ...` inline, with the reasoning for the inference —
  e.g. the create-half of "An unrecognized gate is rejected" (no prior
  stored gate exists to stay "unchanged," so absence-of-a-new-record is
  read as the create-side counterpart), and the choice to read the same
  independent-session pattern for durability across all "read back" tests.
- **Deliberately untested** cases are listed at the bottom of
  `test_product_repository.py` with reasons: `created_at`/`updated_at`
  (implementation columns `design.md` adds but the spec's persisted-fields
  requirement never names), the exact type/hierarchy of the invented
  rejection exception, and gate-transition validation (`design.md`
  Non-Goals, explicitly out of scope for this change).

## Obsolete tests

**Not applicable.** Neither delta spec in this change carries a `MODIFIED`,
`REMOVED`, or `RENAMED` requirement operation:

- `specs/launch-instance/spec.md` is entirely `## ADDED Requirements` (a new
  capability — nothing to supersede).
- `specs/deploy-pipeline/spec.md` is also entirely `## ADDED Requirements`.
  Although `proposal.md`'s "Capabilities" section lists `deploy-pipeline` as
  a **Modified Capability**, that labels the capability, not the delta
  operation on any individual requirement. Both of its two new requirements
  ("Compose File Provisions a Persistent, Network-Isolated Postgres
  Service" and "Application Migrates the Database Before Serving Traffic")
  were diffed by title and text against every requirement in
  `openspec/specs/deploy-pipeline/spec.md` (the five existing requirements:
  Pull Request Validation Gate, Merge to Main Builds and Publishes an
  Image, Deploy Reaches the Host Over a Private Tailnet, Deploy Delivers
  the Compose File and Triggers the Host-Side Deploy Script, Deploy Is
  Verified by Checking the Health Endpoint, Serialized Deploys) — neither
  new requirement's text overlaps with or supersedes any existing one; both
  are wholly new. No test anywhere in the dispatched glob (`tests/**/test_*.py`)
  bears on either capability's prior behavior in a way any delta here
  supersedes.

Since no `MODIFIED`/`REMOVED`/`RENAMED` operation exists, the bounded
obsolete-test search (within `tests/**/test_*.py`) was not performed — there
is nothing for it to be a search *for*.

## Unresolved project questions

None of these are answered by `AGENTS.md`/`CLAUDE.md` or by any other
convention file dispatched for this pass. Each records the assumption taken
and which tests depend on it.

1. **Async test plugin.** No convention names `pytest-asyncio` vs. `anyio`'s
   pytest plugin (or any other). Assumption: use `anyio`'s plugin (already
   an installed transitive dependency, auto-registered under `pytest11`;
   confirmed live via `importlib.metadata.entry_points(group="pytest11")`),
   pinned to the `asyncio` backend only via a local `anyio_backend` fixture
   in `conftest.py` (no `trio` dependency is installed). Depends on this:
   every async test in `tests/integration/products/` (all are marked
   `pytestmark = pytest.mark.anyio`).
2. **`DATABASE_URL`'s scheme.** `tasks.md` 1.2/4.1 only say it's read from
   the environment, not what scheme it carries (e.g. whether it already
   includes `+asyncpg`). Assumption: passed through unchanged to
   `create_async_engine`. Depends on this: the `engine` fixture, and
   therefore every test in the directory.
3. **`ProductRepository`'s constructor and transaction ownership.** No
   artifact fixes this. Assumption: `ProductRepository(session: AsyncSession)`,
   each method (`create`, `get_by_id`, `get_by_sku`, `update_current_gate`)
   committing its own work — grounded in `design.md`'s statement that this
   change "does not yet add a use case that calls it, since none is needed
   to exercise the store directly via integration tests," read as meaning
   the repository is usable standalone. Depends on this: every test in
   `test_product_repository.py`, via the `repository`/`new_repository`
   fixtures.
4. **Rejection-signaling mechanism.** The delta spec says an operation "is
   rejected" three times, never specifying how (exception, `None`, a result
   type). Assumption: a single invented `ProductRepositoryError`, raised
   for all three rejection causes — chosen over three invented subtypes
   because the spec treats the causes identically, and because this
   project's domain layer already has precedent for one named exception per
   rejected-operation family
   (`products/domain/launch_playbook.py`'s `InvalidPlaybookError`).
   Depends on this: `test_creating_with_a_duplicate_sku_is_rejected`,
   `test_creating_with_an_unrecognized_gate_is_rejected`,
   `test_updating_to_an_unrecognized_gate_is_rejected`,
   `test_updating_a_nonexistent_product_is_rejected`.
5. **Test-database lifecycle.** No artifact says whether
   `tests/integration/products/` should run against a
   transactionally-rolled-back-per-test database, a truncate fixture, or an
   ephemeral container recreated per run. Assumption: no such fixture is
   added; each test generates its own unique SKU
   (`conftest.unique_sku()`) and only reads back records it created itself,
   so correctness doesn't depend on the database starting empty. Flagged:
   this means repeated local runs against a persistent Postgres will
   accumulate rows over time — worth a human decision (e.g. a
   truncate-between-tests fixture, or a disposable test database) once the
   implementation exists, not invented here. Depends on this: every test in
   the directory.
6. **Whether `deploy-pipeline`'s two new requirements get any `pytest`
   coverage at all.** See the "Scenario accounting — `deploy-pipeline`"
   section above for the full reasoning. Assumption taken: no, following
   this capability's established zero-pytest-coverage precedent across all
   five of its pre-existing requirements. This is the one judgment call in
   this pass most likely worth a human overriding — in particular, the
   network-isolation scenario ("Postgres is unreachable from the
   public-facing network") is straightforwardly checkable via a static
   parse of `docker-compose.yml` with no Docker involved, and a reviewer
   may prefer that be added as this capability's first such test rather
   than left to follow precedent. Depends on this: all four
   `deploy-pipeline` scenarios being recorded uncovered rather than tested.

## Files this pass added

- `tests/integration/products/__init__.py`
- `tests/integration/products/conftest.py`
- `tests/integration/products/test_product_repository.py`
- `openspec/changes/add-products-store/test-manifest.md` (this file)

No existing test file was edited, deleted, or disabled.
`tests/integration/test_placeholder.py` (whose own docstring says "Delete
once real integration tests exist") was **not** deleted — the additive-only
rule binds regardless of what a file's own docstring invites; removing it is
left for whoever implements next, or a later pass, not this one.
