## Why

The `tests/integration` tier is verified nowhere automatically. It holds
67 tests over real Postgres, and all three places that could run them
let them pass without running:

- **CI** (`.github/workflows/ci.yml`) runs `ruff`, `ruff format`, `mypy`,
  `lint-imports` and `pytest tests/unit tests/agents`. There is no
  integration step and no Postgres service.
- **The `pre-push` hook** runs `pytest tests/integration`, but every test
  in the tier calls `pytest.skip()` when `DATABASE_URL` is unset — and
  the hook does not set it.
- **Locally**, the same skip fires, so a session that does not happen to
  export the variable sees `67 skipped` and a zero exit status.

pytest exits `0` on a skip by design, and rightly: a skip means the test
does not apply here, which is true for a contributor with no Postgres.
But a missing environment variable on a machine where the database is
running and `.env` already names it is a misconfiguration wearing a
skip's clothing, and it reports as success. This was observed, not
theorised: a `pre-push` run in this repository reported `3 passed, 64
skipped` and was taken for a passing tier until the variable was
exported by hand, after which the same command reported `67 passed`.

Underneath it, the skip is copy-pasted. Twelve integration test files
carry the same `_database_url()` helper — identical bodies, with skip
messages that differ only in naming each subtree's migration — and
`tests/integration/` has no `conftest.py` at all, so the rule that
decides whether the tier runs exists in twelve places and is owned by
none.

## What Changes

- One `tests/integration/conftest.py` owns how the tier reaches its
  database: the `DATABASE_URL` environment variable, then `.env.test`,
  then `.env` — reading **only that key** from either file. The twelve
  duplicated helpers are replaced by it.
- `.env.test` lets the tier run against a database of its own rather
  than the one the developer works in. It is optional: absent, the tier
  falls back to `.env` exactly as before, so the file costs nothing
  until someone wants the isolation.
- Where the tier is *required* — CI — an absent or unreachable database
  becomes a **failure**, not a skip, so the gate can no longer report
  success without having run.
- `pre-push` is deliberately **not** made required, but its behaviour
  changes anyway — for anyone who installed that hook; a plain
  `pre-commit install` does not, since `default_install_hook_types`
  omits it. That change is intended rather than incidental. The
  resolver is what changes it: on a machine with `.env`, rung 3 now
  supplies a URL, so a push with the database **running** exercises the
  tier — the case that produced the observed false green — and a push
  with it **stopped** fails on connection rather than skipping. The skip
  survives only where nothing is configured at all: no variable, no
  `.env`, no `.env.test`. Adding the flag on top would change nothing
  for the first two cases, because it fires only when no URL resolves,
  and would penalise the third — the one population `README.md`'s
  recorded decision protects.
- CI runs `tests/integration` against a Postgres service container,
  migrated with `alembic upgrade head` first, so the tier is verified
  independently of any developer's machine.
- Skip reasons become visible. `pyproject.toml` sets no `addopts`, so
  pytest's default `-r fE` hides them: the twelve helpers already say
  what to start and what to migrate, and a default run prints none of
  it. That is why `3 passed, 64 skipped` read as success — the tier
  said why and nothing showed it.
- `AGENTS.md`'s Testing Strategy section records how the tier resolves
  its database — as a pointer to behaviour that works, not as a step
  anyone must remember.

No **BREAKING** changes to the code under test: no test's assertions
change and the tier's contents are untouched. The local loop does change
for anyone with an `.env` and a stopped Postgres, as the bullet above
records — that is the point, not a side effect.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deploy-pipeline`: the **Pull Request Validation Gate** requirement
  enumerates the tiers the gate runs — `tests/unit` and `tests/agents` —
  and so currently specifies the omission. It gains the integration tier
  and the Postgres service that tier needs, and gains the rule that a
  gate SHALL NOT report success for a tier that did not run. The
  existing constraints are preserved: the gate still reads no deploy
  secret, and an ephemeral service container inside the runner is not a
  connection to the deploy host.

## Impact

- `.github/workflows/ci.yml` — a Postgres service container, an
  `alembic upgrade head` step, and a `pytest tests/integration` step.
- `tests/integration/conftest.py` — new; the single resolver.
- Twelve files under `tests/integration/` — their local
  `_database_url()` helpers give way to the shared fixture. Assertions
  are untouched.
- `README.md` — the "Local Postgres" section. It prescribes the manual
  `export` this change removes, and line 105 states that the tier
  "skips rather than failing", which stops being true for anyone with
  `.env`. It is where a contributor looks, so it is where `.env.test`
  is documented.
- `pyproject.toml` — `-rs` in `addopts`, so a skipped test's reason
  reaches the terminal.
- `AGENTS.md` — one line under Testing Strategy.
- No `.env.example`: the file does not exist in this repository, and
  creating one means deciding what a full example environment contains,
  which is a different change. `.gitignore` already ignores `.env.test`
  through `.env.*`.
- No change to `src/`, no migration, no schema change.

## Deliberately not included

**Test credentials — no Slack, OpenAI or ClickUp values in `.env.test`,
and no whole-file load of either env file.** Only `DATABASE_URL` is read.

This is evidence-led rather than cautious. Across the suite, the tests
that touch those variables **set** them themselves with
`monkeypatch.setenv` and fake values — 23 files set some environment
variable that way, several of them only `DATABASE_URL` — and **no test
reads any credential from the ambient environment**;
`test_preflight.py` uses the names as data, asserting the preflight
checker's behaviour over a list, never the values. The suite is already
hermetic with respect to credentials, so test tokens would furnish
nothing.

They would also cost something. A test that today forgets to set a
variable fails loudly; against an auto-loaded credential file it would
pick up an ambient value and pass. That is the same defect this change
exists to remove — a green that means nothing — reintroduced one layer
down.

The database is the exception, and the reason `.env.test` is worth
having at all: it is the one dependency the integration tier cannot
mock, which is what makes it the integration tier.
