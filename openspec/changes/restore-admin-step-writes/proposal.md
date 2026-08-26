## Why

Every write on the playbook admin page is broken in production, and has been since `move-principals-to-roster` replaced the principals file with a Postgres roster. Creating a step answers `Internal Server Error`; editing, retiring, un-retiring and changing a status appear to do nothing at all. Nothing is persisted by any of them.

The cause is one seam. `main.py` injects `PostgresRoster` — a store exposing `load()` and `save()` — into `playbook_admin.roster`, and the five write routes hand that object straight to the authoring use cases as their `roster=` collaborator. `playbook_authoring._read_people` understands three shapes (`.list_people()`, a callable, an iterable) and the store is none of them, so the precondition check raises `TypeError: 'PostgresRoster' object is not iterable` before the write is judged. The page's *read* path adapts the store correctly, through `access`'s public `list_people`; only the write path passes it through unadapted.

The two symptoms differ only in how htmx treats the failure. The create form is deliberately un-boosted, so the browser paints the raw 500. Every other write is boosted from `<body hx-boost="true">`, and htmx's `responseHandling` config swaps nothing on a `[45]..` response — so the admin sees no error, no change, and no reason to think the write did not land. That silence is a defect in its own right: the surface's stated contract is that a rejected write renders every fault with the submitted values still in the form, and it holds for faults the page anticipated while an unanticipated one renders nothing whatsoever.

## What Changes

- The admin page's write routes SHALL pass the authoring use cases a roster **reader**, adapted from the injected store exactly as the page's own read path already adapts it. The injected collaborator stays the store, because `_require_admin` calls `verify_admin_session(roster, …)`, which is typed `RosterStore` and genuinely needs it.
- The roster collaborator the authoring use cases take SHALL have one named shape rather than three guessed ones, so that a caller handing over the wrong object gets a loud, named **error** — not a `TypeError` raised halfway through a write, and not an entry in the write's fault list, which is what "fault" means everywhere else in these specs.
- A write on the admin page that fails for a reason the page did not anticipate SHALL still tell the admin it failed. No write SHALL be able to leave the page looking as though nothing was submitted.
- The seam SHALL be covered by a test that hands a real `RosterStore`-shaped collaborator to an authoring write, which is the one arrangement no existing test exercises.

Non-goals, recorded so scope does not drift:

- Two further duck-typed roster readers in `launch` carry the same latent hazard: `clickup_sync._roster_people` and `activation_readiness._people_of`. Neither is narrowed here — both are fed a correctly shaped reader today, and unifying all three behind one typed port is a separate change. The reader this change **does** narrow is `playbook_authoring`'s own, which is the one the authoring writes use and the one that is mis-fed.
- No change to what the preconditions check, to which steps they are evaluated over, or to any coherence rule.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `playbook-authoring`: the roster collaborator the write-side preconditions are evaluated against gains a stated contract — one shape, and a collaborator that cannot answer it is refused by name rather than crashing mid-write.
- `playbook-admin`: adds that every write reaches the same roster the page reads, and that a write failing for an unanticipated reason is reported to the admin rather than silently swallowed.

## Impact

- `src/commerce_ops/launch/infrastructure/driving/playbook_admin.py` — the five write routes (`create`, `save_edit`, `retire`, `unretire`, `change_status`) and the roster seam beside `_roster_people`.
- `src/commerce_ops/launch/application/playbook_authoring.py` — `_read_people`, the `_roster_identifiers` that calls it, and the `roster` parameter of the five write use cases.
- **Not** `src/commerce_ops/main.py`: the composition root keeps injecting the store, because the page's guard still needs one. `design.md` — *The page adapts the store* records why.
- The admin page's client behaviour: a boosted write that fails must surface. That lands in `shared/…/templates/_admin_header.html`, the one partial both boosted templates include — not in `page.html` and `edit.html` separately, and not in a server-side handler. `design.md` — *The listener lives in the shared header partial* records why.
- Tests: `tests/unit/launch/application/` (the store-shaped collaborator), `tests/unit/launch/infrastructure/driving/` (the surfaced failure), and `tests/integration/launch/test_playbook_authoring_live.py`, which today passes `roster=None` and so never exercises the precondition path at all.
- No data migration. Every failing write raised before `steps.save`, so nothing was half-written and the set version never moved.
