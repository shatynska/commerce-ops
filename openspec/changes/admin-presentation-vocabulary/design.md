## Context

See `proposal.md` — Why. The constraints that actually shape the
approach, all verified against the repository rather than recalled:

- **The two surfaces live in different modules and may not import each
  other.** `.importlinter`'s `access-infrastructure-boundary` forbids
  `access.infrastructure` → `commerce_ops.launch`, and
  `products-infrastructure-boundary` forbids `launch.infrastructure` →
  `commerce_ops.access.infrastructure`. Both may import
  `shared.infrastructure`; `shared-boundary` forbids `shared` from
  importing any business module, `access` included.
- **The composition root already injects across that boundary.** Both
  `roster_admin.py:62` and `playbook_admin.py` carry module-level
  `roster: Any = None` / `admin_sessions: Any = None` with the comment
  "Injected by `main.py` after the app is built. Resolved at call time."
  `main.py:72-81` mounts every router.
- **Both admin guards are the same guard.** `roster_admin._require_admin`
  and `playbook_admin._require_admin` both call `verify_admin_session`
  on `access`'s public surface and both raise a bare `HTTPException(404)`.
- **Access already hardcodes launch's URL.** `admin_link.py:85` declares
  `ADMIN_HOME_PATH = "/admin/playbook"`. A cross-module href is an
  established pattern here, not a new coupling this change introduces.
- **Both modules build a plain Jinja `Environment` over a
  `FileSystemLoader` of their own `templates/`** — `playbook_admin.py:113`,
  `roster_admin.py:50`.
- **The created step's identifier already reaches the template.**
  `_render_page` takes `created` and passes it to `page.html`
  (`playbook_admin.py:897`); the comment at `:1055` calls it "what a
  fragment cannot be: server-visible". The row `id="step-…"` already
  exists (`page.html:126`).
- **The fault-mark markup already exists.** `_fields.html:20` renders
  `<ul class="field-faults" data-field="…">` via the `marked()` macro,
  and `attribute-faults-to-fields`'s design records at its line 330 that
  this change owns the treatment.

## Goals / Non-Goals

**Goals:**

- One stylesheet, one substrate, one header, reachable from both modules
  without relaxing an `import-linter` contract.
- Every behavioural guarantee in the two delta specs observable from a
  server response, since the test tiers are server-side pytest with no
  browser tooling (`AGENTS.md` — Testing Strategy). Where a guarantee is
  genuinely about what an admin *sees*, the delta asserts a structural
  proxy a response does establish, and the eye-check is a manual
  verification task — never a scenario. Two components have no proxy at
  all and are manual-only: the row's action layout entirely, and the
  legibility half of the fault requirement — a dim is a computed style,
  and no response carries one.
- Leave every existing `playbook-admin` and `roster-admin` guarantee
  standing. This change restyles and connects; it removes no action,
  changes no write, and alters no narrowing.

**Non-Goals:**

- A design system, a component library, or a token set intended to
  outlive these two pages.
- Restyling any surface that is not one of these two — Slack blocks and
  the briefing output are untouched.
- Changing what the admin guard is or how a session is established.
  `admin-session` is not modified.
- Making the roster page use htmx. It is plain form posts by design and
  stays that way.

## Decisions

### The shared asset route lives in `shared`, with its guard injected

`shared/infrastructure/driving/admin_assets.py` owns one route,
`GET /admin/assets/{asset}`, serving from
`shared/infrastructure/driving/static/`. It carries a module-level
`verify: Any = None`, injected by `main.py`, and its guard resolves that
at call time — the idiom `roster_admin.py:62` already establishes.

This is the only arrangement that satisfies every constraint *and* keeps
one URL for one file. `shared` may not import `access`, so it cannot call
`verify_admin_session` itself; the composition root may know both, and
already does. The per-module alternative below satisfies the same
constraints at the cost of a second URL — the trade is drift risk against
injection machinery, not legality.

An un-injected `verify` SHALL refuse. If a mis-wired composition root
left it `None` and the route defaulted to serving, `/admin/assets/…`
would answer 200 to an anonymous caller while every other admin path
answered 404 — an existence oracle for the admin surface, and a
contradiction of `admin-session`'s requirement that the principal
resolve admin-capable *at the time of the request*. Absent a guard is
not the same as passing one.

