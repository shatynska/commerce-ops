## Context

See `proposal.md` — Why. The constraints that shape the approach:

- Every integration test resolves its own URL. Twelve files carry the
  same `_database_url()` shape, calling `pytest.skip()` when
  `DATABASE_URL` is unset; `tests/integration/` has no `conftest.py`.
  The bodies are identical but the **messages are not** — each names the
  migration its own subtree needs ("the table-split migration", "the
  `known_work` migration", "step tables and seed"). Collapsing twelve
  tailored diagnostics into one generic message is a real loss, and the
  shared message has to carry a migration note to stay as useful.
- The tests assume the schema is already applied. Their own docstrings
  state "`alembic upgrade head` assumed applied (schema + seed), a skip
  when `DATABASE_URL` is unset, no truncate fixture". CI must therefore
  migrate before running them.
- They are written to be safe against a populated database: writes are
  confined to the `mg.*` namespace with unique descriptions per run, and
  seeded `lp.*` rows are never updated or retired. That is what lets
  them run against a developer's own database as well as a throwaway CI
  one.
- `.env` already carries a `DATABASE_URL` pointing at `localhost:5432`,
  and `docker-compose.yml`'s `postgres` service publishes exactly that.
  The value the tier needs is present on a working machine; nothing
  reads it.
- The tier currently has no database of its own. Run locally it uses the
  one the developer works in, and it leaves traces there: that database
  holds **138 `mg.*` rows** of accumulated test residue at the time of
  writing, 27 of them from two runs made while investigating this
  change. The tests are written to be safe against a populated
  database, but that safety is a convention the tests keep, not a
  property of where they run.
- `.gitignore` already carries `.env.*` with `!.env.example`, so a
  second env file is anticipated by the repository and needs no change
  there.
- `deploy-pipeline` requires the gate to run "without any host
  connection" and to declare no deploy SSH credential. Whatever CI gains
  must keep both true.

## Goals / Non-Goals

**Goals:**

- Make it impossible for the tier to report success without running,
  wherever the tier is required.
- Give the tier one place that decides how it reaches a database.
- Keep a genuine skip available for someone with no database
  configuration at all — no variable and no env file.

**Non-Goals:**

- Changing any test's assertions, fixtures or contents beyond replacing
  its local URL resolver.
- Loading `.env` wholesale into the test process. See
  `proposal.md` — Deliberately not included.
- Adding a dependency for `.env` parsing. One key, read with the
  standard library, is smaller than `python-dotenv` and has no import-
  time side effects.
- Making the unit tiers depend on a database. They are mocked by design
  and stay that way.

## Decisions

### One resolver in `tests/integration/conftest.py`

One resolution order, shared by the two fixtures introduced in the next
decision. The URL is resolved once per session, in this order:

```
   DATABASE_URL in os.environ ?      ──yes──▶  use it   (explicit wins)
             │ no
             ▼
   .env.test has DATABASE_URL= ?     ──yes──▶  use it   (isolated test db)
             │ no
             ▼
   .env has DATABASE_URL= ?          ──yes──▶  use it   (today's behaviour)
             │ no
             ▼
   tier required (env flag set) ?    ──yes──▶  FAIL the session
             │ no
             ▼
                    skip, stating that no database was configured
```

Each rung answers a different question, which is why there are four and
not fewer. The environment variable is an explicit instruction and must
win. `.env.test` is the developer's standing choice to keep the tier out
of the database they work in. `.env` is what every machine already has,
and is the rung that makes the tier run without anyone doing anything.
The flag decides what an unresolved URL *means*.

The twelve `_database_url()` helpers become requests for the
`database_url` fixture below. This is the enabling change: while the
rule lives in twelve copies, any fix has to be made twelve times and
will drift.

**The conftest publishes the resolved value into
`os.environ["DATABASE_URL"]` as well as returning it.** Four integration
files drive the real FastAPI application
through `TestClient`, and its session provider reads the variable
straight from the process environment
(`shared/infrastructure/driven/database.py:31-37`, raising when it is
absent or empty). Today the skip guarantees the variable is set before
any of them runs; rungs 2 and 3 would remove that guarantee and **three
of the four** would fail on a `RuntimeError` instead of running — the
exact outcome the change exists to produce the opposite of. The fourth,
`test_scheduled_runs_freshness_unreachable.py`, supplies its own address
in every test and never resolves one; it is unaffected here and is the
subject of the next decision. Publication uses a session-scoped
`MonkeyPatch`, so it unwinds at the end of the session and a per-test
`setenv` still overrides it. It is still one key, so
nothing about the credentials decision changes.

**Alternative rejected — override the app's dependency in those tests
instead.** Cleaner in principle, but it edits test bodies to route
around the very wiring they exist to exercise, and this change otherwise
touches no test's behaviour.

### Publishing is autouse; gating is opt-in

These are two jobs and they need different triggers, because one test in
the tier must not be gated at all.
`tests/integration/shared/test_scheduled_runs_freshness_unreachable.py`
says so in its own docstring: it "needs no *configured* Postgres … unlike
its neighbours it does not skip when `DATABASE_URL` is unset. That is
deliberate — the scenario it covers is about a database that is not
there, and a test that skipped without one would skip exactly when it
could run." A single autouse fixture carrying both jobs would start
skipping the only two integration tests that run on a bare machine — in
a change about tests that silently do not run.

So the conftest offers two things:

- an **autouse session fixture that only publishes**: if a URL resolves,
  it is placed in `os.environ`; if none does, it publishes nothing and
  raises nothing — it still reports, see below. Harmless to every test,
  and it is what makes the app-driving files work under rungs 2 and 3.
- a **`database_url` fixture that gates**: it returns the resolved URL,
  and it is the one that skips, or fails under the flag. Tests request
  it because they need a configured database — which is exactly the
  distinction the twelve `_database_url()` calls already encode.

The never-skipped file requests neither and keeps its behaviour
unchanged. The twelve converted files request `database_url` and behave
as they do today, minus the duplication.

**Nothing here is worth writing unless pytest will show it.**
`pyproject.toml` sets no `addopts`, so two defaults apply to the exact
invocations this change uses: stdout from a session fixture is captured
and surfaces only beside a failing test, and `-r fE` suppresses skip
reasons entirely.

That is not a detail — **it is the root of the reported problem.** The
twelve helpers already carry precise messages naming the service to
start and the migration to apply, and a default run prints none of them.
Verified: `pytest tests/integration/launch/test_playbook_seed.py -q`
reports `13 skipped` and nothing else; the same run with `-rs` prints
the full instruction. The reason the observed `3 passed, 64 skipped` read
as success is not only that the tier skipped — it is that the tier said
why and pytest swallowed it.

So the session report is written through `pytest_report_header`, which
prints above the run, uncaptured and unconditionally, and `-rs` is added
so a skip reason reaches the reader. Without both, every message this
change composes would be correct code nobody sees.

**The publisher is never silent about being silent.** When a URL
resolves it reports which rung supplied it, with the host, port and
database name but **not** the password the URL carries. When none
resolves it says so, and says the tier will skip — because that is the
state a reader most needs explained, and the state in which a test that
needs a database and forgot to request `database_url` will hard-error
from `database.py:34` rather than skip. Opting in being forgettable is
the cost of making the exemption a property of what a file asks for;
the report is what makes it diagnosable in one line rather than a
traceback.

**Alternative rejected — one autouse fixture with an exemption** (a
marker, or autouse scoped to two subpackages). It works, but it makes
the exemption a property of where a file sits rather than of what it
asks for, and a future test needing no database would have to know to
opt out rather than simply not opting in.

**Alternative rejected — `pytest-dotenv` or `python-dotenv`.** A
dependency to read one key from one file, and both load the whole file
by default, which is the thing this change specifically will not do.

**Alternative rejected — set `DATABASE_URL` in `pyproject.toml`'s pytest
config.** It would have to hard-code a URL with a password in a tracked
file, and it would override a developer's deliberate choice of a
different database.

### `.env.test` carries a database and nothing else

The conventional shape of this file, in the frameworks that popularised
it, is a full parallel environment: a test database *and* sandbox
credentials for every external service. Only the first half earns its
place here.

The suite does not read credentials from its environment. The tests that
touch those variables **set** them themselves with `monkeypatch.setenv`
and fake values — 23 files set some environment variable that way,
several only `DATABASE_URL` — and **none reads a credential from the
ambient environment**, and `test_preflight.py`
uses the variable *names* as data — a list it asserts the preflight
checker's behaviour over — never their values. Test tokens would supply
something nothing asks for.

They would also weaken the suite. A test that omits a variable it needs
currently fails; with credentials loaded from a file it would inherit an
ambient value and pass. That is the defect this change removes — a green
that means nothing — rebuilt one layer down, and it is the reason the
resolver reads a single key rather than loading a file.

The database is the exception because it is the one dependency the tier
cannot mock. Isolation there is worth having for two reasons beyond
tidiness: the tier accumulates `mg.*` rows in whatever database it runs
against, and `test_playbook_seed.py` asserts a "before any authored
edit" premise that a hand-edit through the admin UI would break — a
failure with no connection to the code under test.

**Kept optional deliberately.** Absent `.env.test`, the tier falls back
to `.env` and behaves as it does today. Requiring the file would put a
setup step in front of every contributor to remove a papercut that only
bites people who run the tier often.

### A required-tier flag turns a skip into a failure — in CI only

The skip is correct for a contributor with no database configuration at
all — no variable and no env file — and wrong for CI.
Rather than guess which context is which, the caller says so: an
environment variable — `COMMERCE_OPS_REQUIRE_DATABASE=1` — set by the CI
step. When it is set and no URL resolves, the session fails with a
message naming what to start and what to set.

**`pre-push` does not set it — and the reason is not the one this
change's first draft gave.** That draft said the flag would reverse
`README.md`'s recorded decision that the tier "skips rather than failing
— which is what keeps the `pre-push` hook from rejecting a push on a
machine with no local Postgres". The honest position is that **the
resolver reverses that decision by itself, flag or no flag**:

| at `pre-push` | before | after |
| --- | --- | --- |
| `.env`, Postgres running | 3 passed, 64 skipped — the observed false green | the tier runs |
| `.env`, Postgres **stopped** | skip, push allowed | rung 3 resolves, connections fail, **push rejected** |
| no `.env`, no variable | skip, push allowed | skip, push allowed |

So the README decision survives only for the third row. For the second,
`pre-push` now effectively requires a *reachable* Postgres of anyone who
has an `.env`, and that is a real change to the local loop which this
change makes deliberately: a developer with the database stopped is told
so at push time rather than at review time.

The flag is dropped from `pre-push` because in that second row it is
**inert** — it fires only when no URL resolves, and rung 3 resolved one.
It would change behaviour for the third row alone, which is the one
population the README decision still protects and the one least able to
act on the failure.

**Alternative rejected — make rung 3 conditional on the flag**, so a
bare `pre-push` skips exactly as before. It is the only option that
preserves the recorded trade-off intact, and it is rejected because it
also discards the change's main local benefit: the tier would go back to
not running for the very person who has a working database sitting
there. Recorded because rejecting it is a judgement, not a technicality.

The division of labour that leaves: the rungs make the tier *run*
wherever it can, `pre-push` reports honestly to whoever has a database
configured **and has installed that hook** — `default_install_hook_types`
is `[pre-commit, commit-msg]`, so a plain `pre-commit install` leaves no
pre-push hook and none of the three rows above applies — and CI is the
gate that cannot be skipped. That the local half reaches only some
contributors is a further reason the CI half carries the guarantee.

**Alternative rejected — always fail, everywhere.** It makes the tier
unrunnable for anyone without Docker and turns `uv run pytest` over the
whole tree into a hard error on a fresh clone.

**Alternative rejected — infer the context from `CI=true` or from the
git-hook environment.** `CI` is set by other tools, and a hook's
environment is not a stable contract. An explicit flag says what is
meant, which is the whole reason a flag exists rather than a heuristic.

**Alternative rejected — detect whether Postgres is reachable and skip
only when it is not.** This is the question row 2 of the table invites,
and it is the most dangerous option available: a database that is
briefly down would silently downgrade a required run to a skip, which is
precisely the class of defect this change exists to remove. Row 2 fails
loudly on purpose. Note this is distinct from task 1.9, which improves
the *diagnosis* of that failure without softening it.

### CI runs the tier against a service container

A `postgres:16-alpine` service — the same image
`docker-compose.yml` runs — with a health check, `alembic upgrade head`
against it, then `pytest tests/integration` with the required flag set.
The URL is composed in the workflow from the service's own credentials;
no secret is involved, because the database is ephemeral and reachable
only from the job.

This keeps `deploy-pipeline`'s two existing constraints true, and the
spec delta says so rather than leaving it to be re-derived: a service
container runs inside the GitHub-hosted runner, so the gate still makes
no connection to the deploy host and still declares no deploy SSH
credential.

The delta does reword one clause, deliberately: "without any host
connection" becomes "without any connection to the deploy host". The
substance is unchanged — the requirement's own first scenario already
says "the deploy host", and the literal reading is already false today,
since `actions/checkout` and `uv sync --locked` both connect to hosts.
The rewording states what the constraint always meant, so that an
ephemeral service inside the runner is not caught by a phrase aimed at
the deployment target.

**Alternative rejected — run the tier only at `pre-push`.** That leaves
verification on whoever happens to push, from whatever machine, and a
contributor without Docker could still merge a break. CI is the only
layer that does not depend on a laptop.

## Risks / Trade-offs

- **CI gets slower.** The tier runs in about 12 seconds locally; the
  service container and `alembic upgrade head` dominate. Accepted: the
  alternative is a tier nobody runs.
- **`pre-push` now needs a *reachable* database of anyone with `.env`.**
  Not because of the flag, which is CI-only, but because rung 3 resolves
  a URL and the tier then tries to use it. A stopped Postgres turns a
  push into dozens of connection tracebacks, so the session must report
  the supplying rung and how to start the service — otherwise the change
  trades a silent skip for an unreadable failure.
- **The env-file fallbacks couple tests to files that are not tracked.**
  A machine with neither file and no variable still skips, exactly as
  today. The fallbacks are what remove the false green locally, by making
  the tier run; the flag is what removes it in CI, by making an
  unconfigured gate fail.
- **Two env files can disagree, silently.** A stale `.env.test` pointing
  at a database that was dropped, or at one never migrated, produces a
  connection or schema error rather than the clear "no database"
  message — and it takes precedence over a perfectly good `.env`. The
  resolver therefore reports **which rung supplied the URL at session
  start**, unconditionally, rather than only on a connection failure:
  the harder case is a database that connects fine and has no tables,
  where there is no connection error to hang the diagnosis on.
- **A separate test database has to be created and migrated by hand.**
  Nothing in this change creates `commerce_ops_test`. Whoever opts in
  runs `createdb` and `alembic upgrade head` against it once. Automating
  that is more machinery than the problem justifies, but it does mean
  the isolation is opt-in effort, not a default.
- **Two migration paths against one database in CI.** `alembic upgrade
  head` seeds the playbook, and the tier's own tests assume that seed.
  If a future migration stops being idempotent against an empty
  database, CI is where it will surface — which is a gain, not a risk,
  but it will surface as an integration failure rather than a migration
  one.

## Migration Plan

None. No schema change, no persisted-data change, no change to `src/`.
Revertible as a code change alone.
