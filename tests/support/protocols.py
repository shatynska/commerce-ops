"""The shapes the shared fakes are checked against.

**Intentionally empty, and not an accident.** No protocol is declared here yet
and nothing imports this module: `share-the-unit-test-harness` delivered the
constants, the HTML harness, the admin session, the fixtures and the step
builder, and cut the shared *fakes* to a follow-up change. The rules below are
what that change is held to, recorded now so the first fake is written against
them rather than after them. If you are reading this expecting protocols and
finding none, none were deleted -- they were never written.


A `Protocol` declared beside a fake checks nothing on its own: `mypy` compares
a class to a protocol only where a value is assigned to a protocol-annotated
target. So every fake in this package carries, beside it::

    _conforms: SomeProtocol = TheFake()

That assignment -- not this module's existence -- is what makes a double which
has stopped matching its subject a type error rather than something a reader
has to notice. `uv run mypy .` already runs strict over `tests/`, so it costs
one line per fake and nothing at runtime.

**Completeness carries the same-value invariant with it.** Production reads
several of these shapes by probing attribute names in order --
`gate_progression_job._awaiting_gate` returns the first of
`("awaiting_gate", "gate_id", "current_gate")` that is a non-empty string, and
`clickup_sync._members` tries `list_members()`, then a callable, then a plain
iterable. Modelling every name a probe reads is only safe if the added
spellings agree with the one they displace; otherwise completeness silently
redirects the probe to an earlier branch and the test exercises a path it did
not before. So:

    Where a fake adds a spelling a production probe reads earlier in its
    branch order than the spelling the local variants populated, the added
    spelling carries the same value as the one it displaces. An added
    attribute the probe reads as a guard or as a sequence defaults to the
    value the fall-through produced.

These protocols are **temporary**. `unify-launch-adapter-dependencies` defines
the boundary collaborators as protocols in `src/`, and when it lands these are
replaced by imports of the real ones -- two definitions of one boundary is the
disagreement this change exists to end. They live here rather than in `src/`
only because that change has not landed yet.

Each protocol is added by the task that adds its fake, never up front: the
shape comes from reading the local variants being replaced, so authoring one
before that reading would be guessing at it.
"""

from __future__ import annotations
