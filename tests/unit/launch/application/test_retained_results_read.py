"""Reading every result retained for one product (`launch-step-automation`).

Derived strictly from the delta spec
`openspec/changes/add-product-dossier-page/specs/launch-step-automation/spec.md`
— the ADDED requirement *A retained result is kept and stays readable as
the product's record*, in the halves a use case over an in-memory
repository double can observe:

- *A settled result is still readable*
- *A voided result is readable and is not a rejection*
- *A voided result carries no decider*
- *A result for a step no longer served is still readable*
- *A graduated launch's results are still readable*
- *A product outside the caller's scope answers as an empty record*
- *A product with nothing retained answers emptily, not with a failure*

Its two ordering scenarios — *Results are answered newest first* and
*Results sharing a produced moment are answered in the tiebreak's order*
— are **not** covered here and are covered in
`tests/integration/launch/test_retained_results_read_live.py` instead.
`design.md` — Decision 5 puts the order in the repository's query
(`produced_at DESC, id DESC`), so a fake repository asserting it here
would only be asserting the fake. `tasks.md` 8.4 requires the tiebreak to
be asserted at the read against a real database, and says why: two
renders compared against each other pass against a query with no
tiebreak at all.

The requirement's other ADDED sibling — *The retained record covers
results held for a decision and nothing else* — is observable only once a
pass has run, and lives in
`tests/unit/launch/infrastructure/driving/test_retained_record_boundary.py`.

`test-manifest.md` at the change root records every scenario, every
assertion's classification, and the project questions this file answered
by assumption.

## Level

Every scenario above is stated over *the read* — what it answers, and
what it answers for a product the scope forbids. The use case over an
in-memory repository double is the smallest unit that can observe "the
store held it and the read still answered nothing", which is what the
out-of-scope scenario requires. It is the level
`test_scope_aware_launch_reads.py` already establishes for this module's
other scope-filtered reads, and the one `tasks.md` 1.2 names.

## The repository double filters nothing, deliberately

`_FakeResults` applies no scope and drops no row. `design.md` — Decision
4 puts the scope check in the use case and keeps the repository
policy-free, so a filter pushed down into the port would leave this
double answering everything and the scope assertions below would fail —
the honest outcome.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- A `launch/application/retained_results.py` use case, exported from
  `launch.application` (`tasks.md` 2.3, 2.5).
- That it applies `scope.permits(product_id)` and answers **emptily**,
  never raising, where the scope does not permit (`tasks.md` 2.3;
  `tasks.md` 8.5).
- That it returns a frozen record per result carrying the step
  identifier, handler, proposed outcome, produced text, produced moment,
  state, decider and decision moment — not the ORM row (`tasks.md` 2.4).
- That a voided row's absent decider is carried through as absent
  (`tasks.md` 2.6), and that the decider is never re-resolved against
  the roster (`tasks.md` 2.7; `design.md` — Decision 6).
- The four states, `voided` distinct from `rejected` (the delta, and
  `launch-step-automation` as served).

INVENTED, each recorded in the manifest with its correction point:

- The use case's **name**. `_use_case()` probes `launch.application` for
  it and fails loudly rather than defaulting. Correction point:
  `_USE_CASE_NAMES`.
- Its **call shape** — the repository first positionally, everything
  else matched by parameter name, the convention `read_launch` and
  `list_products` already follow. Correction point: `_read`.
- The **repository read's method name**. `_FakeResults` answers a list of
  plausible spellings and fails loudly, naming them, for anything else.
  Correction point: `_READ_NAMES`.
- The answered record's **attribute spellings**
  (`_ATTRIBUTE_ALIASES`), the accommodation `test_launch_reports.py` and
  `test_scope_aware_launch_reads.py` both record for a record shape no
  artifact spells.
- The stored row's own shape, taken verbatim from the `_PendingRow`
  double that `tests/unit/launch/application/
  test_automated_result_decisions.py` and `test_automation_pass.py`
  already share, plus an `id` — `design.md` — Decision 5 names the row
  identifier as the tiebreak, and nothing else here reads it.

What must survive any correction is what each test asserts: which
results are answered, what each carries, that a voided one is neither a
rejection nor decided by anyone, and that an out-of-scope product is
answered exactly as one with nothing retained.

## Expected first-run state

Neither the use case nor the record type exists (`tasks.md` 2.3–2.5), so
every test here is expected to fail on an **absent target** — the import
of `launch.application` succeeds, and `_use_case()` fails the test by
name. Per `ai-toolkit:testing`, that establishes absence only: none of
the assertions below has been exercised.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1232 passed, 96 skipped, 0 failed (2026-08-27). The 96
skips are the whole integration tier, which finds no database here and
says so.
"""

