## Why

The people directory is called four different things depending on where you
look. The specs and the code say `roster`; the domain calls its inhabitant a
`Person`; the admin page's own `<h1>` says *Users*; and the specs' prose
already reaches for **member** whenever it needs a human noun — *"An active
roster member resolves to the unrestricted scope"*, *"a deactivated member
sees nothing"*, *"membership says what a person may see"*.

`docs/playbook-program.md` settles which of the four wins: the directory is
**members**, and the admin page is titled **Team**. `employee` was rejected
because the company head confirms steps and is not one; `collaborator`
because 26 uses across four specs already mean a supplied port, not a person.
The rename therefore promotes vocabulary the repository already uses rather
than inventing any.

**Why now, and why alone.** The program plan folds this rename in as the
first of four commits of `rebuild-the-member-directory`. Measured, it does
not belong there: the rename reaches 13 capabilities and ~4,800 identifier
and prose occurrences across 144 files, while the roles, role-management and
page-rebuild work it was bundled with reaches 2. Landing them together hands
one reviewer a change in which ~90% of the diff carries none of the risk and
11 unrelated capabilities are dragged through review for a word. Splitting it
out costs one extra review cycle over artifacts that are almost entirely
mechanical, and leaves `rebuild-the-member-directory` a change about roles
and a page — which is what it is for.

The program plan already treats a pure rename this way once:
`rename-lifecycle-stage-to-state` is its own change, for the same reason and
at a third of the size.

## What Changes

- **`Person` becomes `Member`, and `Roster` becomes `Members`** throughout
  the `access` module's domain, application, infrastructure and templates,
  and at every site the other modules reference them.
- **The tables are renamed**: `roster_people` → `members`, `roster_set` →
  `members_set`, with the check constraint `ck_roster_set_singleton` →
  `ck_members_set_singleton`. One new Alembic revision on top of
  `c04d95ba6e31`; the existing revisions are applied history and are not
  edited.
- **The two capability specs are renamed** on disk: `openspec/specs/roster/`
  → `openspec/specs/members/`, `openspec/specs/roster-admin/` →
  `openspec/specs/members-admin/`. The prose of eleven further specs is
  updated to the new vocabulary. **No requirement's meaning changes** — see
  *Capabilities* below.
- **The admin surface is renamed**: route `/admin/roster` → `/admin/team`,
  template `roster.html` → `team.html`, the header entry's label *Users* →
  *Team* and its key `roster` → `team`, and the page's `<h1>` from *Users* to
  *Team*. **BREAKING**: a bookmarked `/admin/roster` no longer resolves. The
  minted admin link lands on `/admin/playbook` and is unaffected, and the
  page is reached from the shared admin header, so nothing but a bookmark
  breaks.
- **Two stale module names are corrected while the file is being rewritten
  anyway**: `access/domain/principals.py` → `access/domain/members.py` (it
  survived `move-principals-to-roster`, which renamed the concept and not the
  file, and its own docstring already opens *"The roster: who is known"*),
  and `access/application/roster.py` → `access/application/members.py`.
- **`docs/playbook-program.md` records the split** — its Change 1 bullet
  loses the rename and gains a pointer to this change — so the program plan
  does not describe work that has already landed elsewhere.
- No behaviour changes. No route gains or loses a guard, no validation rule
  is added, removed or relaxed, and no test's assertions are weakened.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change sets `skip_specs: true` in its `.openspec.yaml`.

That is a deliberate reading of the marker and the alternative was
considered. Expressed through deltas, this change would be `ADDED × 5` in
`specs/members/` against `REMOVED × 5` in `specs/roster/`, the same again for
`roster-admin`, and `MODIFIED` restating 29 further requirements across
eleven specs: **≈49 requirement blocks, ~40 of them verbatim copies with one
word swapped.**

**What the archive precedent says.** OpenSpec has no capability-rename
operation, and no change among this repository's **78** archived ones has
ever renamed a capability. Two have *emptied* one: `introduce-launch-briefing`
removed every requirement of `product-monitoring`, and
`replace-cron-with-job-runner` did the same to `internal-trigger` — and
neither `openspec/specs/product-monitoring/` nor
`openspec/specs/internal-trigger/` exists today, so the delta route's end
state is **known rather than guessed**. (What is observed is the end state,
not the mechanism: the directories could have been removed by hand at archive
time. The end state is all this argument needs.) **The delta route therefore
carries no unknown archive behaviour.** An earlier draft of this proposal
claimed it did; that claim was wrong and is withdrawn. The delta set is the
*known-safe* alternative, and it is still the worse one, for two reasons that
do not depend on it:

1. **It is anti-informative.** A reviewer handed 40 near-identical
   requirement blocks must diff them by eye to establish that nothing
   drifted. The specs' own diff establishes the same thing better, word by
   word, and is what a reader will actually use.
2. **It would generate duplicate tests.** `openspec-test-writer` derives
   tests per scenario of an `ADDED` requirement. All ten of the `ADDED`
   requirements here already carry full coverage under their old names, so
   the pass would write a second copy of tests that exist.