One route means one URL, so both templates link the same `href` and the
delta specs' "the same stylesheet" is literally true rather than true by
convention.

**Alternative rejected — launch keeps serving it, access links the URL.**
No new module, and `import-linter` would never notice, since a template
href is not an import. Rejected because the invisibility is the problem:
the roster page would depend on a route owned by `launch`, enforced by
nothing, and deleting that route while editing the playbook page would
break the roster page with no signal. The roster delta forbids this
explicitly.

**Alternative rejected — each module serves its own copy from a shared
directory.** Two routes, two URLs, one asset directory in `shared`. Honest
about ownership and needs no injection. Rejected because two URLs for
one file invites the two surfaces to drift to different copies later,
and the injection it avoids is nine lines the codebase already writes
twice.

### Pico moves to `shared`; htmx stays in `launch`

The vocabulary is a token and density layer *over* Pico, not a
replacement for it. If the roster page does not load Pico, the two
surfaces do not match no matter how good the layer is, and the change
fails at its stated purpose. So `pico.min.css` moves to
`shared/infrastructure/driving/static/` and both surfaces load it.

`htmx.min.js` does not move. Only the playbook page uses it; the roster
page is deliberately script-free ("Every write is a plain form post, so
the page works without scripting" — `roster.html:6`), and moving a
dependency to `shared` that one consumer needs would be sharing for its
own sake.

Launch's own `GET /admin/static/{asset}` route stays for `htmx.min.js`.
Its `path.parent != _STATIC_DIR.resolve()` traversal guard
(`playbook_admin.py:1340`) is copied verbatim into the shared route
rather than reinvented.

### The header is a shared partial, not duplicated markup

`shared/infrastructure/driving/templates/_admin_header.html` holds the
header, and each module's Jinja `Environment` gets a `ChoiceLoader` over
`[FileSystemLoader(own templates), FileSystemLoader(shared templates)]`.
Each page includes it passing which surface is current.

**Alternative rejected — six lines of markup in each template.** No
loader change and nothing shared. Rejected because two copies of a header
that must stay identical is precisely the divergence this change exists
to end; the roster page's inline `<style>` is what that failure looks
like after a few months.

The header's links are literal paths — `/admin/playbook` and
`/admin/roster`. Launch cannot import access's `PAGE_PATH` and access
already writes launch's path as a literal (`ADMIN_HOME_PATH`), so a
literal in one shared partial is strictly better than the two literals
in two modules that exist today.

**The header link out of the playbook page is un-boosted**
(`hx-boost="false"`), for the reason `page.html:63-67` already records
for the Add step control: `hx-boost` is inherited from `<body>`, so
htmx would swap the roster page into the playbook page's body, discard
that page's own body attributes, and leave a roster page that cannot
post.

### Actions become one row of same-weight controls, marked in the response

Every action control carries `class="row-action"`, and the destructive
one additionally `class="row-action danger"`. That is what the delta
specs' "marker" means, and it is what a pytest assertion reads.

The two shapes are reconciled the way `page.html:68` already reconciles
them for Add step: the `edit` link becomes
`<a … role="button" class="row-action">`, matching the buttons rather
than the buttons matching it. Pico styles `[role=button]` as a button,
so this needs no rule of our own.

Getting them into one row is CSS, not restructuring: the action cell
becomes `display: flex` with `gap`, and `td.actions form { display: contents }`
collapses each single-action form so its button becomes a direct flex
item. The forms stay exactly as they are — separate forms with separate
actions and separate hidden inputs — which matters, because they post to
five different endpoints and merging them would change behaviour this
change has no business changing.

`danger` is a colour and a border, never a size or a weight increase.
The requirement is that retire stops being the loudest control, so
making it a *different* loud control would fail it.

### The fault-visibility defect does not exist, and the treatment is negative

Two earlier drafts of this design were wrong about the same thing, and
the correction is the most important decision recorded here.

The claim was that a fault marked on a timing-anchor input the submitted
kind does not use is rendered inside that input's `hidden` group, and so
is present in the response and invisible on the page. **No authoring
write can produce that state.** `_anchor_from_form`'s docstring says so
outright — "Only the inputs the submitted kind uses are read. The others
still submit their values" — so a fault can only ever be attributed to
an input the submitted kind uses, and the surface re-renders against
that same submitted kind, where that input is offered. No entry in the
fault-attribution table names an anchor field. The existing suite asserts
the negation directly: a test requires that a bad `anchor_start` does not
mark `anchor_days`, "which the submitted anchor kind does not even use".

The second draft's fix — moving `hidden` from the `<label>` to the
`<input>` — was therefore surgery for an unreachable case, and it would
have broken a reachable one. The live anchor toggle in `_fields.html`
sets `group.hidden` on the `[data-anchor-group]` **label**. Splitting
ownership of that attribute between the server and that script would
leave a visible label over an invisible input the moment an author
reconsidered an anchor kind.

What `attribute-faults-to-fields` actually deferred here is narrower
than either draft assumed. Its design says "Marking ships unstyled", and
the not-offered case it names as guaranteed is the **disabled** one: a
`human` step carrying an automation brief is refused for the pair and
marks both halves, and the brief renders disabled inside the fieldset
this change is about to dim.

So the treatment is a negative obligation and nothing more: **dimming
must not become hiding, and must not swallow the fault it sits beside.**
`.inapplicable` dims its fieldset and never hides it; no vocabulary rule
renders a mark, or a container holding one, as not displayed or as less
legible than the surface's ordinary text. That is tasks 2.5 and 2.5a,
and it is the whole of the fix. No template restructuring is required,
and none is done.

The second half is not a refinement of the first. The mark is rendered
*inside* the control's `<label>`, so the obvious way to dim a fieldset
— `opacity` on it, or on its labels — reaches the fault too, and
`opacity` establishes a stacking context that a descendant rule cannot
undo. An implementer who reads only "must not become hiding" writes
exactly that rule and passes every scenario.

A third draft carried the not-offered nesting rule forward as a
**rendering invariant** — a guard against a rule added later that named
an anchor field. It has been cut, and the reason is a factual error in
its own rationale worth recording so it is not proposed a fourth time.

The rationale said a rule *reworded* in another layer could produce the
state silently. It cannot. `_crossing` returns `_AttributedFault(text, ())`
when no entry matches, so a reworded rule produces a fault with **no
fields** — no mark at all, hence nothing to nest. Only a rule *added*
naming an anchor field could produce it.

And the remedy that would have made the invariant meaningful does not
hold either. Binding it to the exhaustive provocation sweep looks
attractive, but that sweep's own docstring says: "This sweep catches a
rule reworded, not a rule added. Nothing enumerates the rule set
mechanically, so a coherence rule introduced later is simply missing
from `_PROVOCATIONS`." So the guard would have ridden a human obligation
the codebase explicitly declines to enforce mechanically — against a
state no current code path produces, in a change whose subject is
presentation.

Where that obligation properly lives is the served requirement *Every
rule an authoring write can provoke attributes its fault*, in the
attribution capability. If someone adds a rule naming an anchor field,
that requirement is what obliges them to think about it. A second,
weaker guard here would not have added enforcement, only the appearance
of it.

**Alternative rejected — keep the requirement and the restructuring.**
It pays a live regression for a case that cannot occur.

**Alternative rejected — prefix the fault with its `data-field` value.**
Moot once the premise falls, and wrong on its own terms: `data-field`
carries `anchor_days`, not "Days (offset)".

### The created step's marker is a class from an existing variable

`page.html` already receives `created`. The row becomes
`class="step … {% if step.identifier == created %}just-created{% endif %}"`.

The delta's "never outrun the addressing" falls out for free: the
template can only mark a step it is rendering, so a `created` naming a
step the read did not return marks nothing, which is the same condition
`_created_outside` (`playbook_admin.py:809`) already computes for the
notice. No new plumbing, and no second source of truth about what was
created.

The visual treatment is a background tint that does not fade on a timer.
A timed fade would be unassertable from a response and would punish an
admin who looked away.

### Field grouping is presentation, and carries three hard bounds

The authoring form's eleven top-level controls become grouped sections
alongside the two fieldsets that already exist. This implements no
requirement — it is taste, and `proposal.md` says taste belongs here
rather than in a spec. Recording it here is what keeps it from being
markup governed by nothing, which is the state this change exists to end.

It is bounded, and the bounds are not stylistic:

1. **No field is added, removed, renamed, or reordered in the submitted
   body.** The form's wire shape is a contract the write depends on;
   grouping is a visual regrouping of the same controls.
2. **No mark is separated from the control it concerns.** Grouping must
   not do what the rejected fault fix above would have done. This is the
   interaction that makes the two pieces of work touch: both move markup
   the fault attribution depends on for meaning.
3. **The anchor and automation fieldsets keep their existing semantics**
   — `hidden` on the anchor inputs, `disabled` on the automation
   controls. Grouping wraps; it does not re-decide which controls are
   offered.

If this work proves to enlarge the change beyond one sitting, it is the
seam to cut on: it needs no shared route, no header, and no vocabulary
token, and it is the only element here that nothing else depends on.

### The type layer is a system stack

`--font-ui: system-ui, …` and `--font-mono: ui-monospace, …`; identifiers,
gate names and anchor values take mono, prose takes UI. Nothing binary is
committed and no licence needs auditing.

This reverses the change's original framing, which called for subset
vendored faces. Subsetting is a build step in all but name, and the
delta spec now forbids one outright — `AGENTS.md` scopes this project to
pure Python with no build toolchain, and a stylesheet whose asset
pipeline lives in a developer's shell history is not "served as
committed".

### Density: one row per step, facts as marks

The facts cell currently renders a sentence —
`kind · needs confirmation · blocks its gate` (`page.html:113`). It
becomes a set of short `<span class="mark">` pills. Combined with the
flex action cell, a step's row returns to a single line.

This is the only part of the change with a number attached to it, and
the number is the point: at roughly 220px per row the seeded set renders
about four steps per screen. Verifying it is a manual check (see
**Risks**), not a test.

## Risks / Trade-offs

- **Moving `pico.min.css` breaks every template href at once, and the
  break is silent** — an unstyled page still returns 200. → The delta's
  "the stylesheet is served to an admin" scenario asserts a 200 and the
  committed bytes for the shared route; a task asserts no template still
  references `/admin/static/pico.min.css`.
- **`display: contents` on a form is the load-bearing trick and has real
  accessibility caveats in older engines.** → Confined to single-button
  forms carrying only hidden inputs, which is the case its known bugs do
  not affect. If it has to go, the fallback is `form { display: inline }`
  with the button as the inline item; the markup does not change either
  way.
- **The header's literal paths can drift from the routes' `PAGE_PATH`
  constants.** → Accepted, and narrowed: this change reduces the count of
  such literals from two in two modules to one in a shared partial.
  `import-linter` cannot help here, and inventing a URL registry for two
  paths would cost more than it saves.
- **`shared` gains a driving adapter that knows what an "admin" is.** →
  It does not: `admin_assets.py` knows only that it was handed a callable
  that either returns a principal or raises. The word "admin" is in its
  route path and its filename, not in its dependencies.
- **The density claim rests on a manual check.** → Explicitly a manual
  verification step in `tasks.md`, not a scenario. No test tier here can
  measure a rendered row's height, and writing a scenario that pretends
  otherwise would be worse than admitting the limit — the same line
  `add-step-page` drew for scroll position.
- **Restyling touches templates whose behaviour is covered by a large
  existing suite.** → That is the mitigation. The full `tests/unit` +
  `tests/agents` tier runs at commit time, so a restyle that breaks an
  assertion about markup fails immediately rather than in review.

## Migration Plan

None. No schema, data or persisted-state change, and no configuration
value added — so nothing in `deploy.yml`, `settings.py` or
`test_settings.py` moves. Deployment is templates, one moved static
file, one new router mounted in `main.py`. Rollback is a revert of the
branch.

## Open Questions

None. The three that were open when this change was drafted have been
resolved and are recorded above: the typography question (system stack),
the roster page's inclusion (in scope, hence the `shared` route), and
whether a created step is distinguished at all (yes, untimed tint) —
the last inherited from `add-step-page`'s design, which deferred it here
by name.