from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
OTHER_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

SERVED_STEP: Final = "listing.sub-category"
RETIRED_STEP: Final = "listing.a-step-the-playbook-no-longer-defines"
HANDLER: Final = "listing.subcategory_advisor"

ALICE_NAME: Final = "Alice Admin"
BOHDAN_NAME: Final = "Bohdan Colleague"

EARLIER: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LATER: Final = datetime(2027, 1, 7, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 7, 11, 0, tzinfo=UTC)

ACCEPTED_TEXT: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards."
REJECTED_TEXT: Final = "Sports & Outdoors > Camping & Hiking > Cookware."
VOIDED_TEXT: Final = "Toys & Games > Puzzles."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# The stored row, and the repository double
# ---------------------------------------------------------------------------


@dataclass
class _Row:
    """The stored row, the shape `test_automation_pass.py` records, plus
    the `id` `design.md` — Decision 5 names as the ordering tiebreak."""

    id: int
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: str
    result_text: str
    produced_at: datetime
    state: str = "pending"
    delivered_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


#: The read `tasks.md` 2.1 adds to `AutomatedResultRepository`. Its
#: spelling is not fixed by any artifact; these are the plausible ones.
_READ_NAMES: Final = (
    "for_product",
    "all_for_product",
    "retained_for",
    "retained_for_product",
    "results_for",
    "list_for_product",
    "by_product",
    "all_for",
)


class _FakeResults:
    """In-memory stand-in for `AutomatedResultRepository`'s new read.

    Answers the rows it was given, in the order it was given them, and
    filters nothing at all — no scope, no state, no step. Anything the
    use case reaches for under another name fails the test by name
    rather than being silently satisfied.
    """

    def __init__(self, *rows: _Row) -> None:
        self.rows: list[_Row] = list(rows)
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def _answer(self, *args: Any, **kwargs: Any) -> list[_Row]:
        self.calls.append((args, kwargs))
        wanted = _product_argument(args, kwargs)
        return [row for row in self.rows if row.product_id == wanted]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in _READ_NAMES:
            raise AttributeError(name)
        pytest.fail(
            f"the use case reached for `{name}` on the automated-result "
            f"repository; this double answers {_READ_NAMES} — correct "
            "`_READ_NAMES` to the implemented read"
        )


def _product_argument(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    for value in (*args, *kwargs.values()):
        if isinstance(value, ProductId):
            return value
    for value in (*args, *kwargs.values()):
        if isinstance(value, str):
            return value
    pytest.fail("the repository read was called with no product identifier at all")


for _name in _READ_NAMES:
    setattr(_FakeResults, _name, _FakeResults._answer)


# ---------------------------------------------------------------------------
# The use case, reached through one correction point
# ---------------------------------------------------------------------------

_USE_CASE_NAMES: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)


def _use_case() -> Any:
    """The read exposed on `launch.application` (`tasks.md` 2.3, 2.5).

    Probed rather than assumed, and failing loudly rather than
    defaulting, so nothing below can pass against something that is not
    the read.
    """
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            assert name in getattr(launch_application, "__all__", ()), (
                f"`{name}` is not in `launch.application.__all__`, so "
                "`import-linter` does not permit an adapter to reach it "
                "(`tasks.md` 2.5)"
            )
            return found
    pytest.fail(
        "no retained-results read is exported from `launch.application` "
        f"under any of {_USE_CASE_NAMES} — correct `_USE_CASE_NAMES` to "
        "the implemented name"
    )


