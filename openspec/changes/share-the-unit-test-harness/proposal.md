## Why

The test suite is **202,048 lines against 27,578 lines of source** — a ratio of
roughly 7.3:1 — across 319 test files and **four** `conftest.py` files, two of
which exist only for the Slack listener-draining wrapper.

Almost none of it is shared, and the measurement that says so is not the ratio:

**61% of the test suite is preamble.** 123,285 of the 202,048 lines sit *before
the first test* in their own file. Of those, **~42,900 lines are byte-identical
to a block that already exists in another file** — measured by shingling every
file's preamble into 10-line windows and counting the lines covered by a window
that occurs in two or more files. 1,060 distinct top-level symbols are declared
in more than one test file; the suite declares 2,211 in total.

The single most-copied block appears verbatim in **159 of 319 test files**:

```python
SPECIFIED_GATE_ORDER: Final = (
    "commit", "order", "listable", "stock-ready",
    "live", "ignition", "phase-one-complete", "graduated",
)
```

`launch_playbook.py:413` already publishes this as `GATE_SEQUENCE`, and its
neighbour at line 428 states the convention being violated — the final gate is
*named rather than spelled at each site* because "three rules turn on it, and a
sequence change must move all three together." Three sites in `src/`. **159 in
`tests/`**, and `GATE_SEQUENCE` is imported by exactly zero of them.

### This is not a style complaint

**It converted one signature change into a 24-test outage.**
`thread-launch-slack-notifications` gave `run_automation_pass` a required
keyword-only `establish_thread`. Exactly one harness needed updating — `_run_pass`
in `test_automation_pass_repeat_backoff.py` — and because that harness is 2,400
lines into a file nobody wanted to open, the cheaper-looking move was to skip the
file. Every test in it stopped running, under a reason that was untrue.
`restore-the-skipped-unit-tests` fixed that instance and added
`tests/conftest.py`'s zero-skip guard so it fails loudly next time. Nothing
prevents the next signature change from meeting the same 2,400 lines; the guard
turns a silent outage into a blocked commit, which is better and is not a fix.

**Incomplete doubles have already caused two production failures.** When each
file writes its own stand-in, each writes the minimum that file needs.
Production code then grows a tolerance for the shortfall — and a tolerance
absorbs real wiring defects along with the fakes it was widened for. Two
tolerances have been closed since `docs/deferred-work.md` recorded them, each
*after* it failed in production, and each carries a docstring saying what it
cost:

- `automated_decisions.py:95` — probed three spellings for one member lookup.
  The composition root supplied a `MembersStore`, which matched none of them, so
  the probe returned `None` and **every decision by every identity was refused**
  as "the membership does not know that Slack identity." A wiring fault reported
  as a data fault.
- `playbook_authoring.py:245` (`_read_members`) — accepted three shapes for one
  reader and fell through to `tuple(members)`, which produced `'PostgresMembers'
  object is not iterable` **from the middle of a write**.

**Five remain**, one more than `docs/deferred-work.md:1068-1095` lists — that
entry is stale in both directions, and re-enumerating against the current source
is part of this change:

| site | what it tolerates |
|---|---|
| `gate_progression_job.py:256` (`_crossed`) | a fake modelling less than `LaunchProgressed` |
| `gate_progression_job.py:267` (`_awaiting_gate`) | probes `("awaiting_gate", "gate_id", "current_gate")` |
| `clickup_sync.py:128` (`_members`) | three shapes: `list_members()`, a callable, a plain iterable |
| `clickup_sync.py:139` (`_member_identifier`) | probes `("identifier", "id", "member_id")` — **recorded nowhere** |
| `playbook_authoring.py:266` (`member_identifier`) | the same probe, verbatim — the entry's fifth item, **not** closed with its neighbour |

The last two are the same eight lines in two modules. And the first states the
dependency outright — `gate_progression_job.py:256`:

> *"tolerating a caller's fake that models less than the real `LaunchProgressed`
> does […] this module is exercised by tests substituting `progress_launch` with
> stand-ins of varying completeness, and a plain attribute access would make
> every one of them model a field only this one new branch reads."*

That is production code recording that its own shape is dictated by the
incompleteness of test doubles. The dependency also runs the other way, visibly:
the dominant `_FakeMembers` in `tests/` declares `list_members()`, then aliases
`members = list_members`, then adds `async def __call__` — **three spellings, one
per branch of `clickup_sync._members`**. The fake models the tolerance, so the
tolerance can never be deleted.

