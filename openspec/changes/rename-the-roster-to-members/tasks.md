## 1. The substitution map

- [ ] 1.1 Write `rename.py` in this change directory: the substitution table
      from `design.md` §2, applied longest-match-first over a file tree, with
      a `--check` mode that reports differences rather than writing.
- [ ] 1.2 Give the table **three row kinds**, not two: `preserve` (matched
      first, never rewritten), then the substitutions, longest-first.
      **Derive the path-shaped preserve rows** from `design.md` §2's rule
      rather than transcribing a list, evaluating its **two columns
      separately**: map protection where the token occurs outside the
      exclusions *when the map runs*, check-2 permission where it does so *in
      the committed tree*. Expect **two derived protection rows** — the path
      prefix `openspec/changes/move-principals-to-roster/` and the bare token
      `move-principals-to-roster` — and **three derived permitted tokens**,
      those two plus this change's own name `rename-the-roster-to-members`,
      which earns permission only because tasks 7.5 and 7.6 write it into two
      docs. Falsify **the derived set, in both directions**: more than two
      derived protection rows means the list was short again and the extras
      are real; *fewer than three derived permitted tokens* means the two
      columns were collapsed back into one, which silently reinstates the
      gate failure this rule exists to prevent; and
      `a3d7e9f2c481_add_roster_tables` appearing in either column means the
      "occurs outside" test is not implemented at all. Scope those counts to
      the **derived** rows: §1.3 adds two more, which are protected by
      definition, so the finished table carries four protection rows and five
      permitted tokens (`design.md` §2).
      **One case is deliberately uncovered here**: *fewer* than two derived
      protection rows. It is caught downstream instead — `move-principals-to-roster`
      would then be rewritten at all 20 of its sites, so its permission row
      produces no hit, which 8.2's symmetric half rejects. Recorded because
      the coupling is six sections away and invisible from either end.
- [ ] 1.3 Add the two **enumerated** preserve rows the rule cannot derive,
      both prose quoting a prior state: the quoted pre-rename spec fragments
      at `docs/playbook-program.md:153` and the decision sentence at line
      151. Match every row **by its text, never by line number** — task 7.5
      edits that file and shifts the lines below its edit before the map
      runs.
- [ ] 1.4 Declare the input set as **the whole tree minus the exclusions**
      (`design.md` §1): `openspec/changes/**` — this change's own directory
      included, since it is named for the old vocabulary and quotes it as
      evidence — plus `alembic/versions/**`, `.git/`, `.venv/` and
      `uv.lock`. The exclusion list is the only place the scope is decided.
      When measuring against it, **check the exclusion actually excludes**:
      the counts in `design.md` §2 were wrong twice because a path filter
      silently matched nothing.
- [ ] 1.5 Enumerate every `roster`- and `person`-bearing token in the input
      set and confirm each is covered by a row. Two stems suffice: every
      substitution row carries one, the three admin-surface rows included
      (`/admin/roster`, `roster.html`, and the header tuple matched whole).
      There is deliberately no `Users → Team` row — `design.md` §2 gives the
      measurement, and `roster.html`'s two display strings are hand-edited
      under §5 instead. A token the table does not cover is a row to add — a
      substitution row, or a `preserve` row where the token names the old
      vocabulary rather than using it.
- [ ] 1.6 Assert the table is injective over its substitution rows: no two
      sources map to the same target. `roster_people → members` and
      `roster → members` would collide, which is why the first is applied
      first and the second never sees it. A `preserve` token is never a
      target, so it cannot collide.

## 2. Domain and application

- [ ] 2.1 `git mv src/commerce_ops/access/domain/principals.py`
      `src/commerce_ops/access/domain/members.py` (design §3).
- [ ] 2.2 `git mv src/commerce_ops/access/application/roster.py`
      `src/commerce_ops/access/application/members.py`.
- [ ] 2.3 The map produces `access/`'s contents: `Person → Member`,
      `Roster → Members`, the collection's field `people → members`,
      `InvalidRosterError → InvalidMembersError`, `RosterStore →
      MembersStore`, `StaleRosterError → StaleMembersError`, `PersonRecord →
      MemberRecord`, and the four write use cases.
