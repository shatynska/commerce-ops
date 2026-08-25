## 1. Carry the active filter through every write and every link

- [x] 1.1 Add a `_filters_of(request)` helper in `playbook_admin.py` returning the four narrowing values (gate, discipline, search term, show-retired) from `request.query_params`, and use it in the `step_table` read route in place of its inline parameter reads
- [x] 1.2 Thread the helper's result through every write route — `save_edit`, `create`, `retire`, `unretire`, `move_up`, `move_down` — so no route calls `_render_page()` argument-less
- [x] 1.3 Remove `unretire`'s hardcoded `show_retired=True`, which the carried filter now supplies
- [x] 1.4 Render the filter once into the page context as a query string and append it to every form `action` in `page.html`
- [x] 1.5 Carry the filter across the edit round trip: append it to the edit link (`page.html:72`), read it in `edit_form` via the helper, pass it to `_render_edit`, and append it to `edit.html`'s form action and its "Back to the table" link (`edit.html:34,39`)
- [x] 1.6 Carry gate, discipline and search across the show-retired and hide-retired links (`page.html:48,50`), which today discard them
- [x] 1.7 Verify against the five scenarios of "The narrowed view survives every write and every move between views", including the rejected-edit one, which must still re-render the edit form rather than the list

## 2. Render each step's position within its gate

- [x] 2.1 Compute each live step's 1-based position among its gate's live steps and the gate's live count in `_render_page`, before the narrowing is applied, so the position reflects the whole gate
- [x] 2.2 Add the position column to the step table in `page.html`
- [x] 2.3 Verify a filtered view renders unchanged positions

## 3. Make a move filter-aware

- [x] 3.1 Add a test pinning that `_render_page`'s sort key and `playbook_authoring._slot_of`'s ordering agree over a gate's live steps, so drift surfaces as a failure rather than as misplaced steps
- [x] 3.2 Implement the target-index rule from `design.md` — Decisions: given the gate's live steps, the visible subsequence and the named visible step to come to rest after (or the head), return `index in G∖S` + 1, or the index of the first visible step other than `S`
- [x] 3.3 Treat a move that would leave the visible order unchanged as a no-op that persists nothing — testing the resulting visible order, not whether the rule yields an index, since for a head move on an already-first step it yields a perfectly good one that slides the step past hidden steps (see `design.md` — "A move that changes nothing is not a write")
- [x] 3.4 Stop `_render_page` discarding the set version it loads (`records, _version`, `playbook_admin.py:269`), put it in the page context, and emit it as a hidden field on each move control, so a move has a rendered version to submit
- [x] 3.5 Replace `_move` with a single route taking `step_id`, the named visible step (empty for the head) and the rendered set version, deriving `target_index` server-side
- [x] 3.6 Reject the move with the stale notice unless the submitted version equals the version the route's own load returns, **before** computing the position, so a move made on a superseded list is never recomputed against a set the admin did not see — note that passing the route's own load version through instead would make the check vacuous and leave the race open
- [x] 3.7 Express move-up and move-down in that vocabulary — down names `V[j+1]`, up names `V[j-2]` or the head when `j == 1` — so both share one code path, and render each inert at its end of the visible list
- [x] 3.8 Render the stale notice when the named step is absent or retired at the route's own load
- [x] 3.9 Render `reorder_step`'s `InvalidPlaybookError` and bare `ValueError` (out-of-range index, retired step) as the existing `_move` does, so neither escapes as a 500
- [x] 3.10 Confirm the new route rides `_require_admin` and refuses with the app's own 404, per `admin-session`'s absence-shaped requirement
- [x] 3.11 Verify against the spec's filtered-move scenarios: landing against the named visible step, landing against the next visible step up on a move up across hidden steps, disturbing nothing else, stopping at the first visible step on a head move, stopping at the last visible step on a tail move, and persisting nothing on a no-op

## 4. Honour a caller-supplied view in the authoring reorder

- [x] 4.1 Add an optional expected set version to `reorder_step`, leaving its position logic untouched
- [x] 4.2 When a version is supplied, reject with `StaleStepSetError` unless it equals the version the write reads — refusing a mismatch whichever way it differs, not only an older one — and suppress the `_WRITE_ATTEMPTS` retry so a lost view is never recomputed against; when absent, keep today's re-read-and-recompute behaviour so no existing caller changes meaning
- [x] 4.3 Update the `StaleStepSetError` docstring (`playbook_authoring.py:51-53`, "The write path retries against the fresh set") and `reorder_step`'s to state both paths, since that sentence is now true only of the absent-version one
- [x] 4.4 Pass the version the route validated in 3.6 into `reorder_step`, so the position is applied only to the set it was computed against
- [x] 4.5 Verify against the `playbook-authoring` delta's three added scenarios — a supplied view is not retried past, a mismatch is refused whichever way it differs, and a reorder without a view still resolves concurrency — and confirm the capability's pre-existing scenarios still hold
- [x] 4.6 Verify the page renders the stale notice on a rejected pinned version, per the admin spec's "A move computed on a superseded view is rejected"

## 5. Hold reordering unavailable where it has no honest meaning

- [x] 5.1 Render both reorder controls inert when a description search is active, stating why and offering to clear the search in one action
- [x] 5.2 Render both reorder controls inert when retired steps are shown, stating why and offering to hide them in one action
- [x] 5.3 Refuse a move server-side when the request carries an active search term or the show-retired state, persisting nothing and saying why, so the restriction does not rest on the rendered controls
- [x] 5.4 Verify a gate or discipline filter alone leaves reordering live

## 6. Verification

- [x] 6.1 Run `uv run pytest tests/unit tests/agents`
- [x] 6.2 Run `uv run pytest tests/integration`
- [x] 6.3 Run `ruff check`, `ruff format --check`, `mypy`, and `import-linter`
- [x] 6.4 Exercise the page by hand against the seeded 97-step set: filter `listable` by discipline, move a step, confirm the filter survives, the position column moved as expected, and the edit round trip keeps the filter in both directions
