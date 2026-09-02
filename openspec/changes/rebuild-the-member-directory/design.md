## Context

See `proposal.md` — Why. What shapes the approach below:

- **`docs/playbook-program.md` is the source, and this change supersedes parts
  of it.** The plan seeds nine roles, leaves *Managing Director* open, and
  marks H7 unresolved; all three are decided here. The plan says it "is not a
  specification: authoritative behaviour lives in `openspec/specs/`", so the
  specs win — but a plan left contradicting the repository is the fault the
  plan itself indicts in `playbook_v1.yaml`, so it is amended rather than left.
- **`members` already carries the rules roles will mirror.** Deactivated never
  deleted, a floor that refuses a write leaving the collection incoherent,
  every write validated whole and attributed, and one optimistic version row
  serializing them. Roles borrow all four rather than inventing anything.
- **`move-step-actions-into-step-pages` shipped the page pattern.** A row that
  links to the record's own page, every action on that page, and the markers
  observed there. The Team page is the last surface that predates it.
- **The `access` module holds the membership.** `MemberRow` and `MembersSet`
  are in `access/infrastructure/driven/models.py`; writes go through
  `access/application/members.py`.

## Goals / Non-Goals

**Goals:**

- A role collection with the same write discipline the membership has, such
  that Change 2 can resolve a step's assignee through it and Change 3 can seed
  358 steps against it.
- A member/role invariant that cannot be broken by two concurrent writes.
- One admin pattern across both collections, so adding the second surface does
  not add a second way of doing things.

**Non-Goals:**

- Resolving a step's assignee or confirmer through a role — Change 2.
- The discipline-to-role map the seeded step set uses — Change 3. This change
  seeds the role *list*; the mapping from a step's discipline to a role is a
  separate artifact and is not written here.
- "A retired role takes no new assignments." The plan lists this among this
  change's rules, but nothing in this change can assign anything to a role.
  It lands in Change 2 with the assignment it constrains.
- Splitting `launch-playbook:414`'s self-confirmation check into load-time and
  resolution-time halves — the consequence of H7, and Change 2's. The program
  plan cites this rule as `:513`, which is a blank line; the rule is at `:414`,
  with its load-time enumeration at `:1060` and `:1098`. Task 1.7 corrects the
  plan's citation while §1 is amending it.

## Decisions

### 1. Roles live in `access`, beside the membership, not in a module of their own

The rule "a member may not be deactivated while they are the default holder of
an active role" spans both collections. Inside one module it is an ordinary
invariant a use case checks. Across a module boundary it becomes a distributed
constraint — `members` would have to ask a `roles` module a question mid-write,
and `.importlinter`'s contracts would record a dependency that the invariant
makes bidirectional in practice.

*Alternative considered:* a `roles` module with its own public surface. Rejected
because the cross-collection invariant is not incidental — it is the reason
roles exist as first-class data rather than as strings on a step. Two modules
would have to share a transaction and a version row anyway, which is the
definition of one consistency boundary.

The capability specs stay separate (`roles`, `roles-admin`) because a
capability is a behaviour contract, not a module — `members` and
`members-admin` already split one module across two specs.

### 2. The slug is the identifier; no generated id is issued

`members` generates a `uuid4` precisely so an identifier can never be
re-pointed at a different human. A role inverts both halves of that reasoning:
a step will *store* the slug, and a vendored file must be able to *name* it in
advance, so it must be stable and human-chosen. A generated id would be
neither, and would force every role reference through a lookup that buys
nothing.

The consequence accepted: correcting a badly chosen slug is impossible, and the
only remedy is retiring the role and creating another. That is the same trade
steps already make with `lp.strategy.001`, and it is why the title is editable —
the wrong *word* is free to fix, only the wrong *key* is not.

### 3. Three statuses, and `draft` earns its place by one obligation

From a step's side `draft` and `retired` are identical: neither takes an
assignment. They differ in exactly one thing — **only an `active` role must
have a default holder** — which is what lets the collection record a position
the company intends to staff but has not. This mirrors `launch-playbook:503`,
which binds only an *active* human step to name an assignee.