What replaces the delta review is a machine check, recorded in `design.md`
§1 and §8: the rename is **generated by a committed script and diffed against
the commit**, so the review question becomes "is this ~50-row map right?"
rather than "did 4,800 edits stay faithful?". The map is not fully invertible
— *"an active roster member"* collapses to *"an active member"*, and some
tokens are deliberately preserved (`design.md` §2) — so the check is stated
forward, over the script's output, rather than as a reverse substitution. The
prose half is reviewed as a diff, which is bounded and readable.

Per `AGENTS.md`, a change declaring no specification deltas has none to
derive tests from, and **this change states that exemption in advance**: it
owes no new tests. What it owes is that the existing suite stays green with
no assertion weakened, which `tasks.md` makes the completion gate. That
exemption is the one thing downstream of the `skip_specs` choice: taking the
delta fallback would re-arm `openspec-test-writer`, with the duplication
reason 2 predicts.

## Impact

**Code** — 144 files, ~4,800 occurrences:

- `access/domain/principals.py` → `members.py`: `Person` → `Member`,
  `Roster` → `Members`, `InvalidRosterError` → `InvalidMembersError`, the
  collection's field `people` → `members`.
- `access/application/roster.py` → `members.py`: `RosterStore` →
  `MembersStore`, `PersonRecord` → `MemberRecord`, `StaleRosterError` →
  `StaleMembersError`, `create_person` → `create_member`, `update_person` →
  `update_member`, `deactivate_person`/`reactivate_person` →
  `deactivate_member`/`reactivate_member`, `list_people` → `list_members`.
- `access/application/__init__.py`: the `__all__` surface, which
  `import-linter` holds as the module's only public face — every consumer's
  import changes with it.
- `access/infrastructure/driven/models.py`: `RosterPerson` → `MemberRow`,
  `RosterSet` → `MembersSet`, both `__tablename__`s, the check constraint.
- `access/infrastructure/driven/roster_repository.py` → `members_repository.py`:
  `PostgresRoster` → `PostgresMembers`, `RosterRepository` →
  `MembersRepository`.
- `access/infrastructure/driving/roster_admin.py` → `members_admin.py`:
  `PAGE_PATH`, the five routes' path segments, `roster.html` → `team.html`.
- `shared/infrastructure/driving/templates/_admin_header.html`: the surface
  row `("roster", "/admin/roster", "Users")` → `("team", "/admin/team", "Team")`.
- `launch`: `UnreadableRosterError` → `UnreadableMembersError` (defined in
  `playbook_authoring.py`, exported from `launch.application`), and the
  `roster`/`roster_reader` seam
  arguments in `activation_readiness`, `automated_decisions`,
  `gate_decisions`, `playbook_authoring`, `retained_results`,
  `thread_establishment`, `launch_playbook`, `clickup_sync`, and the seven
  driving adapters that wire them.
- `main.py`, `worker.py`: the near-identical private `_RosterReader`
  adapters that wire `access` into `launch`'s seams, plus `seed_admin.py` and
  `check_step_handlers.py`.

**Database** — one new revision on `c04d95ba6e31`, renaming two tables and
one constraint. Reversible; no data is read, written or moved.

**Tests** — 93 files, ~3,900 occurrences. Renames only: fixture and helper
identifiers (`_FakeRosterStore` → `_FakeMembersStore`, `_FakeRoster` →
`_FakeMembers`, `ALICE_ROSTER_ID` → `ALICE_MEMBER_ID`, …), test function
names, and the module paths under test. Thirteen test files are renamed to
match their subject. No test is added, deleted or disabled, and no assertion is
changed **other than renamed expected strings, renamed alongside the source
they assert on** — the same carve-out `design.md` §8's check 3 carries, since
an expected string naming a renamed thing has to move with it.

**Specs** — 13 files. Two directories renamed; prose updated in all thirteen.

**Docs** — `docs/playbook-program.md` (records the split),
`docs/proposed-change-order.md` (records that
`share-the-unit-test-harness` rebases onto this, which that file says is the
one place cross-change ordering lives), `docs/deferred-work.md`,
`docs/reference/README.md`, `docs/reference/agent-orchestration.md`,
`README.md`, `AGENTS.md`.

**Not touched** — `openspec/changes/**` (this change's own directory
included), the 28 existing `alembic/versions/**` revisions, and
`docs/domain-map.md`'s stale `Principal` vocabulary, whose exclusion
`design.md` §7 records with its reasoning and which
`docs/deferred-work.md` carries an entry for. The archives
and the applied revisions are history: an archived change records what was
proposed at the time, and an applied revision's identifiers are what deployed
databases hold. Rewriting either would make the record lie. This change's own
artifacts are excluded for a related reason — they quote the pre-rename
vocabulary as the *evidence* for renaming it, and a directory named
`rename-the-roster-to-members` cannot survive its own substitution.

**Downstream** — `rebuild-the-member-directory` branches off this change's
merge, so its diff contains no rename. `share-the-unit-test-harness` (queued,
unstarted, already marked *last*) touches many of the same test files and
should be rebased onto this rather than the reverse.
