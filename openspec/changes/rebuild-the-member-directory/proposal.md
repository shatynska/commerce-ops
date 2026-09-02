## Why

`docs/playbook-program.md` makes this Change 1, and two later changes are
blocked on it: `assign-steps-by-role` gives `assignees` and `confirmer` a role
reference, and `activate-the-seeded-step-set` seeds 358 steps against one.
Neither can start while roles do not exist. `move-principals-to-roster` put
roles out of scope explicitly, to be added "when there is behavior to hang on
it" — steps assigned by role is that behaviour, and it is now next.

Separately, the Team page is the last admin surface still editing in a table
cell. Its `actions` column holds two `<form>`s containing three unlabelled
`<input>`s, worked around by a `td.actions form { display: contents }` CSS
hack, while `move-step-actions-into-step-pages` already replaced that pattern
for steps with a row that links to the record's own page. Adding a second
managed collection to the same surface is the moment to stop copying the
pattern this change exists to undo.

The rename half of this change landed separately as
`rename-the-roster-to-members`, so what remains is roles, role management and
the page rebuild.

## What Changes

- **Roles become a managed collection.** A role carries an immutable slug, an
  editable title, a lifecycle status, and its holders — exactly one of them the
  default. The slug is what steps will store and what a vendored file can name,
  so it is chosen once and never changed; the title is free to correct. This
  deliberately differs from a member, whose identifier is a generated `uuid4`
  precisely so it can never be re-pointed at a different human.
- **Three statuses: `draft`, `active`, `retired`.** Only an `active` role must
  have a default holder — a `draft` role may have none, which is what lets the
  directory record a position the company intends to staff but has not. This
  mirrors `launch-playbook:503`, which binds only an *active* human step to
  name an assignee. From a step's side `draft` and `retired` are identical:
  neither takes an assignment. They differ only in the holder obligation.
- **Four rules, three of them mirroring ones `members` already carries.** An
  active role always has a default holder; removing the default while other
  holders remain is refused rather than auto-promoting one of them; a role is
  retired, never deleted, and keeps its holders when retired; and a member may
  not be deactivated while they are the default holder of an active role, the
  refusal naming every such role at once.
- **Twelve roles are seeded**, by the same `seed_admin` step that seeds the
  first admin — roles must exist before steps can reference them, and the
  container chain already runs `seed_admin` before `seed_playbook`. The eight
  discipline-owning roles seed `active` holding the **seeding administrator**;
  `operations`, `managing-director`, `it` and `analytics` seed `draft` and
  unstaffed, because none owns a step today and seeding them active would
  assert a position is filled when it is not.
- **The seeding administrator is resolved, not assumed.** "The bootstrap admin"
  names nobody on an already-administered membership — `members` has the admin
  seeding alter nothing *only where* the membership already holds an active
  admin, which is the branch the first deployment of this change takes. So the seed resolves the
  member the admin seeding established on this run, else the earliest-created
  active admin; the second branch always resolves, because it is defined by an
  active admin existing. The seed alters no membership entry and confers
  nothing.
- **Roles are created, renamed and retired from the admin** — a list page, a
  create page and a role's own page, with holders added and removed and the
  default moved there. The create page and a role's own page carry a breadcrumb
  back to the list, which the header does not supply.
- **The Team page is rebuilt** to the pattern `move-step-actions-into-step-pages`
  shipped for steps: a read-only list whose name column links to the member's
  own page, with adding on its own page and editing, deactivating and
  reactivating on the member's page. The `display: contents` hack goes with it.
- **`docs/playbook-program.md` is amended** in seven places across four
  sections, listed in `design.md` Decision 12: the role seed is twelve rather
  than nine (three separate statements of it), its default holder is the
  seeding administrator rather than "the bootstrap admin", the *Managing
  Director* question it leaves open is decided, H7 is resolved, the retired-role
  assignment rule is marked as Change 2's, and the rename bullet becomes done
  now that `rename-the-roster-to-members` has merged. One further correction is
  not a supersession: the plan cites the self-confirmation rule as
  `launch-playbook:513`, which is a blank line.

Not in this change: resolving a step's assignee through a role, and the
discipline-to-role map the seeded step set uses. Both belong to Changes 2 and
3, which this one unblocks.

## Capabilities

### New Capabilities

- `roles`: the role collection — slug, title, status, holders and default
  holder — as Postgres-backed data edited only through validated, attributed
  writes, with its lifecycle and holder rules and its seeding step.
- `roles-admin`: the admin surface's Roles pages — roles listed, created,
  renamed, retired and un-retired from the browser, holders managed and the
  default moved, on the same authenticated admin surface the Team page rides.

### Modified Capabilities

- `members`: member deactivation gains a second refusal — a member who is the
  default holder of an active role may not be deactivated — alongside the
  existing last-active-admin refusal, which it composes with rather than
  replaces. This is an added requirement, not a changed one: deactivation for a
  member holding no active role's default behaves exactly as it does today. The
  existing seeding requirement is likewise unchanged — it never claimed the step
  seeds nothing else, so `roles` states the role seeding from its own side.
- `members-admin`: the Team page becomes a read-only list linking to each
  member's own page; creating moves to its own page, and editing, deactivating
  and reactivating move onto the member's page. The header requirement is
  **widened** from "The Team page" to the surface's three pages — a create page
  or member's page rendered without it would be a page from which the rest of
  the admin is unreachable. Its "a surface added later is named by the header"
  clause has its obligation exercised rather than changed, the Roles surface
  being the case in point. The capability also gains an **added** requirement:
  the create page and each member's own page carry a breadcrumb back to the
  list, which the header does not supply.

## Impact

- **`access` module**, all three layers: a role entity and its rules in
  `domain`, write use cases and ports in `application`, a repository, models
  and the admin adapter in `infrastructure`. `application/__init__.py`'s
  `__all__` surface grows.
- **Schema**: new tables for roles and their holders, with an Alembic
  migration. Existing members tables are unchanged.
- **`seed_admin`**: seeds the twelve roles after the first admin, in the same
  step. The Dockerfile's healthcheck `start-period` is tuned to this chain's
  length and its comment records `seed_playbook` having broken the probe when
  it joined; twelve inserts should not move it, but the file records the
  sensitivity.
- **Admin templates**: `team.html` rebuilt and split into per-member pages, new
  role templates, a breadcrumb on each of the four new sub-pages, the shared
  `_admin_header.html` partial gains a Roles entry and is rendered on them,
  and the shared admin stylesheet absorbs whatever `display: contents` was
  working around.
- **Tests**: unit tests for the role rules and the seed, and integration tests
  for the repository and the admin routes.
- **`docs/playbook-program.md`**: amended as described above.