`automation_pass.py` alone carries 31 `: Any` annotations and 16 `getattr`
probes under `mypy strict = true`. Strict mode is satisfied nominally and buys
nothing where the types are `Any`, and the reason they are `Any` is partly the
boundary (`.importlinter` forbids `launch` naming `catalog`'s and `access`'s
types) and partly that a `Protocol` would fail against the doubles as written.
`unify-launch-adapter-dependencies` proposes typing those collaborators as
protocols and explicitly cannot delete the tolerances, because deleting one is
only safe once the doubles it tolerates are complete. **This change is what makes
them complete.**

**The tax is compounding.** Between 2026-09-01, when this proposal was first
written, and 2026-09-03:

| | 2026-09-01 | 2026-09-03 | Δ |
|---|---|---|---|
| test lines | 162,335 | 202,048 | **+24%** |
| source lines | 23,629 | 27,578 | +17% |
| test files | 272 | 319 | +47 |
| ratio | 6.9 : 1 | **7.3 : 1** | worse |

Tests grew half again as fast as source over two days of ordinary feature work.
Every one of the remaining proposed changes lists test files as its largest
surface area, and that will keep being true.

## What Changes

- **A `tests/support/` package holding the arrangement every tier already writes
  by hand**: the playbook framework's constants; builders for a launch, a step
  definition, a playbook, a product, a member; the HTML assertion helpers; the
  admin-session harness; one fake session; one recording Slack API; one
  recording ClickUp client. Named and typed against the real thing, so a double
  that stops matching its subject fails at the seam rather than being absorbed
  by a `getattr` in production code.

- **Migration is split by how far each duplicate has drifted**, because the two
  populations carry entirely different risk and `design.md` treats them
  separately:

  | | copies | distinct variants | migration |
  |---|---|---|---|
  | `SPECIFIED_GATE_ORDER` | 159 | **1** | mechanical |
  | `_opening_for` | 120 | **1** | mechanical |
  | `CONFIRMATION_GATES` | 128 | 1 (+1 formatting) | mechanical |
  | `_gates` | 93 | 6 (89% one) | mechanical |
  | `_elements`, `_inherited`, `_VOID_TAGS`, … | 18–38 each | 1 | mechanical |
  | `_step` | 135 | **77** | one builder, per-file deltas |
  | `_hold` | 104 | **56** | one builder, per-file deltas |
  | `_playbook` | 95 | **61** | one builder, per-file deltas |
  | `_Member` | 47 | 14 | one fake |
  | `_FakeMembers` | 43 | 24 | one fake |
  | `_RecordingSlackApi` | 12 | **12** | one fake |

  The verbatim population is a delete-and-import with no judgement in it. The
  drifted population turned out, on reading it, to be **one body with many
  default sets** rather than many designs: all 135 `_step` declarations are
  `attributes: dict = {...}; attributes.update(overrides); return
  StepDefinition(**attributes)`, differing only in that dict. `design.md`
  Decision 4 derives the canonical default set from the modal value of each of
  the 17 keys and measures what each file would then need to override —
  **69 of the 121 need two or fewer**, 94 need four or fewer. The signatures are
  *not* uniform (121 `(**overrides)`, 14 `(identifier, **overrides)`), so the
  migration form is a `functools.partial` where the local signature allows one
  and a one-line wrapper where it does not.

- **The builders are complete by construction, not minimal.** A
  `LaunchProgressed` double that models `crossed`, `awaiting_confirmation`,
  `awaiting_gate`, `gate_id` and `current_gate` is what allows
  `gate_progression_job._crossed` to read one attribute instead of three.
  Completeness is the point; a builder that models only what its first caller
  needed reproduces the problem in one file instead of 159. `design.md`
  Decision 6 makes it checkable rather than aspirational: each fake carries a
  `_conforms: SomeProtocol = TheFake()` assignment, so an incomplete double is a
  `mypy` error rather than something a reader has to notice.

- **A spec-restating constant stays a literal, declared once.**
  `SPECIFIED_GATE_ORDER` exists so that 15 files can assert production's gate
  sequence *against an independently written statement of the specification* —
  `test_playbook_coherence_by_status.py:472` compares `playbook.gates` to it
  directly. Replacing it with an import of `GATE_SEQUENCE` would make those
  assertions vacuous. Declaring the same literal **once** instead of 159 times
  does not: it is still independent of production. `design.md` makes this the
  explicit rule, because it is the one place where "share it" and "keep the test
  honest" appear to conflict and do not.

- **A file is migrated when its own tests are unchanged in what they assert and
  shorter in how they arrange it.** A migration that changes an assertion is not
  a migration and must be raised as a finding instead.

- **The rule for new tests is recorded** in `AGENTS.md`'s Testing Strategy
  section, alongside the tier definitions it already carries: a new test uses the
  shared builders, and a new bespoke fake is a signal that a builder is missing
  rather than a licence to write a thirteenth `_FakeSession`.