*Alternative considered:* two statuses, `active` and `retired`. Rejected
because the seed then has to point four unstaffed positions at the seeding
administrator, which both asserts they are filled and pins that member as the
default holder of twelve roles on day one (see Decision 7).

Roles get three where steps have four; `in-development` has no counterpart here
because a role has no work to be in development on.

### 4. Holders are a set from the first commit, not a single field deferred

An earlier reading of this change deferred non-default holders to Change 2 on
the grounds that nothing resolves through them until the picker exists. That
was reversed, and the reason is spec shape rather than schema cost.

With a single `holder` field this change would state *"an active role always
has a holder"*, and Change 2 would have to issue a **MODIFIED** delta turning it
into *"at least one holder, exactly one of them the default"*. A MODIFIED delta
on a requirement written one change earlier re-arms the test writer over
behaviour that already has coverage and hands the reviewer two prose blocks to
diff by eye — the same anti-informative churn that earned
`rename-the-roster-to-members` its `skip_specs: true`. The column rename it
would have avoided is four lines.

The "nothing reads it yet" objection also fails on inspection: **role management
is in this change**, so the role's own page reads and edits the holders from the
first commit. What Change 2 adds is the *picker*, not the first reader.

The set also collapses two rules into one. With a single holder, "an active role
always has a holder" and "a member may not leave while holding the last one"
are two statements; with a set, a sole holder is necessarily the default, so
**refuse if the member is the default holder of an active role** covers both.

### 5. Four transitions, and none returns to `draft`

```
        ┌─────────┐   activate    ┌──────────┐
        │  draft  │──────────────▶│  active  │
        └─────────┘               └──────────┘
             │                          │
             │ retire           retire  │
             │                          ▼
             │                    ┌───────────┐
             └───────────────────▶│  retired  │
                                  └───────────┘
                                        │
                                        │ un-retire
                                        └──────────▶ active
```

`draft → retired` is permitted deliberately, reversing an earlier inclination to
forbid it as meaningless. The collection offers **no deletion**; without this
transition a position sketched and then abandoned would sit in the draft group
forever with no way to clear it, and the draft list would grow monotonically.
`retired` is what the collection has instead of deletion, so an abandoned sketch
belongs there.

Nothing returns to `draft`: once a role has been in play, `retired` records that
it no longer is, and a return to `draft` would erase that distinction.

Entering `active` from either side requires a default holder who is an **active
member**. The retired-side check is not redundant: a retired role keeps its
holders unenforced, so its default may have been deactivated in the meantime.

### 6. No holder is ever promoted to default implicitly

Removing an active role's default is refused rather than silently promoting
another holder. A promotion the system chose would name a person nobody picked,
and would do it in the one place — who is accountable for this position — where
guessing is least acceptable. The admin moves the default first, or retires the
role.

*Alternative considered:* promote the longest-standing holder. Rejected: it is
an arbitrary rule presented as a policy, and its result is indistinguishable
from a deliberate choice when read back a month later.

### 7. Twelve roles seeded, eight `active` and four `draft`

| Slug | Title | Status | Why this status |
|---|---|---|---|
| `supply-chain` | Supply Chain Manager | `active` | Change 3 assigns steps to it |
| `ppc` | PPC Manager | `active` | " |
| `brand` | Brand Manager | `active` | " |
| `catalog` | Catalog Manager | `active` | " |
| `controller` | Financial Controller | `active` | " |
| `creative` | Creative Manager | `active` | " |
| `customer-service` | Customer Service Manager | `active` | " |
| `marketing` | Marketing Manager | `active` | " |
| `operations` | Operations Manager | `draft` | owns no step; no step names a confirmer today |
| `managing-director` | Managing Director | `draft` | the plan's open tenth role, decided in |
| `it` | IT Manager | `draft` | a position the company may not have staffed |
| `analytics` | Data Analyst | `draft` | " |

The eight are active because Change 3 seeds 358 steps against them and
`launch-playbook:503` requires an active step to name an active assignee — they
must be assignable from the first boot. The four hold nobody because none owns a
step, and seeding them active would assert a position is filled when it is not.

