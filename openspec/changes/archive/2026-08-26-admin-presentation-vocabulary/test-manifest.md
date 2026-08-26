# Test manifest — `admin-presentation-vocabulary`

Written before any implementation of this change existed, from the
change's delta specs alone. Not an artifact the OpenSpec schema knows
about: it will **not** appear among `openspec instructions apply`'s
context files, so whoever implements this change has to open it on
purpose.

Test command: `uv run pytest`. Every test below is named in a form that
command can select individually.

## Baseline

Full baseline, taken before any test here was written:

```
uv run pytest        # at the worktree root
954 passed, 0 failed, 0 skipped — the integration tier included
```

Re-run after this pass, to separate what these tests contribute from
what was already there:

```
uv run pytest --ignore=<the four new files>   # 954 passed, 0 failed
uv run pytest                                 # 27 failed, 958 passed
```

The 954 that passed before still pass. The 27 failures and 4 passes are
this pass's own; each is accounted for below.

`uv run ruff check`, `uv run ruff format --check` and
`uv run lint-imports` (17 contracts kept) all pass. `uv run mypy .`
passes too — the shared asset route is resolved by module name rather
than imported, so its absence is a runtime failure with a message rather
than a type error and a collection error.

## Files written

| File | Covers |
| --- | --- |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_presentation_vocabulary.py` | `playbook-admin` — the action vocabulary, the fault non-suppression, the created-step distinction |
| `tests/unit/launch/infrastructure/driving/test_admin_surface_navigation_and_assets.py` | `playbook-admin` — the header; and the "the admin surfaces load their stylesheet" half of the no-build-step scenario |
| `tests/unit/access/infrastructure/driving/test_roster_admin_presentation_vocabulary.py` | `roster-admin` — both requirements |
| `tests/unit/shared/infrastructure/driving/test_admin_assets_route.py` | `playbook-admin` — the shared guarded asset route |

No existing file was edited, deleted or disabled. **This pass adds tests
and never subtracts.**

Level, in every case: the surface's own routes over a store double,
driven the way a browser drives them — the harness the sibling admin
tests established. The header tests mount both admin routers in one app,
because *Departing from the create surface carries nothing forward*
starts on a `launch` surface and ends with an `access` page being
served, and neither module's routes alone can observe that.

## Scenario coverage

23 scenarios across the two delta specs. 23 accounted for, all covered.

### `playbook-admin` — A step's actions are presented as one affordance vocabulary

| Scenario | Test |
| --- | --- |
| A row's actions share one vocabulary | `test_playbook_admin_presentation_vocabulary.py::test_a_rows_actions_share_one_vocabulary` |
| The destructive action is distinguished, not amplified | `test_playbook_admin_presentation_vocabulary.py::test_the_destructive_action_is_distinguished_not_amplified` |
| A retired step's only action speaks the same vocabulary | `test_playbook_admin_presentation_vocabulary.py::test_a_retired_steps_only_action_speaks_the_same_vocabulary` |
| The vocabulary does not change which actions are offered | `test_playbook_admin_presentation_vocabulary.py::test_the_vocabulary_does_not_change_which_actions_are_offered` |

Plus, for the requirement's prose rather than any scenario —
"Every action **a step's row** offers", not only an active step's:
`test_playbook_admin_presentation_vocabulary.py::test_a_non_active_steps_row_speaks_the_same_vocabulary`.
`tasks.md` 4.2 names this exact trap: `page.html` renders a step row at
two sites, and a draft's row could keep the old vocabulary while every
scenario above passed.

### `playbook-admin` — The vocabulary never suppresses a marked control's fault

| Scenario | Test |
| --- | --- |
| A fault on a disabled automation control is not suppressed | `test_playbook_admin_presentation_vocabulary.py::test_a_fault_on_a_disabled_automation_control_is_not_suppressed` |

### `playbook-admin` — A created step is distinguished on the row the list lands on

| Scenario | Test |
| --- | --- |
| The created step's row is distinguished | `test_playbook_admin_presentation_vocabulary.py::test_the_created_steps_row_is_distinguished` |
| A step created as a draft is distinguished where it renders | `test_playbook_admin_presentation_vocabulary.py::test_a_step_created_as_a_draft_is_distinguished_where_it_renders` |
| A list not naming a created step distinguishes nothing | `test_playbook_admin_presentation_vocabulary.py::test_a_list_not_naming_a_created_step_distinguishes_nothing` |
| A named step the list does not render distinguishes nothing | `test_playbook_admin_presentation_vocabulary.py::test_a_named_step_the_list_does_not_render_distinguishes_nothing` |

Plus, for the requirement's prose — "names one it does not render — a
step the narrowing hides":
`test_playbook_admin_presentation_vocabulary.py::test_a_created_step_the_narrowing_hides_distinguishes_no_row`.

### `playbook-admin` — The page carries a header from which the other admin surface is reachable

| Scenario | Test |
| --- | --- |
| Departing from the create surface carries nothing forward | `test_admin_surface_navigation_and_assets.py::test_departing_from_the_create_surface_carries_nothing_forward` |
| The roster page is reachable from the step list | `test_admin_surface_navigation_and_assets.py::test_the_roster_page_is_reachable_from_the_step_list` |
| The header does not depend on how many steps are shown | `test_admin_surface_navigation_and_assets.py::test_the_header_does_not_depend_on_how_many_steps_are_shown` |
| The authoring surfaces carry the header too | `test_admin_surface_navigation_and_assets.py::test_the_authoring_surfaces_carry_the_header_too` |

### `playbook-admin` — The presentation assets stay behind the admin guard and need no build step

| Scenario | Test |
| --- | --- |
| The stylesheet is refused without an admin session | `test_admin_assets_route.py::test_the_stylesheet_is_refused_without_an_admin_session[vocabulary.css]`, `[pico.min.css]` |
| The stylesheet is served to an admin | `test_admin_assets_route.py::test_the_stylesheet_is_served_to_an_admin[vocabulary.css]`, `[pico.min.css]` |
| No build artifact stands between source and response | `test_admin_assets_route.py::test_no_build_artifact_stands_between_source_and_response[vocabulary.css]`, `[pico.min.css]` — the committed-file half; and `test_admin_surface_navigation_and_assets.py::test_the_admin_surfaces_load_their_stylesheet_with_no_build_step_run` — the "the admin surfaces load their stylesheet successfully" half, over the hrefs the templates actually render |

Plus, for the requirement's own reasoning, which `tasks.md` 1.2a makes
explicit — an **un-injected** `verify` refuses rather than serving:
`test_admin_assets_route.py::test_an_uninjected_guard_refuses_rather_than_serving[vocabulary.css]`,
`[pico.min.css]`.

### `roster-admin` — The page carries a header from which the other admin surface is reachable

| Scenario | Test |
| --- | --- |
| The playbook page is reachable from the roster | `test_roster_admin_presentation_vocabulary.py::test_the_playbook_page_is_reachable_from_the_roster` |
| The header is rendered on a roster holding nobody | `test_roster_admin_presentation_vocabulary.py::test_the_header_is_rendered_on_a_roster_holding_nobody` |

### `roster-admin` — The page's presentation comes from the shared admin vocabulary

| Scenario | Test |
| --- | --- |
| The page carries no styling of its own | `test_roster_admin_presentation_vocabulary.py::test_the_page_carries_no_styling_of_its_own` |
| The stylesheet is refused without an admin session | `test_roster_admin_presentation_vocabulary.py::test_the_stylesheet_is_refused_without_an_admin_session` |
| The destructive action is distinguished, not amplified | `test_roster_admin_presentation_vocabulary.py::test_the_destructive_action_is_distinguished_not_amplified` |
| A deactivated person's action is not destructive | `test_roster_admin_presentation_vocabulary.py::test_a_deactivated_persons_action_is_not_destructive` |
| The create control speaks the same vocabulary | `test_roster_admin_presentation_vocabulary.py::test_the_create_control_speaks_the_same_vocabulary` |

Two sentences of this requirement's prose carry no scenario and are
asserted anyway:

- "SHALL NOT reach the asset through a route belonging to the module
  that owns **the other admin surface**" — inside
  `test_the_page_carries_no_styling_of_its_own`, which fetches the href
  the roster page renders against an app mounting *only*
  `playbook_admin.router` and requires it to find nothing there.
- "the **same** stylesheet the playbook admin surfaces load" — the
  roster half is in the same test (its href must be served by the shared
  router); the playbook half rides
  `test_admin_surface_navigation_and_assets.py::test_the_admin_surfaces_load_their_stylesheet_with_no_build_step_run`,
  which needs the three playbook renderings anyway.

## First-run state, test by test

`testing`'s four states. Recorded because three tests here **pass** on
their first run, and a pass before an implementation exists means one of
two things, neither of which is coverage of new behaviour.

### Failing on a wrong value — the code ran and produced the wrong answer

The page renders, the assertions execute, and what they assert is not
there. 19 tests:

- All five action-vocabulary tests and both positive `just-created`
  tests in `test_playbook_admin_presentation_vocabulary.py`.
- All four header tests in `test_admin_surface_navigation_and_assets.py`.
- All seven tests in `test_roster_admin_presentation_vocabulary.py`.
  Two of these — the header ones — fail inside `_header_of`, which is a
  `pytest.fail` rather than an `assert`, but the page rendered first:
  the failure is "this response carries no such element", not "there is
  nothing to call".

### Failing at the absent target — the assertions never executed

8 tests, all in `test_admin_assets_route.py`: the module
`commerce_ops.shared.infrastructure.driving.admin_assets` does not
exist. These establish that the route is absent and **nothing else** —
whether their assertions are any good is still unverified, and will only
be known once task 1.2 lands.

`test_admin_surface_navigation_and_assets.py::test_the_admin_surfaces_load_their_stylesheet_with_no_build_step_run`
is a mixture and is deliberately ordered so: its "the pages load what
they link" half executes and currently passes (the templates point at
`launch`'s own `/admin/static/`, which serves them); its "and it is the
shared stylesheet" half then hits the absent module.

### Passing on the first run — regression guards, not coverage

Four tests. Each is recorded here so that a green result is not later
read as evidence that this change was implemented.

| Test | Why it passes now |
| --- | --- |
| `test_playbook_admin_presentation_vocabulary.py::test_a_fault_on_a_disabled_automation_control_is_not_suppressed` | The marking already ships (`attribute-faults-to-fields`, archived 2026-08-26) and nothing dims the automation fieldset yet, so there is nothing suppressing anything. The requirement is **negative**; this guards the dim tasks 2.5/2.5a introduce from becoming a hide. |
| `test_playbook_admin_presentation_vocabulary.py::test_a_list_not_naming_a_created_step_distinguishes_nothing` | Nothing carries `just-created` today, so "no row carries it" is trivially true. Guards the marker from over-reaching once it exists. |
| `test_playbook_admin_presentation_vocabulary.py::test_a_named_step_the_list_does_not_render_distinguishes_nothing` | Same. |
| `test_playbook_admin_presentation_vocabulary.py::test_a_created_step_the_narrowing_hides_distinguishes_no_row` | Same. |

The positive counterparts of those three — *The created step's row is
distinguished* and *A step created as a draft is distinguished where it
renders* — do fail on a wrong value, so the marker's introduction is
covered. The three above cover only the rule that it must never outrun
the addressing.

## Assertion classification

### SPECIFIED — traces to a stated requirement

Everything asserted about:

- The literal marker tokens `row-action`, `danger`, `just-created` on
  the controls and rows each scenario names. The deltas give these
  tokens on purpose — "they are what a test is derived from".
- Which control is destructive on each surface (retire; deactivate) and
  which is not (un-retire; reactivate; the roster's create submit).
- That a not-offered move control is still rendered, still inert, and
  still marked.
- That the fault mark on a disabled automation control is rendered, that
  the control stays disabled, and that neither the mark nor the fieldset
  holding it is rendered as not displayed.
- That exactly one row carries `just-created` where a create landed, and
  none where the list names no created step or names one it does not
  render.
- That the header offers the other surface in one action, identifies the
  current one, renders on an empty list and on an empty roster, appears
  on the create and edit surfaces, carries no query forward, and that
  taking it persists nothing on either store.
- That the shared asset route serves the committed bytes to an admin and
  answers an anonymous caller exactly as an unregistered route does;
  that an un-injected guard refuses; that the asset is tracked in git.
- That the roster page carries no `<style>` element and that its
  stylesheet is served by the shared route and not by `launch`'s.

### DERIVED — inferred, no stated requirement covers it

Each is labelled `DERIVED` in the test source at the point it is
asserted, and each is a guard against a **vacuous** pass rather than a
new constraint on behaviour:

| Derived assertion | Where | Why |
| --- | --- | --- |
| A step's row offers at least 3 action controls | `test_a_rows_actions_share_one_vocabulary` | A row rendering one control would satisfy the sweep while offering nothing to speak a vocabulary about. |
| The middle-of-gate row's move controls are all live | `test_the_vocabulary_does_not_change_which_actions_are_offered` | Otherwise "the head row's move is inert" is satisfied by a page whose reorder controls are all dead. |
| The created draft really landed with status `draft` | `test_a_step_created_as_a_draft_is_distinguished_where_it_renders` | Otherwise the row read might be the served site rather than the non-active one. |
| The gate filter really hides the named step | `test_a_created_step_the_narrowing_hides_distinguishes_no_row` | Otherwise the test never reaches the case it was written for. |
| The search really matches no step | `test_the_header_does_not_depend_on_how_many_steps_are_shown` | Same. |
| The roster really holds nobody | `test_the_header_is_rendered_on_a_roster_holding_nobody` | Same. |
| The asset really is served to an admin | the two refusal tests | Otherwise the refusal says nothing about a guard — a dead route refuses everyone. |

An implementer who finds one of these in the way should say so rather
than editing it; none of them traces to a requirement, and changing one
is a decision, not a repair.

### Deliberately untested — identified and knowingly left uncovered

Each is a manual verification task in `tasks.md`, and `design.md` —
Goals states the policy: where a guarantee is genuinely about what an
admin *sees* and no response carries a proxy, it is a manual check and
never a scenario. Writing an assertion that pretended otherwise would be
worse than the gap.

| Not tested | Reason | Carried by |
| --- | --- | --- |
| That a row's actions sit on one line, share one weight, and that retire is not the most prominent control | No response carries layout or visual weight. The `row-action` / `danger` markers pass for any stylesheet, including one leaving retire loudest. | `tasks.md` 7.7 |
| That the fault on a dimmed automation fieldset stays **as legible as** the surface's ordinary text | A dim is a computed style. Only "not displayed" is assertable, and only that is asserted. | `tasks.md` 7.6 |
| Table density — one row per step, a scannable gate, the page far short of ~23,000px | No test tier here can measure a rendered row's height. | `tasks.md` 7.4 |
| Whether the roster page carries inline `style=` **attributes** | The scenario says "carries no page-local style **block**", and the requirement's target is the nine-line `<style>` block the page ships today. Asserting the absence of every inline attribute would oblige an implementer to a constraint nobody stated. | Nothing; recorded as a knowing gap |
| The traversal guard `tasks.md` 1.3 asks be copied verbatim | Every probe that would exercise it is normalised away before the route sees it: `TestClient` unquotes the path, so `..%2Ffoo` arrives as two segments and never matches the single-segment route, and a bare `..` is collapsed by the client. A test would pass on the router's own path matching rather than on the guard — a pass for the wrong reason. | Code review of task 1.3 |
| That no template still references `/admin/static/pico.min.css` | `design.md` — Risks assigns this to a grep, not a scenario. The stylesheet test catches the *consequence* (a page linking something the shared route does not serve), which is the part a response can show. | `tasks.md` 7.2 |
| A rendering invariant for a mark nested inside a not-offered element | `tasks.md` 5.2 says outright not to write one, and `design.md` records why: a *reworded* rule produces no mark at all, and a rule *added* would be missing from the provocation sweep anyway. Not written. | `tasks.md` 5.2 (a negative task — no test, no diff) |

## Obsolete tests

**Not applicable.** Every requirement in both delta files is `ADDED`;
neither delta carries a `MODIFIED`, `REMOVED` or `RENAMED` requirement
operation, so no existing requirement is superseded and no existing test
can be bearing on superseded behaviour. `proposal.md` says the same in
its own words: the change "removes no action, changes no write, and
alters no narrowing".

For completeness, and because the change does rewrite templates a large
existing suite asserts markup against, a bounded search was run anyway
across the dispatched test-path glob (`tests/**/test_*.py`) for anything
that would conflict — tests referencing `row-action`, `danger`,
`just-created`, a `<style>` element, an inline `style` attribute, `pico`,
`/admin/static`, a stylesheet link, or `/admin/roster`. **No such test
exists** — not "none was found": every one of those greps returned
nothing at all across the whole glob. No earlier `test-manifest.md` path
was supplied to this pass, so none was consulted.

If the restyle nonetheless turns an existing test red, that is a
regression in the restyle, not a superseded test. Do not edit it.

## Unresolved project questions

No channel exists to ask on, so each is recorded with the assumption
taken and the tests that depend on it. A correction point is named for
each, so that a wrong assumption is fixed in one place rather than
across a file.

| Question | Assumption taken | Depends on it | Correction point |
| --- | --- | --- | --- |
| How is "carries the marker `X`" spelled in the response? The deltas say only "marker". | A **class token** on the element, per `design.md` — *Actions become one row of same-weight controls, marked in the response*, which writes `class="row-action"` and `class="row-action danger"`. | Every marker test in files 1 and 3 | `_carries` in both files |
| What counts as an "action control"? | `a[href]`, `button`, `input[type=submit\|image]`, or any element with `role="button"`. A `<select>` submitting itself through an `hx-*` attribute is **not** swept — an under-reach, not a false pass. | The vocabulary sweeps in files 1 and 3 | `_is_action_control` |
| How is one action told from another? | The enclosing form's `action` and hidden fields, plus the control's own `href`, `formaction`, `name`, `value`, label and text. A `<select>`'s option labels are excluded, so a status control offering a `retired` option is not mistaken for the retire action. | `test_the_destructive_action_*`, `test_a_retired_steps_only_action_*`, `test_the_vocabulary_does_not_change_*`, the roster's three marker tests | `_control_haystack`, `_RETIRE_HINTS`, `_UNRETIRE_HINTS`, `_MOVE_HINTS`, `_DEACTIVATE_HINTS`, `_REACTIVATE_HINTS` |
| Where does a step's row begin and end? | The element carrying `id="step-<identifier>"` (which `design.md` — Context records already exists), else the one `<tr>` naming the step. | Every row-scoped test in file 1 | `_row_of` |
| Where does a person's row begin and end? | The smallest element naming that person, offering at least one action control, and naming nobody else. | The roster's three row tests | `_person_row` |
| What **is** the header, structurally? | The smallest element that links to the other admin surface, names this one, and does not enclose the page's own tables or forms. The last clause matters: without it, a step table's "Step" column heading reads as the header naming the current surface. | All six header tests | `_header_of` |
| What words name each surface? | `("playbook", "step", "steps")` and `("roster", "people", "person")`. The deltas fix that both surfaces are named, not the wording. | All six header tests | `_PLAYBOOK_WORDS`, `_ROSTER_WORDS` (kept identical in both files; they correct together) |
| How is "identifies the surface currently viewed" read off a response? | Somewhere in the header, the current surface is named by something that either carries `aria-current`/`data-current`/a current-ish class, or is not rendered as a link at all. That is the structural reading of "reads as a position rather than as an undifferentiated pair of links". `design.md`'s choice — the current one identified rather than linked — satisfies it. | `test_the_roster_page_is_reachable_from_the_step_list`, `test_the_authoring_surfaces_carry_the_header_too`, `test_the_playbook_page_is_reachable_from_the_roster` | `_identifies_current`, `_CURRENT_ATTRIBUTES`, `_CURRENT_CLASSES` |
| Is `pico.min.css` inside the asset requirement, or only `vocabulary.css`? | Both. The requirement's last paragraph says "This is a constraint on the whole vocabulary, not on one file", and "the vendored assets the playbook page already loads keep this guarantee unchanged"; `tasks.md` 1.1 moves pico into the shared directory. So the guard and served-bytes scenarios are parametrised over both. A guard applied to the new stylesheet while pico moved out from behind `launch`'s guard and lost it would satisfy the scenario as written. | All eight tests in file 4 | `_SHARED_ASSETS` |
| Where are the shared assets committed? | `src/commerce_ops/shared/infrastructure/driving/static/`, per `tasks.md` 1.1 and `proposal.md` — Impact. | `test_the_stylesheet_is_served_to_an_admin`, `test_no_build_artifact_stands_between_source_and_response` | `_ASSET_DIR` |
| What are the shared route's module name, router attribute and guard seam? | `commerce_ops.shared.infrastructure.driving.admin_assets`, `router`, and a module-level `verify` the composition root injects — `tasks.md` 1.2 states all three. It is a task, not a spec, so it is recorded here rather than treated as fixed behaviour. | All eight tests in file 4, plus the shared-stylesheet half of file 2's asset test and file 3's two asset tests | `_ROUTE_MODULE_NAME` / `_ASSETS_MODULE_NAME` |
| How is "committed to the repository" established? | `git ls-files --error-unmatch`. Where `git` is not on `PATH` the test **skips** with a reason naming the file to check by hand, rather than passing silently. | `test_no_build_artifact_stands_between_source_and_response` | that test's own `shutil.which` branch |
| May a test in `tests/unit/launch/…` import an `access` module (and vice versa)? | Yes. `import-linter` governs `src` only (17 contracts, all kept), `main.py` composes exactly these routers, and one scenario cannot be observed without both. No project convention records an answer either way. | `test_admin_surface_navigation_and_assets.py` (all five), `test_roster_admin_presentation_vocabulary.py::test_the_page_carries_no_styling_of_its_own` | the module-level imports of those two files |
| Should the shared route be imported at the top of a test file, or resolved by name? | Resolved by name. A hard import makes its absence a **collection error**, and pytest stops the whole run on one — which would leave the 954 tests unrelated to this change unreported while it is missing. Each test still reports the absent-target state, with a message saying so. | Files 2, 3 and 4 | `_assets_module` in each |

## Corrected during implementation

One assertion in this pass was unsatisfiable by any implementation and was
corrected rather than worked around. Recorded here because the section
below tells implementers not to edit a SPECIFIED assertion, and this was
one.

`test_admin_surface_navigation_and_assets.py::test_departing_from_the_create_surface_carries_nothing_forward`
asserted `surfaces.roster.saves == []`. That file's own roster fixture
seeds its store **through the write path** — `_build_roster_store` calls
`create_person(roster=store, …)`, which calls `store.save` — so the double
already holds one save before a `TestClient` exists. Reproduced in
isolation: one entry, the seeded `Alice Admin` record at
`expected_version=13`. The sibling assertion one line above passes only
because `_seeded_store` builds `_Record`s directly instead of writing.

The scenario's meaning is a difference across the navigation, not an
absolute count, so the test now snapshots both stores' save counts before
anything is driven and requires them unchanged after — with
`_open_create` inside the span, so rendering the create surface is held to
the same standard as departing from it. Nothing else in the test moved,
and no assertion was weakened: a write during either step still fails it.

## For whoever implements this next

- Run `uv run pytest <file>::<test>` to work one task at a time; every
  test above is individually selectable.
- Nothing in this manifest is a task list. `tasks.md` is. In particular
  `tasks.md` 5.1 and 5.2 are **negative** tasks — they produce no test
  and no diff, and no test here corresponds to them.
- If a test's *discovery* fails rather than its assertion — a
  `pytest.fail` naming a correction point — that is this file's
  vocabulary being wrong about the implemented page, not the page being
  wrong. Correct the named helper. If a test's **assertion** fails,
  that is the code. Do not edit an assertion to match what the code
  produced; a specified assertion that does not match means the code is
  wrong.
