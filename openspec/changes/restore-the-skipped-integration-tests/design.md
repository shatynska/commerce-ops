# Design

## Context

See `proposal.md` — Why, for the motivation and the measurements. What matters here
is the shape of the existing machinery, because this change reuses it rather than
building anything.

Three mechanisms decide today whether an integration test runs, and none of them can
see the other two:

```
  1. tests/integration/conftest.py :: _resolve() + `database_url`
     ── absence of a URL ──▶ skip, or fail under COMMERCE_OPS_REQUIRE_DATABASE
     ── a URL ─────────────▶ run, whatever it names

  2. per-module `_requires_an_isolated_database()`      (2 files, 5 tests)
     ── name does not end `_test` ──▶ skip.  The flag is never consulted.

  3. an in-test precondition                             (1 file, 1 test)
     ── nothing to discriminate on ──▶ skip.  The flag is never consulted.

  guarded by tests/conftest.py?   unit ✓   agents ✓   integration ✗
```

Mechanism 1 is the only one the gate's flag reaches, so the gate's guarantee covers
one of three ways a test can decline to run. `tests/conftest.py` already implements
the general answer — accumulate every skip from both report kinds, then fail the
session naming each one — and excludes `tests/integration` on a premise that holds
on a bare machine and not in CI.

The seeded/migrated distinction is prior art too: `ci.yml`'s `seed-playbook` step
carries a comment explaining that the migration writes 97 rows and `seed_playbook`
writes the other 255, and that without it "the integration tier sees a step set with
no drafts at all". The specification never absorbed that; `AGENTS.md` and `README.md`
inherited the silence.

## Goals / Non-Goals

**Goals**

- One mechanism decides whether a skipped integration test is tolerable, and it is
  the one already written and argued.
- The gate's behaviour changes; a developer's machine's does not.
- Every skip the tier can currently produce is either impossible or fails the gate —
  no skip survives on the grounds that nobody enumerated it.

