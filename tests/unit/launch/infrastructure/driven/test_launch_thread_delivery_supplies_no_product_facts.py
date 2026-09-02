"""No delivery path can hand the anchor its product facts.

Derived strictly from the MODIFIED requirement in `launch-instance`:
`openspec/changes/inject-the-thread-anchor-poster/specs/launch-instance/spec.md`
— specifically the second clause's second half:

    … and SHALL NOT be composed from product facts supplied by whichever
    delivery path happens to be establishing the thread.

Covers:

- Scenario: The anchor names the product the system resolved, not what the
  caller held — its *delivery-path* half.

The application-tier half, and the other nine scenarios of that requirement,
are in `tests/unit/launch/application/test_thread_anchor_resolution.py`.
`test-manifest.md` maps all ten.

## Why this is a separate, structural file

The clause has two readings and they fail independently. The application
tier can compose the anchor from a read it takes itself — the other file
asserts that — while the *seam the four driving adapters call through*
still accepts a product name, a SKU and a marketplace and quietly forwards
them. That combination would satisfy every behavioural assertion in the
other file and still leave the permanent header depending on which of four
adapters fired first, which is the failure the clause names as its reason.

So this asserts the negative directly, on the one seam every delivery path
crosses: `establish_thread_and_resolve_mention` cannot be handed product
facts, because it does not take any.

## Level

`inspect.signature` over the module's public seam. The smallest unit that
can observe "no delivery path can supply these" is the signature itself — a
behavioural test would have to enumerate the four adapters and would still
only establish it for the four that exist today
(`ai-toolkit:testing`, *Choosing the level*). No database, no Slack, no
transaction: the module is imported, not called.

## What is fixed, and what is DERIVED

Fixed by the delta: the anchor is not composed from product facts supplied
by the establishing delivery path.

DERIVED, recorded in `test-manifest.md`:

- That the seam is named `establish_thread_and_resolve_mention`, and that
  the forbidden parameters would be spelled `product_name`, `product_sku`,
  `product_marketplace`. Both come from `tasks.md` 4.1 and from the four
  call sites as they stand, not from the delta. `_SEAM_NAMES` and
  `_FORBIDDEN` are the single correction points. The spelling risk is
  one-sided and in the safe direction: a rename would make this test stop
  *catching* rather than start *failing wrongly*, so the surviving
  parameter assertion — that what remains is the product identifier and the
  step — is asserted positively as well.

## Expected first-run state

Expected to FAIL before the change is implemented — `ai-toolkit:testing`'s
failure state 1: the seam exists and today takes all three names, so the
assertion executes and discriminates.

Baseline, taken before this was written: `uv run pytest` — 2064 passed,
135 skipped, 0 failed.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any, Final

import pytest

launch_thread_delivery = importlib.import_module(
    "commerce_ops.launch.infrastructure.driven.launch_thread_delivery"
)

_SEAM_NAMES: Final = ("establish_thread_and_resolve_mention",)

#: The three the delta forbids a delivery path from supplying.
_FORBIDDEN: Final = ("product_name", "product_sku", "product_marketplace")

#: What a delivery path may still name: which launch, and which step the
#: message is about. `tasks.md` 4.1; asserted positively so that a rename of
#: the three above cannot silently empty this file of content.
_PERMITTED: Final = ("product_id", "step")


def _seam() -> Any:
    for name in _SEAM_NAMES:
        found = getattr(launch_thread_delivery, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"`launch_thread_delivery` exposes no seam under any of {_SEAM_NAMES}; "
        "correct this file's probe to the implemented collaborator rather "
        "than deleting the assertion it guards"
    )


def test_the_delivery_seam_takes_no_product_facts() -> None:
    """SPECIFIED: the anchor "SHALL NOT be composed from product facts
    supplied by whichever delivery path happens to be establishing the
    thread".

    Three of the four adapters fall back to empty strings when their own
    catalog read returns nothing, so today a transient fault at the wrong
    instant writes a blank SKU into a header nothing can later correct. The
    clause's remedy is not "pass better facts" — it is that the facts cannot
    be passed at all.
    """
    parameters = inspect.signature(_seam()).parameters

    supplied = [name for name in _FORBIDDEN if name in parameters]
    assert not supplied, (
        f"the thread-establishment seam still accepts {supplied} from its "
        "caller. Any delivery path can therefore supply the anchor's facts — "
        "including partial ones — which is what the delta forbids, because "
        "the anchor is permanent and no later message can correct it. Its "
        f"signature is {inspect.signature(_seam())}."
    )


def test_the_delivery_seam_still_names_the_launch_and_the_step() -> None:
    """SPECIFIED, negatively: the clause governs *only* where the anchor's
    values come from. It removes nothing else, and in particular the seam
    still has to be told which launch it is establishing a thread for and
    which step the message concerns — the latter is what
    `resolve_mention_target` needs, and no part of it is in this change's
    scope.

    Paired with the test above deliberately: an implementation that made
    that one pass by gutting the seam would fail this one.
    """
    parameters = inspect.signature(_seam()).parameters

    missing = [name for name in _PERMITTED if name not in parameters]
    assert not missing, (
        f"the thread-establishment seam no longer accepts {missing}; the "
        "delta narrows where the anchor's product facts come from, and "
        "removes nothing else from this seam. Its signature is "
        f"{inspect.signature(_seam())}."
    )