- [ ] 2.4 Confirm `access/application/__init__.py`'s imports and `__all__`
      came through the map correctly — the module's only public surface,
      which `import-linter` enforces.

## 3. Infrastructure and the admin surface

§3 is map output apart from two things: the `git mv`s, which are the
file-level half the map does not perform, and the two display strings in
3.4, which are hand-edited under `design.md` §5 because no `Users → Team`
row exists.

- [ ] 3.1 `access/infrastructure/driven/models.py`: `RosterPerson →
      MemberRow`, `RosterSet → MembersSet`, `__tablename__`s
      `roster_people → members` and `roster_set → members_set`, constraint
      `ck_roster_set_singleton → ck_members_set_singleton`.
- [ ] 3.2 `git mv .../driven/roster_repository.py` to `members_repository.py`;
      `PostgresRoster → PostgresMembers`, `RosterRepository →
      MembersRepository`.
- [ ] 3.3 `git mv .../driving/roster_admin.py` to `members_admin.py`;
      `PAGE_PATH` from `/admin/roster` to `/admin/team` and the five routes
      that hang off it.
- [ ] 3.4 `git mv .../driving/templates/roster.html` to `team.html`; its
      `<title>` and `<h1>` from *Users* to *Team*, **by hand** — those two
      display strings are `design.md` §5's enumerated exception, not map
      output. **Nothing else in this template changes** — the add-a-person
      form, the `actions` column and the `display: contents` hack all stay,
      per design's Non-Goals.
- [ ] 3.5 `shared/.../templates/_admin_header.html`: the surface row
      `("roster", "/admin/roster", "Users")` becomes
      `("team", "/admin/team", "Team")` — matched whole, so the key, path and
      label cannot half-apply. Two comments in the same file follow it by
      hand: the one about `current` being `"roster"`, and **the one at line
      39 explaining why the label reads *Users***, which no map row reaches
      and which otherwise survives to explain a label that no longer exists.

## 4. The seams `launch` and the composition root read through

Map output, listed so the faithfulness check has a named subject — not a
hand pass.

- [ ] 4.1 `launch/application/playbook_authoring.py`: `UnreadableRosterError
      → UnreadableMembersError`, and `launch/application/__init__.py`'s
      import and `__all__` with it.
- [ ] 4.2 The `roster` / `roster_reader` seam attributes and their `__all__`
      entries across `activation_readiness`, `automated_decisions`,
      `gate_decisions`, `retained_results`, `thread_establishment`,
      `launch_playbook` and `clickup_sync`.
- [ ] 4.3 The driving adapters that wire them: `automation_confirmation`,
      `automation_pass`, `clickup_sync_job`, `clickup_webhook`,
      `gate_confirmation`, `gate_progression_job`, `launch_admin`,
      `playbook_admin`, `product_dossier`, `slack_entry`.
- [ ] 4.4 `main.py` and `worker.py`: the two near-identical private
      `_RosterReader` adapters; `seed_admin.py`; `check_step_handlers.py`.
- [ ] 4.5 Confirm `import-linter` is clean — a missed public-surface site
      fails here rather than silently importing a private path.

## 5. The database

- [ ] 5.1 Write one Alembic revision on `c04d95ba6e31` (the current single
      head) renaming both tables and the constraint, with a downgrade that
      inverts all three. No row is read, written or moved (design §4).
- [ ] 5.2 Confirm `alembic heads` still reports a single head afterwards.
- [ ] 5.3 Leave the 28 existing revisions untouched,
      `a3d7e9f2c481_add_roster_tables.py` included — applied history, per
      design §7. It is **not** a preserve row and must not be made one: it
      occurs only under `alembic/versions/**`, so the exclusion already
      protects it and a permission row would fail 8.2 on a correct tree
      (design §2).

## 6. Tests

- [ ] 6.1 Map output over `tests/`. Renames only: fixture and helper
      identifiers, test function names, module paths under test, and the
      expected strings that changed with their source.
- [ ] 6.2 `git mv` the thirteen test files whose names carry the old
      vocabulary, so a file's name still says what it tests.