The second reason is mechanical and matters more than it looks: every active
role's default at seed is the seeding administrator, and a member cannot be
deactivated while holding an active role's default. Twelve active roles pin
that member on day one and require twelve deliberate actions to release
them. Eight is already the floor Change 3 forces; adding four more for
completeness would be paying that cost for nothing.

**`operations` is the debatable one.** The plan names it the cross-cutting
confirmer role, which is a function in the framework the other three lack. It
seeds `draft` anyway because the plan also records that **none of the 358 steps
names a confirmer**, so it owns nothing until Change 2 gives some step one — at
which point activating it is a single admin action taken by someone who knows
who actually confirms. Seeding it active would mean guessing that now.

**Who holds the eight is not simply "the bootstrap admin".** That phrase has no
referent on the branch every already-administered deployment takes — including
the first deployment of this change against the existing production database.
`members`:88 has the admin seeding *alter nothing* whenever the membership
already holds an active admin, so on that branch it establishes no member for
the roles to point at:

```
  membership has no active admin          membership has an active admin
  ──────────────────────────────          ──────────────────────────────
  admin seed creates or promotes          admin seed alters nothing,
  an entry                                variable confers nothing
            │                                       │
            ▼                                       ▼
  that member holds the eight          ✗ "the bootstrap admin" names nobody
```

So the seed resolves a **seeding administrator**: the member the admin seeding
established on this run where it established one, otherwise the earliest-created
active admin, ties broken by identifier. The second branch always resolves,
because it is *defined* by the membership holding an active admin — and where
the membership holds none, the admin seeding has already failed the chain and
this step never runs. The resolution is therefore total, and yields an active
member on both branches, which is what the active-role obligation needs.

*Alternatives considered:* seeding the eight `draft` when nothing resolves —
rejected because it breaks the premise that they are assignable from the first
boot, which Change 3 depends on. Failing the step — rejected because it turns an
ordinary redeploy of a live system into a start-up failure, the same shape
`BOOTSTRAP_ADMIN_IDENTITY` already produced once. Naming the seeding
administrator confers nothing on them and alters no membership entry, so
`members`:88's guarantee that the variable confers nothing is untouched.

The seed **adds only what is missing** and alters nothing present, matching
`seed_playbook`'s existing behaviour: a slug already in the collection is left
exactly as it stands whatever an operator has since done to it, so edits survive
every redeployment.

### 8. Role writes serialize on the existing `members_set` version row

The member/role invariant spans both collections, so they are one write-serialization
boundary. Two version rows would let this interleaving land:

```
  A: deactivate member M            B: move role R's default to M
     reads members_set v1              reads roles_set v1
     M holds no active default         M is active ✓
     writes M inactive, v2             writes R.default = M, v2
                    ▼                                ▼
         R is active with a deactivated default holder — the exact
         state the invariant exists to forbid
```

So role writes take the same version row membership writes take. Its table is
named `members_set`, which now under-describes it; a docstring records that it
is the `access` module's write version rather than the membership's alone.

*Alternative considered:* rename it `access_set`. Rejected for timing, not for
accuracy — `rename-the-roster-to-members` renamed this exact table
(`roster_set` → `members_set`) in the change that merged immediately before
this one, and renaming it again in the next change is churn a reader has to
reconcile against two archived records. Recorded as naming debt for whoever
adds a third collection here.

### 9. Schema

```
  roles                             role_holders
  ──────────────────────            ──────────────────────────────
  slug            PK                role_slug     FK → roles.slug   ┐ PK
  title                             member_id     FK → members.id   ┘
  status          CHECK in          is_default    bool
                  (draft, active,   added_by, added_on
                   retired)
  created_by/on                     UNIQUE (role_slug) WHERE is_default
  updated_by/on                     ── at most one default per role,
  retired_by/on                        enforced by the database
  unretired_by/on
```

The partial unique index makes "at most one default" a storage guarantee rather
than only a checked invariant, in the same spirit as `members.slack_identity`'s
uniqueness constraint. Attribution columns mirror `MemberRow`'s exactly,
including the split between `updated_*` and the status-transition pair, so the
admin can present the same audit for both collections.