async def _read(
    results: _FakeResults, product_id: ProductId, scope: AccessScope
) -> tuple[Any, ...]:
    """The one place to correct if the read's call shape differs.

    Assembled from the signature rather than guessed: the repository
    goes first (this project's port-passing precedent), and every other
    parameter is matched by name.
    """
    use_case = _use_case()
    parameters = inspect.signature(use_case).parameters
    names = list(parameters)
    assert names, "the retained-results read takes no arguments at all"
    arguments: dict[str, Any] = {}
    for name in names[1:]:
        if "scope" in name:
            arguments[name] = scope
        elif "product" in name or name in ("identifier", "id"):
            arguments[name] = product_id
    assert any("scope" in name for name in names), (
        "the retained-results read takes no access-scope parameter, so "
        "the caller's scope cannot reach it (`tasks.md` 2.3)"
    )
    assert any("product" in name for name in names[1:]), (
        "the retained-results read takes no product-identifier "
        "parameter, so it cannot answer 'for one product'"
    )
    return tuple(await use_case(results, **arguments))


def _parameters() -> tuple[str, ...]:
    return tuple(inspect.signature(_use_case()).parameters)


# ---------------------------------------------------------------------------
# Reading an answered record — the single correction point for spellings
# ---------------------------------------------------------------------------

_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "step_id": ("step_id", "step", "step_identifier", "identifier"),
    "handler": ("handler", "handler_name", "produced_by"),
    "proposed_outcome": (
        "proposed_outcome",
        "outcome",
        "proposal",
        "proposed",
    ),
    "result_text": ("result_text", "text", "produced_text", "result"),
    "produced_at": ("produced_at", "produced", "produced_on", "when"),
    "state": ("state", "fate", "status"),
    "decided_by": ("decided_by", "decider", "decided_by_name"),
    "decided_at": ("decided_at", "decided_on", "decision_moment"),
}


def _read_field(subject: object, field: str) -> Any:
    for name in _ATTRIBUTE_ALIASES[field]:
        if hasattr(subject, name):
            return getattr(subject, name)
    pytest.fail(
        f"{type(subject).__name__} exposes none of "
        f"{_ATTRIBUTE_ALIASES[field]} for '{field}'; the retained-result "
        "record must carry it (`tasks.md` 2.4)"
    )


def _state_of(record: object) -> str:
    """The state, whether it is answered as a string or an enum."""
    value = _read_field(record, "state")
    for attribute in ("value", "name"):
        found = getattr(value, attribute, None)
        if isinstance(found, str):
            return found.lower()
    return str(value).lower()


def _entry_for(records: tuple[Any, ...], text: str) -> Any:
    found = [
        record for record in records if str(_read_field(record, "result_text")) == text
    ]
    assert len(found) == 1, (
        f"expected exactly one answered result carrying {text!r}, got {len(found)}"
    )
    return found[0]


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _row(**overrides: Any) -> _Row:
    attributes: dict[str, Any] = {
        "id": 1,
        "product_id": PRODUCT_ID,
        "step_id": SERVED_STEP,
        "handler": HANDLER,
        "proposed_outcome": "Satisfied",
        "result_text": ACCEPTED_TEXT,
        "produced_at": EARLIER,
        "state": "pending",
    }
    attributes.update(overrides)
    return _Row(**attributes)


def _accepted() -> _Row:
    return _row(
        id=1,
        result_text=ACCEPTED_TEXT,
        produced_at=EARLIER,
        state="accepted",
        decided_by=ALICE_NAME,
        decided_at=DECIDED_AT,
    )


def _rejected() -> _Row:
    return _row(
        id=2,
        result_text=REJECTED_TEXT,
        produced_at=LATER,
        state="rejected",
        decided_by=BOHDAN_NAME,
        decided_at=DECIDED_AT,
    )


def _voided() -> _Row:
    """`void` sets the state and the decision moment and leaves
    `decided_by` untouched (`design.md` — Context; `tasks.md` 2.6)."""
    return _row(
        id=3,
        result_text=VOIDED_TEXT,
        produced_at=LATER,
        state="voided",
        decided_by=None,
        decided_at=DECIDED_AT,
    )


def _permitting(*product_ids: ProductId) -> AccessScope:
    return AccessScope.permitting(product_ids)


# ---------------------------------------------------------------------------
# Requirement: A retained result is kept and stays readable as the
# product's record
# ---------------------------------------------------------------------------