- Explicitly **not** in scope: deleting or weakening any assertion; changing
  which tier any test runs in; reducing the number of tests;
  `tests/integration/conftest.py`, whose database resolution is genuinely shared
  already and works; `tests/conftest.py`'s zero-skip guard, which is not
  arrangement.

- Explicitly **not** in scope: removing the five surviving production-code
  tolerances. This change makes that removal safe; performing it belongs with
  `unify-launch-adapter-dependencies`, where the types those tolerances stand in
  for are being defined. Doing both here would mean editing `src/` inside a
  change whose whole claim is that it does not.

- Explicitly **not** a goal: reducing the line count for its own sake. Some of
  the 202k lines are long because the behaviour is subtle and the docstrings
  carry the reasoning, which is this project's convention and worth keeping.
  What is removed is arrangement, not explanation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/`, `AGENTS.md`, one line of `pyproject.toml`
(`pythonpath` under `[tool.pytest.ini_options]`) and
`docs/proposed-change-order.md`. Every requirement the suite covers is unchanged
and every test must still assert exactly what it asserts today — that is the
acceptance criterion, not an aside.

One recorded specification mentions anything this change touches:
`deploy-pipeline`'s validation-job requirement, which names `ruff`,
`ruff format --check`, `mypy`, `lint-imports` and the three tiers by path.
`tests/support/` is a fourth directory under `tests/` that is not a tier and is
collected by nothing, so that requirement stays satisfied and owes no `MODIFIED`
delta.

`.openspec.yaml` therefore sets `skip_specs: true`, following
`isolate-tests-from-the-shared-runner` (2026-08-25), the nearest precedent for a
change wholly inside `tests/`.

## Impact

- **New**: `tests/support/` — builders, fakes, HTML helpers, and the protocols
  they satisfy.
- **Reduced**: the 159 files declaring `SPECIFIED_GATE_ORDER`, the 37 carrying a
  hand-rolled HTML parser, the 46 files declaring `_Member` (47 declarations),
  the 42 declaring `_FakeMembers` (43 declarations, 24 variants). The eleven
  files over 1,700 lines are where it is felt most:
  `test_clickup_field_configuration_check.py` (2,535),
  `test_automation_pass_repeat_backoff.py` (2,412), `test_launch_admin_list.py`
  (2,367), `test_launch_surface_vocabulary_rules.py` and
  `test_launch_admin_detail.py` (2,144 each).
- `tests/unit/launch/infrastructure/driving/conftest.py` and
  `tests/unit/omni_agent/infrastructure/driving/conftest.py` — the duplicated
  `_DrainsDeferredListeners` wrapper. The first declares itself a mirror of the
  second in its own docstring; `design.md` hoists it.
- `AGENTS.md` — Testing Strategy gains the rule for new tests.
- `pyproject.toml` — one line, `pythonpath = ["."]` under
  `[tool.pytest.ini_options]` (`design.md` — Decision 1).
- `docs/proposed-change-order.md` — the entry is deleted on archive, per that
  file's own rule. It is **not** renumbered in the meantime: the queue is worked
  out of order by this decision, not by editing the file, and an entry that is
  about to be deleted is not worth renumbering twice.
- **No change to `src/`**, to the schema, to CI configuration, or to any
  deployed behaviour. The commit-time gate runs the same tests and should not get
  slower; if it gets meaningfully faster, that is a bonus and not a claim being
  made here.

### Ordering against the other proposed changes

This one touches nearly every test file and will conflict with anything else
editing tests. `docs/proposed-change-order.md` placed it **last** for that
reason alone — not for lack of value. Both of its preconditions are now met:

- `restore-the-skipped-unit-tests` landed 2026-09-01, so no file being migrated
  is one nobody has seen run.
- `rename-the-roster-to-members` merged 2026-09-02, so the "rebase onto it, not
  the reverse" note is discharged; rebasing onto `main` is enough.

And as of 2026-09-03 **nothing is in flight.** Every other queue entry —
`defer-eager-clickup-convergence`, `unify-launch-adapter-dependencies`,
`unify-the-launch-advisory-locks` — exists as a `proposal.md` and no code.
`defer-eager-clickup-convergence` is still in exploration with an open design
decision. The two sibling worktrees sit on branches already merged to `main`.

The only stated cost of moving this change up is therefore currently zero, and
that window closes the moment any other entry starts. **This proposal asks for it
to be worked now rather than last.** The queue file is not edited to say so — its
entries are deleted on archive, and renumbering an entry about to be deleted
records the decision in the shortest-lived place available. The decision is
recorded here instead.