### 10. The Team page follows the shipped step-page pattern rather than inventing one

Row links to the record's own page; every action on that page; the create form
on a page of its own. This is `move-step-actions-into-step-pages` applied
unchanged, and the Roles pages are built to it from the start rather than
built inline and rebuilt later — which is the mistake this change is undoing
for members.

**Copying the pattern means copying what was added to it later, too.** The
pattern as first shipped left its record pages with no way back: the header
identifies the current surface as a *position rather than a link*, and its
guarantee concerns the *other* admin surfaces, so the list an admin arrived
from is not covered by it — `launch-admin`:988-995 records that gap explicitly
("Nothing therefore obliged a way back, and there was none"), and
`playbook-admin`:1349 records the breadcrumb that closed it for steps. This
change creates four new sub-pages, so both capabilities state the breadcrumb,
and `members-admin`'s header requirement is widened from "The Team page" to all
three pages of the Team surface. Without that widening the two collections would
get different navigation guarantees out of one change whose stated goal is one
pattern across both.

### 11. `row-action` keeps its name despite no longer naming a row's action

After the rebuild the marker sits on the record's own page. Renaming it would
touch every admin template and stylesheet rule at once, for a vocabulary change
with no behavioural content, inside the diff of a rebuild — three reasons not
to. It is the shared admin vocabulary's word for *an action control*. Recorded
as debt; correcting it is separate work touching every admin surface equally.

### 12. `docs/playbook-program.md` is amended, not left to drift

Seven amendments, across four sections this change supersedes. Line numbers are
against `main` at `d1ee1fa`:

| Location | Amendment |
|---|---|
| `:380` rename bullet | "implemented and awaiting merge" → done; `rename-the-roster-to-members` merged as PR #152 |
| `:194` "Roles are a managed collection, seeded with nine" | twelve, with the seeded-status rule from Decision 7 |
| `:197` "What the nine below are is a *starting set*" | twelve |
| `:221` "seeding the nine roles and pointing every default at the bootstrap admin" | twelve, of which four point at nobody; and the holder is the seeding administrator, not "the bootstrap admin" |
| `:263` "**Open:** whether capital commitments want a tenth role" | decided: `managing-director` is seeded, with `it` and `analytics` alongside it |
| `:568` H7 | resolved — a member may hold several roles |
| `:215` and `:399` "a retired role takes no new assignments…" | both halves belong to Change 2, including "the steps still naming one are reported rather than failing a load" |

Plus one correction that is not a supersession: the plan cites the
self-confirmation rule as `launch-playbook:513` at `:425`, which is a blank
line. It is at `:414`. Left uncorrected, Change 2 would be scoped against a
citation pointing at nothing.