async def test_a_settled_result_is_still_readable() -> None:
    """Scenario: A settled result is still readable.

    WHEN every result retained for a product is read after one of them
    was accepted and another rejected
    THEN both are answered, each carrying the state it reached, the
    person who decided it and the moment of the decision.
    """
    results = _FakeResults(_accepted(), _rejected())

    answered = await _read(results, PRODUCT_ID, _permitting(PRODUCT_ID))

    # SPECIFIED: both are answered.
    assert len(answered) == 2

    accepted = _entry_for(answered, ACCEPTED_TEXT)
    rejected = _entry_for(answered, REJECTED_TEXT)

    # SPECIFIED: each carries the state it reached, who decided it and
    # when.
    assert _state_of(accepted) == "accepted"
    assert _read_field(accepted, "decided_by") == ALICE_NAME
    assert _read_field(accepted, "decided_at") == DECIDED_AT
    assert _state_of(rejected) == "rejected"
    assert _read_field(rejected, "decided_by") == BOHDAN_NAME
    assert _read_field(rejected, "decided_at") == DECIDED_AT

    # SPECIFIED by `tasks.md` 2.4 (the record's field set) rather than by
    # this scenario: the page cannot render what the read does not carry.
    assert str(_read_field(accepted, "step_id")) == SERVED_STEP
    assert str(_read_field(accepted, "handler")) == HANDLER
    assert "Satisfied" in str(_read_field(accepted, "proposed_outcome"))
    assert _read_field(accepted, "produced_at") == EARLIER


async def test_a_voided_result_is_readable_and_is_not_a_rejection() -> None:
    """Scenario: A voided result is readable and is not a rejection.

    WHEN every result retained for a product is read after a decision
    voided one of them
    THEN that result is answered carrying the voided state, distinct
    from a rejected one.
    """
    results = _FakeResults(_voided(), _rejected())

    answered = await _read(results, PRODUCT_ID, _permitting(PRODUCT_ID))

    voided = _entry_for(answered, VOIDED_TEXT)
    rejected = _entry_for(answered, REJECTED_TEXT)

    # SPECIFIED: answered, carrying the voided state.
    assert _state_of(voided) == "voided"
    # SPECIFIED: distinct from a rejected one — asserted against the
    # rejected row in the same answer, so "distinct" is a comparison
    # rather than a spelling.
    assert _state_of(voided) != _state_of(rejected)
    assert _state_of(rejected) == "rejected"


async def test_a_voided_result_carries_no_decider() -> None:
    """Scenario: A voided result carries no decider.

    WHEN every result retained for a product is read after a decision
    voided one of them
    THEN that result is answered with no decider, because voiding
    refuses a decision rather than recording one.
    """
    results = _FakeResults(_voided())

    answered = await _read(results, PRODUCT_ID, _permitting(PRODUCT_ID))

    voided = _entry_for(answered, VOIDED_TEXT)
    # SPECIFIED: no decider.
    assert _read_field(voided, "decided_by") is None
    # SPECIFIED by `tasks.md` 2.7 and `design.md` — Decision 6: the
    # decider is whatever the row recorded, never re-resolved. A read
    # taking a roster collaborator could not honour that.
    assert not any("roster" in name for name in _parameters()), (
        "the retained-results read takes a roster collaborator, so a "
        "decider could be re-resolved at read time (`tasks.md` 2.7)"
    )


async def test_a_result_for_a_step_no_longer_served_is_still_readable() -> None:
    """Scenario: A result for a step no longer served is still readable.

    WHEN every result retained for a product is read after the step one
    of them names has been moved out of `active`
    THEN that result is still answered.

    The read is given no playbook at all, which is what makes the step's
    lifecycle irrelevant to it; that is asserted as well as the answer,
    since a read that took one could filter on it later without any
    result-level assertion noticing.
    """
    results = _FakeResults(_row(id=4, step_id=RETIRED_STEP, state="accepted"))

    answered = await _read(results, PRODUCT_ID, _permitting(PRODUCT_ID))

    # SPECIFIED: still answered.
    assert len(answered) == 1
    assert str(_read_field(answered[0], "step_id")) == RETIRED_STEP
    # SPECIFIED, structurally: nothing about the served playbook reaches
    # the read.
    assert not any("playbook" in name or "step" in name for name in _parameters()), (
        "the retained-results read takes a playbook or step parameter, "
        "so a result for a step the playbook no longer serves could be "
        "filtered out of the record"
    )