- [ ] 6.3 Two comments the map cannot reach, at
      `test_roster_header_names_every_surface.py:124` and
      `test_roster_admin_presentation_vocabulary.py:173`: both read *"since
      the header calls this surface Users"* and explain an assertion keyed on
      **lowercase** `"user"/"users"`. The header now says *Team*. Correct
      both comments by hand, then apply this rule to each assertion — it is
      decidable without knowing in advance which case each one is:

      The discriminating question is **"once the label says *Team*, can this
      assertion still fail?"** — not what word it mentions.

      - **If it can still fail**, it is a live constraint that merely passes
        now. **Leave it alone.** A prohibition on the page saying
        `"user"`/`"users"` is this case: the word being gone *satisfies* it,
        and re-pointing it at *Team* would make it forbid the label the page
        is now required to show — an assertion not just changed but
        inverted, which check 3 forbids outright.
      - **If it cannot fail whatever the page does**, it has gone vacuous.
        Re-point it at whatever it was guarding — a locator that finds the
        surface by searching for `"user"`/`"users"` is this case: after the
        rename it matches nothing, asserts over nothing, and passes for that
        reason alone.
      - **If it requires the label's presence**, that is the first case with
        a rename attached: it can still fail, and its expected string is
        renamed to *Team* alongside the source, which is already policy
        (design §5 — no assertion is relaxed, only its expected string
        renamed).

      **This task may correctly produce no assertion edit at all**, only the
      two comment corrections. A task that describes only edits invites one;
      the right outcome here is whatever the question above returns.

      **The corrected comment must state the assertion's *current*
      rationale, not merely drop the stale one.** Under the leave-it-alone
      branch the assertion is untouched and now always passes, and nothing
      in the diff distinguishes that from an assertion nobody opened — the
      same shape of defect this task exists to prevent, one level up. The
      comment beside it is changing regardless, so let that edit carry the
      record: *"keyed on `user`/`users` because this surface must not say
      it; the header now says Team, so this still constrains"* is a comment
      only someone who asked the question could write, and it sits on the
      line `/code-review` at 8.5 is already reading for adjacency. No new
      mechanism, and nothing heavier than the two-site problem warrants.

      Note that 6.4 cannot catch a vacuous pass — an assertion that has gone
      vacuous is one that did *not* change, and shows in the diff as an
      unchanged line beside a changed comment. `/code-review` at 8.5 reads
      that adjacency; the rule above is what makes it not need to.
- [ ] 6.4 Read the test diff for the one thing a rename can hide: **no test
      added, deleted, skipped or weakened, and no assertion changed other
      than renamed identifiers and renamed expected strings.** This is design
      §8's check 3, stated whole — the carve-out matters here because 6.3's
      third branch directs exactly such a rename, and without it this task
      appears to forbid what the previous one requires.

## 7. Specs and docs

- [ ] 7.1 `git mv openspec/specs/roster` to `openspec/specs/members` and
      `openspec/specs/roster-admin` to `openspec/specs/members-admin`,
      including each file's `# <name> Specification` heading.
- [ ] 7.2 Map output over all thirteen spec files, then correct the prose by
      hand where the mechanical output reads wrongly — *"an active roster
      member"* collapses to *"an active member"*, not to *"an active members
      member"* (design §5).
- [ ] 7.3 In that hand pass, apply design §5's noun rule — the surface is
      **the Team page**, the capability stays `members-admin` — and design's
      Non-Goals rule on the `member` collision: keep a qualifier wherever the
      sense is ambiguous against set, enum, network or Slack-workspace
      membership, rather than dropping every qualifier.
- [ ] 7.4 Leave prose that says "a person" about a human in general —
      `admin-session`'s *"the person who minted the link"* — alone. That is
      not this directory's entity (design's Non-Goals).
- [ ] 7.5 `docs/playbook-program.md`: rewrite *### 1.
      `rebuild-the-member-directory`*'s rename bullet (lines 378–382) and the
      "four commits" framing at 408–412 to record that the rename landed as
      its own change. **Naming this change is required** — a pointer that does
      not name `rename-the-roster-to-members` is not a pointer — and that
      name is a `preserve` row, so the map leaves it and 8.2 permits it.
      Lines 151, 153 and 383 are likewise preserved and stay exactly as they
      are; lines 212, 318, 389 and 426 are ordinary uses and are map output.
