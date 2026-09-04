"""The stateful doubles the suite arranges around.

A fake here stands in for a production collaborator and **is not one**. It holds
state, answers queries and records writes; `values.py` beside it holds the
doubles that only carry fields.

**Every fake here reproduces the behaviour a measured population had.** A
parameter no measured declaration needed is not added because it might be
wanted, and a spelling the locals carried is dropped only where it has been
measured dead across both `src/` and `tests/` -- three of them, listed in
`share-the-stateful-fakes`'s design as clause (e) and nowhere extended.

**Declaration form is part of the contract, and for two of these it is the whole
substance.** `StubDate` subclasses `date` and `FakeSlackResponse` subclasses
`dict`: a `StubDate` that is not a `date` fails the `isinstance` checks inside
production date handling, and a `FakeSlackResponse` that is not a `dict` cannot
be indexed by the Slack SDK that receives it. Neither exposes an instance method
for the lockstep proof to intercept, so both migrate on their base class, `mypy`
and the contract tests under `tests/unit/support/` -- recorded there rather than
left to look like a proof that passed.
"""

from __future__ import annotations

from typing import Any


class FakeSlackResponse(dict[str, Any]):
    """What a stubbed `AsyncWebClient.api_call` answers with.

    A `dict` subclass, because that is what the Slack SDK's own
    `AsyncSlackResponse` is indexed as by everything downstream of it -- the
    base class is the substance, and a fake that merely *held* a payload would
    not answer `response["view"]`.

    `data` is the SDK's own spelling for the payload, and this double carries it
    because all 13 local declarations did. **Measured, nothing in `src/` or
    `tests/` reads it** -- a fourth candidate for the treatment clause (e) gives
    `members`, `__call__` and `__iter__`. It is kept anyway: that clause names
    its three cases rather than a category, precisely so it cannot be widened
    at implementation time by whoever next finds an unread spelling.
    """

    @property
    def data(self) -> dict[str, Any]:
        return dict(self)
