## Why

`ensure_launch_thread` lives in `launch/application/thread_establishment.py`, and it builds its own Slack client:

```python
from slack_sdk.web.async_client import AsyncWebClient


@functools.lru_cache
def _get_slack_client() -> AsyncWebClient:
    return AsyncWebClient(token=os.environ["PRODUCT_AGENT_SLACK_BOT_TOKEN"])
```

It also types its first parameter `AsyncSession`.

This contradicts the arrangement the module beneath it was written to protect. `launch_thread_delivery.py:12-17` states the intent explicitly:

> This module is `infrastructure/driven`, not `application`, on purpose: `ensure_launch_thread` and `resolve_mention_target` … take their store, lock and channel as injected ports precisely so the application layer never imports a concrete repository or `transaction()` — that composition belongs on the infrastructure side of the boundary the module-layers contract enforces.

The claim is true of the repository and of `transaction()`, and false of everything else. `ensure_launch_thread` takes `hold_lock` and `channel` as injected ports and then reaches for the Slack SDK directly, reads a credential out of the environment, and names SQLAlchemy in its own signature. Two of its four collaborators are ports and two are not, with nothing distinguishing them.

`import-linter` reports all 18 contracts kept, because its contracts govern edges inside `commerce_ops` and say nothing about third-party imports. So the boundary this project spends real effort on is being enforced on the dependencies that were never the risk, and not on the one that is: the layer described as *"domain layer … at the centre, application layer … around it, infrastructure layer (FastAPI routes, its own Slack adapter, …) on the outside"* now has its Slack adapter on the inside.

Three consequences, in ascending order of cost.

**It is the third copy of the same six lines.** `launch/infrastructure/driven/slack_notifier.py:30-32` and `briefing/infrastructure/driven/slack_notifier.py:21` are the other two. The `launch` one is in the same module tree, sits behind `post_monitoring_message`, and already does what `ensure_launch_thread` needs — it just discards the response, so it cannot hand back the `ts` that becomes the thread reference. That single missing return value is the whole reason a third client exists.

**It breaks a unit-test seam that used to hold.** `restore-the-skipped-unit-tests` identifies two tests whose only obstacle is that `establish_thread_and_resolve_mention` opens its own `transaction()` inside a Slack listener; the same reasoning covers the client. `launch_thread_delivery.py:19-23` explains that it is imported at module level *"the way `post_monitoring_message` already is: that is what lets a unit test substitute it with `monkeypatch.setattr`"* — so substitutability was a design goal, and it stops one level down at the client the application layer builds for itself.

**The anchor is composed from whatever the caller happens to be holding.** Four call sites each assemble the same four fields before calling:

```python
sku_value = ""
marketplace_value = ""
if product:
    sku = getattr(product, "sku", None)
    sku_value = sku.value if sku else ""
    marketplace = getattr(product, "marketplace_id", None)
    marketplace_value = marketplace.value if marketplace else ""
```

— `slack_entry.py:566-572`, `gate_confirmation.py:243-257`, `automation_confirmation.py:157-170`, `automation_pass.py:586-599`. Three of the four fall back to empty strings when their own catalog read returned nothing, and two of them additionally render the product identifier by its `repr` (the defect `fix-launch-thread-mentions` corrects).

`launch-instance`:513 requires the thread reference to be established once and never re-created. So the anchor is written from whichever call site happens to fire first for a launch, using whatever that site could resolve at that moment — and it is then permanent. A transient catalog failure at the wrong instant leaves a launch's thread headed `SKU: ` / `Marketplace: ` for the rest of its life, with no path to correction. The four call sites are not four places that legitimately know different things; they are four places accidentally holding the same thing in different states of completeness.

## What Changes