**Non-Goals (design-level, beyond the proposal's scope statement)**

- Making the guard's condition anything other than the flag already in use. A second
  marker would be a second thing to set and a second thing to forget.
- Bounding the tier's accumulated residue. Measured inert at 1325 retired rows
  (`proposal.md` — Impact), so the premise in `test_playbook_authoring_live.py`'s
  docstring stands and there is nothing to fix.
- Changing how the tier reaches its database. Rungs, `.env.test`, and the refusal of
  a working-database URL are change B's subject.

## Decisions

### Decision 1: Extend the existing guard's path filter, conditioned on the flag

`tests/conftest.py`'s `_GUARDED_TIERS` becomes `("unit", "agents")` plus
`"integration"` **when `COMMERCE_OPS_REQUIRE_DATABASE` is set**. Everything else in
that module is reused unchanged, the `wasxfail` exclusion included — Decision 6
states that exclusion in the requirement rather than altering it, so no task touches
it. Only the path filter, its condition, and the failure report's wording change.

*Why the flag rather than a new marker.* The flag already means exactly "this is a
context where the tier is required and may not be skipped." That is the sentence the
guard needs. Introducing a second variable would let the two disagree, and the
disagreement would be silent in the same way this defect is.

*Why not guard `tests/integration` unconditionally.* It reproduces the defect the
2026-08-25 design rejected: a contributor with no local Postgres is failed for a
condition they cannot act on. The flag is precisely the line between the two
populations, and it is already drawn.

*Alternative rejected — enforce it in `ci.yml` by parsing pytest's output for a
non-zero skip count.* It works, and it is worse in three ways: the failure names a
number rather than a test, it lives in the workflow rather than beside the tests it
governs, and it does not fire for anyone running the tier with the flag set outside
CI — which is exactly what change C will make `pre-push` do.

*Alternative rejected — `-W error`-style strictness via `--strict-markers` or an
`xfail_strict`-shaped pytest setting.* No pytest option turns a skip into a failure;
`-rs` (already set) only reports them. That is why `restore-the-skipped-unit-tests`
wrote a hook in the first place.

### Decision 2: Rename CI's database rather than relax the modules' `_test` check

`POSTGRES_DB` and the database segment of `DATABASE_URL` in `ci.yml` become
`commerce_ops_test`. The database is created by the job's own service container and
is reachable only from that job, so the name is free.

*Why not delete the two modules' guards instead.* They are the only thing standing
between those five tests and a step set they would rewrite. Deleting them is correct
**after** the resolver refuses a non-`_test` database at the door — which is change
B's decision, not this one's. Until then the guards carry a real property and this
change leaves them alone. Once B lands they become dead code and B removes them; the
ordering is deliberate, not an oversight.

*Consequence worth stating.* With the rename, the five tests run in CI for the first
time. This change should expect to discover whether they pass there. They pass
locally against a database prepared the way `ci.yml` prepares one (measured: 137
passed, 1 skipped), so the expectation is that they do — but a first run is a first
run, and `tasks.md` treats a failure among those five as this change's work rather
than as a surprise to hand onward.

### Decision 3: Delete the tier's last skipping test — the sharper form it asserts has no subject

`test_no_seeded_automated_step_is_activated_by_its_handler_existing` skips with
"nothing here to discriminate on". Two earlier drafts of this decision tried to give
it a subject. Both were wrong, and the second was wrong in a way worth recording,
because it is the same error the first made at a different depth.

**Draft one — register a stub under a name a seeded step declares.** The premise is
false. `b8e5c04a1d39_backfill_step_fields.py:77` writes `handler = NULL` for every
backfilled row; `launch_playbook.py`'s `_automation_faults` obliges a handler only
once a step is `active`; `handler_registry.py`'s docstring states the consequence
outright — "One handler is registered, and no step names it." Confirmed live:
`lp.listing.014` and `lp.traffic.001`, both `in-development`, both `NULL`. There is no
name to register under, so `resolvable` is empty on every run of every correctly
prepared database and **the skip is structural, not occasional**. The assertion has
never executed anywhere.

**Draft two — author the step the seed cannot contain, then run seeding against it.**
Implementable, and still a tautology. `seed_playbook._establish()` returns at
`if not added` before touching anything, and on a database prepared the way the gate
prepares one — `ci.yml` seeds, so every vendored identifier is already stored —
`added` is always `0`. Authoring an `mg.*` step raises `len(stored)` and cannot raise
`added`. Even on the other branch, `compose()` says in its own docstring why no branch
of it could ever fail such an assertion:

> Every stored record is carried across untouched — its definition, its status […]
> Nothing here is conditional on what a stored row *contains*.

Seeding is architecturally incapable of re-statusing anything, and that property is
already asserted against the real function at
`tests/unit/test_seed_playbook.py:66-99`.

**So the test is deleted.** Not moved, not re-aimed, not allowlisted.

The case rests on the file it lives in, not on unit coverage alone. Its sibling
`test_a_registered_runtime_does_not_activate_a_seeded_step` (`:234`) already asserts
the very property, **unconditionally, live, over the whole seeded automated set**, and
carries an explicit non-vacuity guard that this process really has registered a
handler:

> The scenario's WHEN, made non-vacuous: this process really has registered at least
> one handler. Without this the assertion below would hold trivially in a deployment
> that registers nothing, which is exactly the state the change moves away from.

The deleted test's only addition is the sharper form — *even for one whose handler
this deployment now registers*. That form needs a seeded step naming a handler, and
the seed structurally cannot carry one.

**The relationship is containment, not overlap.** Both tests read the same
`_authored_steps()`, in the same process, under the same autouse `register_all()`
fixture. The deleted test's subject is
`[step for step in seeded_automated if step.handler in registered]` — a filtered
*subset* of exactly the tuple `:234` calls `automated`, over which `:234` asserts
`len(still_in_development) == len(automated)`, every member. An assertion over the
whole set entails the assertion over any subset of it, so the deleted test could not
have failed in any state where `:234` passes.

**And no scenario is left uncovered.** `openspec/specs/launch-playbook/spec.md:341-344`
carries exactly one scenario for this behaviour — *A registered runtime does not
activate a seeded step* — and `:234` is the test named for it. The deleted test's
docstring cites a *requirement statement*, not a scenario, and calls itself "the
sharper form" of the same one. There is no second scenario under `openspec/specs/` it
uniquely served.

So **nothing is lost that was ever checked**, at either level: the integration-level
property is entailed by a sibling in the same file, the specification's only scenario
for it stays covered, and the seeding half is held at unit level against the real
`compose()`.

*Why deletion is a legitimate answer rather than an evasion.* `tests/conftest.py`
names it as one, in the failure message this change extends:

> If a test genuinely cannot run at this tier, move it to `tests/integration` or
> delete it -- do not skip it.

**The finding is the deliverable, and it outlives the test.** The requirement's
negative half — activation is "never something seeding or deploying does on an
author's behalf" — has *no integration-level subject in this system*, because the only
writer in the container's start chain is `seed_playbook` (`check_step_handlers` was
checked and only reports, every read scoped to `active`), and it cannot re-status by
construction. That is worth more than any test that could be written for it, because
it is what stops the next author manufacturing a third subject. It goes in the
module docstring where the test was, not only here.