The plan's role table currently does two jobs at once: it lists the positions
*and* carries the discipline-to-role completeness argument ("every one of the
358 steps is covered and none is counted twice"). With four discipline-less
rows added, the amendment **splits it in two** — a positions table, and the
discipline-to-role seed map the completeness argument belongs to. Change 3
reads the map; this change seeds the positions.

## Risks / Trade-offs

- **[Risk]** The seeding administrator is the default holder of eight active
  roles on a fresh deployment and cannot be deactivated until each is moved or
  retired → **Mitigation**: the refusal names every blocking role at once, so it
  takes one attempt to learn the full list rather than eight; and the ordinary
  onboarding path (add a holder, move the default) is the same two actions the
  admin would take anyway. Decision 7 keeps this at eight rather than twelve.
- **[Risk]** `members`:103-111's mis-seed correction path now has a second step
  nothing tells the operator about. That path says a wrongly seeded first admin
  is "deactivated through ordinary writes once the corrected admin exists" — but
  on a redeploy where the roles already exist, the seed is add-only, so the eight
  roles still hold the wrongly seeded entry as their default and the ordinary
  write is refused → **Mitigation**: the refusal names all eight roles at once,
  so the remedy is one refusal plus eight add-holder writes and eight default
  moves rather than a mystery — the target of a default move must already be a
  holder, so both actions are needed, exactly as the bullet above accounts for
  them; and the corrected admin is by then available to hold them. Recorded because
  an operator following the members spec's own instructions meets a refusal that
  spec does not mention.
- **[Risk]** This change carries three separable halves — the role model, role
  management, and the page rebuild — and the plan pre-authorizes splitting the
  role-management half if it stops being reviewable in one sitting →
  **Mitigation**: **measured, and the measurement is recorded here rather than
  left as an intention.** The package reaches 4 capabilities, 21 requirements
  and 93 scenarios across 72 tasks:

  | Capability | Requirements | Scenarios |
  |---|---|---|
  | `roles` (new) | 6 | 31 |
  | `roles-admin` (new) | 8 | 29 |
  | `members` (delta) | 1 | 6 |
  | `members-admin` (delta) | 6 | 27 |

  The plan estimated 2 capabilities for this change's remainder
  (`docs/playbook-program.md`:382-384), so its own split criterion is
  observably engaged — 4 against an estimate of 2, where the rename split at 13
  against 2. `roles-admin` plus tasks §7 is what would come out, leaving the
  model, the invariant, the seed and the Team rebuild here, and Decision 4's
  primary argument for holders-as-a-set survives that cut intact. **The
  measurement is recorded, not acted on: whether to split is the author's call
  and is being put to them rather than taken here.**
- **[Risk]** A slug chosen badly is unfixable, and twelve are chosen here in one
  go → **Mitigation**: the twelve come from the plan, where they were derived
  from the 358 steps' disciplines rather than invented; and the title, which is
  what anyone actually reads, stays editable.
- **[Risk]** The seed's add-only behaviour means a mistake in the seeded set
  cannot be corrected by redeploying — a wrong title stays until edited by hand
  → **Mitigation**: accepted deliberately, and it is the same trade
  `seed_playbook` already makes. The alternative, a seed that overwrites, would
  discard an operator's edits at every deployment.
- **[Trade-off]** `members_set` now serializes writes to a collection its name
  does not mention (Decision 8), and `row-action` names a marker that is no
  longer on a row (Decision 11). Both are naming debt taken on deliberately to
  keep this diff about what it is about.
- **[Risk]** The Dockerfile's healthcheck `start-period` is tuned to the start
  chain's length, and its comment records `seed_playbook` having broken the
  probe when it joined the chain → **Mitigation**: twelve inserts inside an
  existing step add no process to the chain; confirm the deployed container
  reaches healthy rather than assuming it.

## Migration Plan

One Alembic migration creating `roles` and `role_holders`; no existing table is
altered. The seed runs in `seed_admin`, after the admin exists and before
`seed_playbook`, so a deployment that cannot establish an admin never reaches
the role seed.

Rollback is a straight revert plus a downgrade dropping the two tables; nothing
outside them holds a role reference yet, which is true only until Change 2 —
after that, a rollback of this change is no longer isolated.

Per `AGENTS.md`, the migration is exercised in both directions against a
migrated clone of the seeded database before the change is called complete, not
only upgraded.

## Open Questions

- **`analytics`' title.** Seeded as *Data Analyst*. Titles are editable by
  design and no stored reference is by title, so changing it costs one admin
  action and rewrites nothing. Does not affect the specs, the approach or the
  tasks.
- **Column order on the Team list.** The admin's three existing tables disagree
  — the product index and launches list read identity-first, the playbook steps
  table name-first after a request scoped to that one page, and the question was
  deliberately left open in `add-admin-breadcrumb-navigation`'s design. The Team
  list carries both a display name and a Slack identity, so it inherits the
  question. Left to the live presentation pass rather than settled in prose; it
  changes no requirement.
- **A `308` from `/admin/roster`.** `rename-the-roster-to-members`' design §6
  declined a redirect, weighing only the bookmark's convenience. It did not
  weigh that admin routes refuse with a 404 indistinguishable from an
  unregistered route, so a stale link reads as *no permission* rather than
  *moved*. Raised and **not** decided here: it reverses a recorded decision in
  an archived change, and doing that unasked is worse than the stale link.