- **The anchor's poster becomes an injected port.** `ensure_launch_thread` receives a callable that posts a message and returns its `ts`, alongside the `hold_lock` and `channel` ports it already takes. `slack_sdk`, `os.environ` and `functools.lru_cache` leave `launch/application/thread_establishment.py` entirely, and the third `_get_slack_client()` copy is deleted rather than moved.
- **`post_monitoring_message` returns the posted message's `ts`.** That is the one missing capability that forced a separate client. Every existing caller ignores a return value today and continues to compile unchanged. `design.md` decides whether the returning form is the same function or a sibling.
- **`ensure_launch_thread` stops naming `AsyncSession`.** The parameter exists only to be handed to `hold_lock`, which is already a port; typing it against SQLAlchemy in the application layer buys nothing and states a dependency the layer does not have.
- **The anchor is composed from one authoritative read, inside `ensure_launch_thread`.** The four call sites stop assembling name/SKU/marketplace and stop passing them; the establishment path resolves the product once, at the moment it is actually about to write something permanent. Where that read fails, `design.md` settles whether the anchor is posted with what is known or the establishment is refused and retried by the next message — but the choice is made in one place, on the evidence, rather than falling out of which adapter happened to fire first.
- **The duplicated four-field extraction disappears from all four driving adapters** as a consequence, not as a separate tidy-up.
- Explicitly **not** in scope: the anchor's *wording* (`_compose_anchor_message` composes the same four facts, and `launch-entry`:10 and `launch-instance`:513 continue to govern them); the establishment race and its advisory lock, which are correct; `resolve_mention_target`, whose own defect is `fix-launch-thread-mentions`'s subject; and the two other `_get_slack_client()` copies in `launch/infrastructure/driven/slack_notifier.py` and `briefing/`, which are in the layer where a client belongs and are left alone.
- Explicitly **not** in scope: adding an `import-linter` contract for third-party imports by layer. It is the obvious follow-up and it is a separate argument — the forbidden set would have to be enumerated for every layer of every module, and getting that wrong is worse than not having it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-instance`: the requirement governing thread establishment (line 513) gains what the anchor message is composed *from* — the launch's product as the system resolves it at establishment time, once — rather than leaving it to whichever delivery path establishes the thread. Today's wording says what the anchor names (`launch-entry`:10: the product, its SKU, its marketplace, its launch date) and is silent on where those values come from, which is exactly how four call sites came to answer it four different ways, three of them able to answer with nothing. What is established, when, and that it happens exactly once are unchanged.

Nothing else is a requirement change. Which layer builds the Slack client, and whether the poster is injected, are architecture obligations recorded in `README.md`'s Architecture section and `AGENTS.md`'s summary — not behaviour any capability describes. That part of this change would carry `skip_specs: true` on its own; the anchor-composition requirement is what makes a delta necessary.

## Impact

- `src/commerce_ops/launch/application/thread_establishment.py` — loses `slack_sdk`, `os`, `functools`, `_get_slack_client`, the `AsyncSession` annotation and the caller-supplied product fields; gains a poster port and a product read. This is the module that shrinks.
- `src/commerce_ops/launch/infrastructure/driven/slack_notifier.py` — `post_monitoring_message` surfaces the `ts`.
- `src/commerce_ops/launch/infrastructure/driven/launch_thread_delivery.py` — supplies the poster port, and its docstring's claim about what the application layer never imports becomes true as written.
- `src/commerce_ops/launch/infrastructure/driving/slack_entry.py`, `gate_confirmation.py`, `automation_confirmation.py`, `automation_pass.py` — each loses the four-field extraction block and passes only the product identifier and the step.
- `src/commerce_ops/main.py`, `src/commerce_ops/worker.py` — the product read reaching `ensure_launch_thread` crosses the catalog boundary, so it comes from a composition root, as `read_product` already does in five other places. Both roots already hold a suitable reader (`_RequestScopedCatalog().get_by_id` and `_read_catalog_product`).
- Tests: `tests/unit/launch/application/test_thread_establishment_race.py` substitutes a poster instead of patching a module-level client; the two tests `restore-the-skipped-unit-tests` names stop needing a database once the transaction and the client are both behind ports. Whichever of these two changes lands second inherits a smaller job — noted in both, resolved by neither.
- No migration, no new runtime variable. `PRODUCT_AGENT_SLACK_BOT_TOKEN` is read in one fewer place, which the environment-drift check tolerates: it is still read by name in `launch/infrastructure/driven/slack_notifier.py`.