*Alternative rejected — re-aim the test at `activate_step`.* `_registration_faults`
(`playbook_authoring.py:364-383`) genuinely consults the registry and genuinely
refuses, so a test authoring an `mg.*` automated step and then activating it — accepted
with `listing.subcategory_advisor` registered, refused with a name nothing registers —
would have a branch that can fail. It is rejected because it tests the requirement's
*positive* half, which this change did not set out to touch and which no scenario here
maps to. `AGENTS.md`: an improvement noticed along the way becomes a separate change
rather than being folded in. Recorded because it is the strongest thing not being
done, and because whoever wants integration coverage of activation should start here.

*Alternative rejected — assert vacuously over the empty set.* `assert all(...)` over no
elements passes. The module docstring refuses it ("says so rather than passing
silently"), and it converts a visible skip into an invisible pass — this defect, one
level down. Note that both earlier drafts were this alternative wearing a disguise:
an assertion that cannot fail is a vacuous pass whether or not the set is empty.

*Alternative rejected — `pytest.xfail`.* The guard exempts `wasxfail`, so it would work
mechanically and is a lie semantically: the test is not expected to fail, it is
inapplicable. See Decision 6, which closes that channel rather than relying on nobody
using it.

*Alternative rejected — contrive a partially-seeded database so `added > 0`.* More
machinery in the gate than the check is worth, to reach a branch that still could not
fail, since `compose()` has no status branch on either side.

*Alternative rejected — re-scope the requirement to admit one declared precondition.*
`tests/conftest.py`'s argument against a list is about lists of *filenames* carrying
false reasons, so a single declared, argued precondition is not quite what it forbids.
Rejected anyway: the precondition here is not merely undeclared, it is unsatisfiable,
and negotiating an exception for a test that can never run is worse than removing it.

### Decision 4: The specification records seeding, though no behaviour changes

`ci.yml` has seeded since `seed-the-reference-step-set`. The requirement says only
"apply the schema". Widening it to the state a deployment serves changes no code and
no workflow — it makes the specification describe what the gate already does, and
gives `AGENTS.md` and `README.md` something to be consistent with.

*Why it belongs in this change rather than a documentation-only one.* Two of the
three misreadings in `proposal.md` — Why trace to this silence: four tests failing on
an unseeded database were read as "pre-existing failures", and the recipe that
produced that database is in `AGENTS.md` and `README.md`, both of which say "create
and migrate" and stop. A change about the gate not lying about what it ran is the
right place to stop the setup instructions lying about what a prepared database is.

### Decision 5: `AGENTS.md` gains worktree rules, in the workflow document rather than the README

The rules are addressed to whoever is *working* — including an agent session — not to
someone setting a machine up once. `AGENTS.md` is where this project states
obligations of that kind; `README.md` keeps the setup recipe.

Five rules, each traceable to an observed failure rather than invented:

| rule | observed as |
| --- | --- |
| The Postgres container runs continuously. Check it (`docker ps`) before concluding a database or Docker is unavailable. | *"Docker isn't available in this WSL setup"*, while `commerce-ops-postgres-1` was up |
| A worktree does not inherit `.env.test` — it is gitignored. Configure one before relying on the tier. | 2 of 4 checkouts on this machine are unconfigured right now, this one included at creation |
| Migrated is not seeded. `alembic upgrade head`, then `python -m commerce_ops.seed_playbook`. | 4 tests failing, read as "pre-existing" |
| Read a failing test's assertion message before concluding the failure is pre-existing. | same incident |
| The `_test` requirement is a **suffix**, not a name. `commerce_ops_x_test` runs; `commerce_ops_test_x` silently loses five tests. | the skip message says "Create `commerce_ops_test`", which reads as a literal name |

The sixth candidate — *"`pre-push` printing `Passed` for the integration tier is not
evidence it ran"* — is deliberately **not** written down. It is true today and change
C makes it false, and a rule that documents a defect competes with fixing it. The
defect is recorded in `docs/deferred-work.md`, which is where a known-and-unfixed
thing belongs.

### Decision 6: An expected failure is not a skip, and the spec says so

`tests/conftest.py:117` returns early on `wasxfail`, so an `xfail`ed test never counts
as a skip. That exclusion is correct — an `xfail` is a recorded, named expectation, not
a check quietly withdrawn — but the requirement as first drafted said **any** skip
fails the gate "whatever the skip's stated reason", admitting no exception. An
implementer reading the spec alone would build a guard with no `wasxfail` branch, and
the spec and the code would disagree about a documented bypass for exactly the defect
class this change closes.

The requirement now states the exclusion rather than leaving it to the implementation:
an expected failure is not a skip for this purpose. Both halves then say the same
thing, and the residual — that a future author could route a genuine skip through
`pytest.xfail` to evade the guard — is recorded in Risks below rather than pretended
away.

*Alternative rejected — drop the exclusion for the integration tier only.* It closes
the bypass, at the cost of an asymmetry between tiers and a contradiction with
Decision 1's "reused unchanged". A tier where `xfail` means something different from
what it means one directory over is a worse trap than the one it removes.

## Risks / Trade-offs

**The five tests fail in CI on their first real run** → They pass locally against a
database prepared as `ci.yml` prepares one, and CI's Postgres is the same image the
compose file runs. `tasks.md` scopes a failure among them as this change's work.

**A genuine skip is routed through `pytest.xfail` to evade the guard** → Not closed,
by Decision 6. `xfail` is visible in the run summary and in review in a way a skip is
not, and an author writing `pytest.xfail("no database")` is making a false statement
under their own name rather than inheriting a silent default. That is a materially
different act from the three misreadings in `proposal.md` — Why, all of which were
honest readers misled by silence.

**A future legitimately-conditional integration test has nowhere to go** → It has the
same nowhere the commit-time tier's tests have had since 2026-09-01, and Decision 3
is the worked example of the answer: manufacture the precondition, or assert
something unconditional. If that ever proves genuinely impossible for some test, the
right response is to revisit the zero-tolerance rule for both tiers at once, not to
carve an exception into one.

**A developer who sets the flag by hand now gets a hard failure they did not before**
→ Correct and intended: setting it is a statement that the tier is required here. It
is also the seam change C uses.

**The guard's condition is an environment variable, so a CI misconfiguration that
unsets it silently restores today's behaviour** → Real, and not fully closed here.
`ci.yml` sets it in the job's `env:` block alongside `DATABASE_URL`, so losing it
means editing the same block that configures the database. Worth noting that the
existing `tests/unit/test_settings_env_drift.py` pattern — a declared set compared
against consumption — is the shape that would close it, and is not proposed here.

**The guard's new half is verified only by a procedure nobody runs again** → Closed.
A first draft verified it by adding a skip, observing, and reverting, which is a
procedure and not a test. `tasks.md` §5 instead extends
`tests/unit/test_commit_time_tier_skip_guard.py`, the spec-derived test that already
exists for this guard and already builds its child environment explicitly. That file
also currently asserts the integration exclusion is *unconditional*; it keeps passing
by accident, because the flag is not inherited into the child, and §5.3 rewrites it
rather than leaving a test whose docstring contradicts the requirement.

## Migration Plan

None. No data, no schema, no deployed behaviour. The change is a workflow file, two
test-infrastructure files, one requirement, and documentation. Rollback is a revert.

## Open Questions

None that can be deferred without changing the specs, approach, or tasks. The two
that existed at exploration — whether accumulated debris breaks the tier, and how to
retire the legitimate skip — were settled by measurement (`proposal.md` — Impact) and
by Decision 3 respectively.