- [ ] 7.6 `docs/proposed-change-order.md`: record that
      `share-the-unit-test-harness` rebases onto this change, by name. That
      file states cross-change ordering "lives nowhere else", so leaving the
      dependency only in `proposal.md` would make it untrue.
- [ ] 7.7 `docs/deferred-work.md`: add an entry for `docs/domain-map.md`
      lines 191 and 198, which still name `Principal` as the `access` root
      model and describe a repo-owned principals file granting access by SKU.
      **Do not correct them here** — they were made false by
      `move-principals-to-roster`, they carry neither stem so no map row or
      check reaches them, and a correct fix is a judgement about the domain
      map's accuracy rather than a substitution. The exclusion and its
      reasoning are recorded in `design.md` §7.
- [ ] 7.8 `docs/reference/README.md`,
      `docs/reference/agent-orchestration.md`, `README.md`, `AGENTS.md`, and
      `docs/deferred-work.md`'s own ordinary uses.

## 8. Verification

- [ ] 8.1 **Faithfulness** — run `rename.py --check` against the commit over
      §1.4's full input set; the difference must touch no line carrying an
      identifier. A difference on such a line means the map is wrong: fix the
      map and re-run, do not hand-patch the file (design §8, check 1).
- [ ] 8.2 **Completeness** — a case-insensitive search for `roster` returns
      nothing outside `openspec/changes/**` and `alembic/versions/**` other
      than the **five** permitted `preserve` tokens (three derived at §1.2,
      two enumerated at §1.3), this change's own name among them — note that
      only two of the three derived tokens carry a *map-protection* row,
      which is deliberate and is `design.md` §2's two-column split; no
      `Person`,
      `create_person`, `list_people` or `person_id` survives in `access` or
      in the seams `launch` reads it through (check 2). A hit that is neither
      a preserve row nor an exclusion is a defect, not a gate to relax — and
      **every one of the five must produce at least one hit**, since a row
      with none means the text it protects has gone. The rule's "occurs
      outside the exclusions" clause is what makes that symmetric half
      passable: a row whose only referent lies inside an exclusion would fail
      it on a correct tree, which is why `a3d7e9f2c481_add_roster_tables` is
      not a row.
      **That symmetric half is load-bearing beyond its own gate — do not
      simplify it away.** It reads as redundant, and it is the only thing
      covering a case §1.2 deliberately leaves uncovered: too *few* derived
      protection rows. A token wrongly left unprotected is rewritten at every
      site, so its permission row then produces nothing, and this clause is
      what notices. Deleting it reopens a gap six sections away with nothing
      recording that the two were connected.
      Before trusting a zero, **confirm the search's own exclusion
      actually excludes**: two counts in `design.md` §2 were wrong because a
      path filter matched nothing and the hits were counted anyway, and a
      completeness gate that greps wrongly reports success.
- [ ] 8.3 **No behaviour changed** — `uv run pytest` green across
      `tests/unit`, `tests/agents` and `tests/integration`; `ruff check`,
      `ruff format --check`, `mypy` and `import-linter` clean; **and the test
      diff contains no changed assertion, only renamed identifiers and
      renamed expected strings** (check 3, whole).
- [ ] 8.4 Open the `/admin/team` page against a live server and confirm it
      renders, its header marks *Team* as current, and every other admin
      surface reaches it in one action.
- [ ] 8.5 Run `/code-review` over the diff before calling the change
      complete, per `AGENTS.md` — the reviewer's question here is check 3's
      last clause, not the substitution.

## 9. Archive and merge

- [ ] 9.1 Run `openspec archive rename-the-roster-to-members --yes` as the
      last commit before the merge, per `AGENTS.md`'s *Deployment and
      configuration*. With `skip_specs: true` it folds no deltas, which is
      exactly why it is easy to skip silently — and skipping it merges an
      unarchived change to `main`, which the deploy rule forbids. (It would
      *not* break 8.2 for later changes: the directory sits inside the
      `openspec/changes/**` exclusion either way.)
- [ ] 9.2 Open the PR. Nothing ships from a local machine; merging to `main`
      is what triggers the deploy.
