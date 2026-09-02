## 1. Amend the program plan

Line numbers are against `main` at `d1ee1fa`; re-resolve each by its quoted text rather than trusting the number if the file has moved.

- [ ] 1.1 In `docs/playbook-program.md:380`, mark the rename bullet done — `rename-the-roster-to-members` merged as PR #152 — rather than "implemented and awaiting merge"
- [ ] 1.2 Split the plan's role table in two (design Decision 13): a **positions** table carrying the eleven slugs, titles and seeded statuses, and a **discipline-to-role seed map** carrying the eight discipline rows and the "every one of the 358 steps is covered and none is counted twice" completeness argument that belongs to it
- [ ] 1.3 Change "Roles are a managed collection, seeded with nine" (`:194`) to eleven, state the seeded-status rule — active where Change 3 assigns steps, draft where the position owns none — and correct "What the nine below are is a *starting set*" (`:197`) with it
- [ ] 1.4 Correct "seeding the nine roles and pointing every default at the bootstrap admin" (`:221`): eleven roles, of which three point at nobody, and the holder is the **seeding administrator** as `roles` resolves it, not "the bootstrap admin" — which names nobody on an already-administered membership
- [ ] 1.5 Resolve the "**Open:** whether capital commitments want a tenth role — *Managing Director*" note (`:263`) as decided, and record that `it` joined with it
- [ ] 1.6 Resolve H7 in the hazards table (`:568`) — a member may hold several roles; note that the self-confirmation split it implies belongs to Change 2
- [ ] 1.7 Record at `:215` and `:399` that **both** halves of "a retired role takes no new assignments while the steps still naming it are reported rather than failing a load" belong to Change 2, not here, since nothing in this change can assign anything to a role; and correct the stale `launch-playbook:513` citation at `:425` to `:414` (its load-time enumeration being at `:1060` and `:1098`), which otherwise scopes Change 2 against a blank line

## 2. The role model

- [ ] 2.1 Add a `Role` entity to `access/domain/` carrying slug, title, status and holders, with slug-format validation (non-empty, no surrounding whitespace, lowercase letters/digits/single interior hyphens, begins and ends alphanumeric)
- [ ] 2.2 Add the role status vocabulary — `draft`, `active`, `retired` — and the four permitted transitions from design Decision 5, refusing every other transition including any return to `draft`
- [ ] 2.3 Express the holder rules in the domain: a member appears at most once per role, the default is one of the holders, and at most one holder is the default
- [ ] 2.4 Express the active-role obligation: an `active` role has a default holder who is an active member; `draft` and `retired` roles are exempt
- [ ] 2.5 Collect faults rather than raising on the first, matching how the membership reports every fault at once

## 3. Role persistence

- [ ] 3.1 Add `RoleRow` and `RoleHolderRow` to `access/infrastructure/driven/models.py` per design Decision 9, with attribution columns mirroring `MemberRow`'s exactly
- [ ] 3.2 Add the `CHECK` constraint on status and the partial unique index enforcing at most one default holder per role in the database
- [ ] 3.3 Write the Alembic migration creating both tables; alter no existing table
- [ ] 3.4 Add a roles repository beside `members_repository.py`, reading and writing whole roles
- [ ] 3.5 Make role writes take the existing `members_set` version row (design Decision 8), and update its docstring to say it serializes the `access` module's writes rather than the membership's alone

## 4. Role write use cases

- [ ] 4.1 Add create, update (title only), retire and un-retire use cases in `access/application/`, each validating whole and recording attribution. `create` takes the role's initial status and, where that status is `active`, its default holder in the same write — never composed as create-draft then add-holder then activate, which would record an activation no admin performed
- [ ] 4.2 Add add-holder, remove-holder and move-default use cases, refusing removal of an active role's default and never promoting a holder implicitly
- [ ] 4.3 Refuse a slug in `update`, the way the membership refuses a Slack identity
- [ ] 4.4 Refuse activation — from `draft` or from `retired` — where the role has no default holder who is an active member
- [ ] 4.5 Refuse adding a deactivated member as a holder
- [ ] 4.6 Export the role use cases and their result types from `access/application/__init__.py`'s `__all__`

## 5. The member/role invariant

- [ ] 5.1 Extend member deactivation to refuse when the member is the default holder of one or more `active` roles, naming **every** such role in the refusal, not the first
- [ ] 5.2 Confirm the new refusal composes with the last-active-admin refusal — a write blocked by both reports both faults together
- [ ] 5.3 Confirm a member who is the default of `draft` or `retired` roles only, or who holds active roles without being their default, deactivates freely

## 6. Seeding

- [ ] 6.1 Extend `seed_admin` to seed the eleven roles after the admin is established, attributed to the same reserved system principal
- [ ] 6.2 Resolve the **seeding administrator** — the member the admin seeding established on this run, else the earliest-created active admin with ties broken by identifier — and confirm the resolution is total: `members`:88 has the admin seeding alter nothing only when an active admin already exists, and where none exists that step has already failed the chain
- [ ] 6.3 Seed the eight discipline roles `active` with the seeding administrator as sole holder and default, and the four remaining roles `draft` holding nobody, per design Decision 7's table
- [ ] 6.4 Confirm the seed alters no membership entry and confers nothing on the seeding administrator, leaving `members`:88's guarantee that the bootstrap variable confers nothing untouched
- [ ] 6.5 Make the seed add-only: a slug already present is left exactly as it stands, whatever its title, status or holders
- [ ] 6.6 Fail the step, rather than passing silently, where the role store cannot be read or written
- [ ] 6.7 Verify the seed is idempotent by running the step twice against the same database and confirming the second run changes nothing