async def test_a_graduated_launchs_results_are_still_readable() -> None:
    """Scenario: A graduated launch's results are still readable.

    WHEN every result retained for a product is read after that
    product's launch has reached `graduated`
    THEN every result retained for it is answered.

    Half of this scenario at this level: the read is keyed on the
    product and is given no launch at all, so no launch state can
    condition its answer. The other half — a real launch actually walked
    to `graduated`, with results still answered afterwards — is in
    `tests/integration/launch/test_retained_results_read_live.py`, which
    is where a launch can really graduate.
    """
    results = _FakeResults(_accepted(), _rejected(), _voided())

    answered = await _read(results, PRODUCT_ID, _permitting(PRODUCT_ID))

    # SPECIFIED: every result retained for it.
    assert len(answered) == 3
    # SPECIFIED, structurally: no launch reaches the read, so nothing
    # about a launch's gate can condition what it answers.
    assert not any("launch" in name or "gate" in name for name in _parameters()), (
        "the retained-results read takes a launch parameter, so a "
        "graduated launch could condition what it answers"
    )


async def test_a_product_outside_the_scope_answers_as_an_empty_record() -> None:
    """Scenario: A product outside the caller's scope answers as an
    empty record.

    WHEN every result retained for a product is read under a scope that
    does not permit that product's identifier
    THEN nothing is answered, exactly as for a product with nothing
    retained, and no error distinguishes the two.

    `tasks.md` 8.5: an assertion that this raises would encode the
    opposite of the requirement, so the two answers are compared against
    each other rather than each against a literal.
    """
    held = _FakeResults(_accepted(), _rejected(), _voided())
    nothing_retained = _FakeResults()
    permitting_something_else = _permitting(OTHER_PRODUCT_ID)

    # SPECIFIED: no error — the call itself must succeed.
    refused = await _read(held, PRODUCT_ID, permitting_something_else)
    empty = await _read(nothing_retained, PRODUCT_ID, _permitting(PRODUCT_ID))

    # SPECIFIED: nothing is answered, exactly as for a product with
    # nothing retained.
    assert refused == ()
    assert tuple(refused) == tuple(empty)
    # DERIVED guard: the rows really are there, so the emptiness above is
    # the scope's decision rather than an empty double.
    assert len(held.rows) == 3
    standing = await _read(held, PRODUCT_ID, _permitting(PRODUCT_ID))
    assert len(standing) == 3


async def test_a_product_with_nothing_retained_answers_emptily() -> None:
    """Scenario: A product with nothing retained answers emptily, not
    with a failure.

    WHEN every result retained for a product that has never had a result
    stored is read
    THEN nothing is answered and the read succeeds.
    """
    results = _FakeResults(_accepted())

    answered = await _read(results, OTHER_PRODUCT_ID, _permitting(OTHER_PRODUCT_ID))

    # SPECIFIED: nothing is answered, and reaching this line at all is
    # the other half — the read succeeded rather than raising.
    assert answered == ()


async def test_the_read_answers_in_the_order_the_repository_gave() -> None:
    """DERIVED, not a scenario of its own.

    `design.md` — Decision 5 puts the order in the repository's query,
    so the use case's part is to carry that order through rather than to
    impose one. The rows are handed over newest-first, as the query
    answers them, and the answer must come back in that order.

    This cannot establish the ordering rule itself — see this file's
    docstring and `tasks.md` 8.4. It exists so that a use case which
    re-sorted its answer by something of its own would be caught here
    rather than silently changing what the page renders.
    """
    newest_first = (_voided(), _rejected(), _accepted())
    results = _FakeResults(*newest_first)

    answered = await _read(results, PRODUCT_ID, _permitting(PRODUCT_ID))

    assert [str(_read_field(record, "result_text")) for record in answered] == [
        row.result_text for row in newest_first
    ]


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED here, recorded rather than omitted
#
# - *Results are answered newest first* and *Results sharing a produced
#   moment are answered in the tiebreak's order*. Both are properties of
#   the repository's query (`design.md` — Decision 5), and `tasks.md` 8.4
#   requires the tiebreak to be asserted against a real database. Covered
#   in `tests/integration/launch/test_retained_results_read_live.py`.
# - *An outcome needing no confirmation is not retained* and *A
#   non-terminal outcome is not retained*. Both need a pass to have run
#   before the read can answer nothing for the step, so no smaller unit
#   can observe them. Covered in `tests/unit/launch/infrastructure/
#   driving/test_retained_record_boundary.py`.
# ---------------------------------------------------------------------------