## 7. The Roles admin surface

- [ ] 7.1 Add the Roles list page — every role on one page, grouped so `active`, `draft` and `retired` are set apart and never interleaved, each row showing title, slug and default holder and carrying no action controls
- [ ] 7.2 Make each role's title link to that role's own page, and leave the slug readable but not a second link
- [ ] 7.3 Add the create page, taking slug, title, initial status and — where the status is `active` — the default holder in one submission
- [ ] 7.4 Add the role's own page: correct the title, add and remove holders, move the default, and offer only the status transitions permitted from the role's current status
- [ ] 7.5 Present the role's slug as an unchangeable value, not an input, and present its attribution the way the member's page presents a member's
- [ ] 7.6 Re-present the submitted form with every fault and the typed values on rejection, without returning to the list, and surface each refused transition with its own explanation rather than a generic one
- [ ] 7.7 Add the Roles entry to the shared `_admin_header.html` partial, and confirm every other admin surface's header picks it up through the existing "a surface added later is named by the header" requirement
- [ ] 7.8 Give the create page and each role's own page a breadcrumb naming the Roles list as a link and the page itself as the current un-linked segment, rendered as the page's own title — the header identifies the current surface as a position, not a link, so it does not serve this
- [ ] 7.9 Carry the shared admin stylesheet with no page-local style block; mark every action control `row-action` and only **Retire** additionally `danger`

## 8. Rebuild the Team surface

- [ ] 8.1 Reduce the Team list to a read-only listing whose display-name column links to the member's own page, with no action controls on any row
- [ ] 8.2 Move creating a member onto its own page, reached from the list in one action, and remove the full-width create form from the top of the list
- [ ] 8.3 Add the member's own page carrying editing, deactivation and reactivation, and move the entry's attribution onto it
- [ ] 8.4 Surface the role-blocked deactivation refusal on the member's page naming every blocking role
- [ ] 8.5 Delete the `td.actions form { display: contents }` rule together with the row actions it worked around, and confirm no rule matching nothing is left behind
- [ ] 8.6 Give the create page and each member's own page a breadcrumb naming the Team list as a link and the page itself as the current un-linked segment, matching the roles surface and the shipped step pages
- [ ] 8.7 Render the shared admin header on all three Team pages, not only the list — a create page or member's page without it is a page from which the rest of the admin is unreachable
- [ ] 8.8 Move the `row-action` and `danger` markers onto the create page and the member's page, leaving rows carrying neither

## 9. Presentation pass

- [ ] 9.1 Run the local preview server and walk both surfaces with the user turn by turn, rather than proposing a layout in prose
- [ ] 9.2 Settle the Team list's column order with the user — identity-first or name-first — noting that the admin's three existing tables disagree and that whichever is chosen, aligning the others is separate mechanical work
- [ ] 9.3 Confirm by direct inspection of the rendered pages what a server response cannot establish: that rows read as one line and the status groups are visually distinct

## 10. Tests

- [ ] 10.1 Unit tests for the role entity: slug validation, transitions, holder-set rules, the active-role obligation, and multi-fault reporting
- [ ] 10.2 Unit tests for each role write use case, including every refusal
- [ ] 10.3 Unit tests for the extended member deactivation, including the both-refusals-together case
- [ ] 10.4 Unit tests for the seed: the eleven seeded from empty, an edited slug left alone, absent slugs added, and the unusable-store failure
- [ ] 10.5 Unit tests for the seeding administrator on **both** branches — a freshly seeded admin, and an already-administered membership where the admin seeding altered nothing — plus determinism across two runs where several active admins exist
- [ ] 10.6 Integration tests for the roles repository and the version-row serialization, against a real database
- [ ] 10.7 Integration tests for both admin surfaces' routes, including the refused transitions and the guard on the stylesheet
- [ ] 10.8 Tests for the navigation the rebuild adds: the breadcrumb on all four new sub-pages with its linked and current segments, the shared header on the two new Team pages, and both reachable without scripting
- [ ] 10.9 Confirm each gate actually **fires** before trusting that it passes — assert the failing case fails, not only that the passing case passes

## 11. Verification

- [ ] 11.1 `uv run ruff check` and `uv run ruff format --check`
- [ ] 11.2 `uv run mypy`
- [ ] 11.3 `uv run pytest tests/unit tests/agents`
- [ ] 11.4 `uv run import-linter` — all contracts, confirming no new module boundary was crossed
- [ ] 11.5 Clone `commerce_ops_test` into a worktree-local database (`CREATE DATABASE … TEMPLATE commerce_ops_test`) and name it in `.env.test`; do not migrate the shared clone
- [ ] 11.6 Run the integration tier with `COMMERCE_OPS_REQUIRE_DATABASE=1` so a skipped test fails rather than passing silently
- [ ] 11.7 Upgrade the migration, inspect, downgrade, and re-inspect against that clone
- [ ] 11.8 Confirm the container start chain still reaches healthy, given the Dockerfile's `start-period` is tuned to its length

## 12. Review and archive

- [ ] 12.1 Run `/code-review` over the change's diff before treating the change as done, per `AGENTS.md`
- [ ] 12.2 Archive with `openspec archive rebuild-the-member-directory --yes` as the last commit before the merge, folding the deltas into `openspec/specs/`
