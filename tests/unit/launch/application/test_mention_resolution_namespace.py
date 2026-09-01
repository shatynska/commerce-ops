"""`resolve_mention_target` answers in one identity namespace.

Derived strictly from the two MODIFIED requirements in
`openspec/changes/fix-launch-thread-mentions/specs/launch-step-automation/spec.md`,
specifically the clause both of them now state:

    **Tagging a person means the message carries a mention Slack resolves
    to them.** A step's confirmer is stored as the roster's own identifier
    for that person, which Slack cannot resolve […]. The system SHALL
    resolve the step's confirmer through the roster to that person's Slack
    identity, and tag them with it.

    A named confirmer SHALL be treated as **resolvable for tagging** only
    where the roster carries them, carries them with a Slack identity, and
    carries them as still active.

This file covers the **resolution** half of the delta — what
`resolve_mention_target` answers, and what it reports when it cannot
answer. The two callers' *opposite* fallback policies on the same failure
are covered separately and per-requirement, in
`tests/unit/launch/infrastructure/driving/test_pending_result_ask_untagged_policy.py`
and `.../test_stuck_step_report_submitter_fallback.py`, because a test
asserting only this shared resolution step would pass whichever policy
each caller applied — which is the shape of assertion that let the defect
ship.

## What this file exists to catch, and why the existing tests could not

`test_thread_establishment_race.py`'s direct tests assert
`mention == "U0CONFIRMER"` against a step whose `confirmer` field was set
to a Slack-looking constant. That assertion is satisfied by returning
`step.confirmer` unchanged — i.e. by returning a roster identifier Slack
renders as inert literal text. So every test below distinguishes the two
namespaces by construction: the roster identifier and the Slack identity
are *different strings*, and each test asserts on both — the identity that
must appear and the identifier that must not.

## Level

The application function directly. It already takes its collaborators as
injected ports, so a plain call over an in-memory roster double is the
smallest unit that can observe every one of these outcomes — no Slack, no
database, no adapter. `ai-toolkit:testing`'s level rule.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- `resolve_mention_target` gains a roster reader and returns a Slack
  identity or nothing, never an identifier from another namespace
  (`proposal.md` — *What Changes*; `tasks.md` 3.1, 3.3, 3.7).
- Resolvable for tagging is three conditions: carried, with a Slack
  identity, and active (delta; `tasks.md` 3.2).
- The reader is matched on `list_people()` and `person_identifier(person)`
  — the same pair `automated_decisions.py` matches on (`tasks.md` 3.1).
- A reader that is absent, of the wrong shape, or failing resolves no
  identity and is reported rather than raised (delta; `tasks.md` 3.6).
- The roster is read only on the confirmer branch (`tasks.md` 3.4).
- The return type stays `str | None` (`tasks.md` 3.3).

INVENTED, recorded in `test-manifest.md` as unresolved project questions
with their correction points:

- The **name of the roster parameter**. `tasks.md` 3.1 says "keyword-only
  `roster: RosterReader | None`" but no artifact fixes the spelling
  against the neighbouring `read_people` convention every other roster
  consumer in `launch` uses. `_ROSTER_PARAMETER_NAMES` is the single
  correction point; the call helper reflects over the real signature and
  fails loudly rather than silently passing an argument the function
  ignores.
- That a gap is **reported through the standard library's logging**, at
  `WARNING` or above. The delta says "reported" and `design.md` points at
  `_clickup_users`'s "two warnings" as the model; nothing fixes the
  mechanism. Correction point: `_reports`.
- The person double's field spellings (`id`, `display_name`,
  `slack_identity`, `active`), copied from `_Person` in
  `test_automated_decision_roster_shape.py` rather than re-invented.

## Expected first-run state

Every test except the last two is expected to FAIL, most of them as
failure state 2 (absent target): `resolve_mention_target` takes no roster
parameter today, so `_resolve` fails the signature probe before any
assertion runs. Once the parameter lands, the remaining failures become
failure state 1.

`test_a_step_naming_no_confirmer_yields_the_submitter…` and
`test_no_step_at_all_yields_the_submitter…` are expected to fail on the
same probe but assert behaviour that is correct today and must stay
correct — `proposal.md` is explicit that the submitter branch is not in
scope. They are regression guards on the half of the function this change
must not touch.
"""

from __future__ import annotations

import inspect
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

import pytest

from commerce_ops.launch.application.thread_establishment import resolve_mention_target
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
LAUNCH_DATE: Final = date(2027, 3, 1)

#: The roster's own generated identifier for a person — `str(uuid.uuid4())`
#: per `access/application/roster.py`, as `proposal.md` records. Deliberately
#: *not* Slack-shaped, so a test cannot pass by returning it.
ALICE_ROSTER_ID: Final = "3f7c1a92-6b0e-4c7a-9d51-1e8a4b2c9f30"
ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Admin"

BOHDAN_ROSTER_ID: Final = "9a2d4e18-77c3-4f16-8b90-2c5f7a1d6e44"
BOHDAN_SLACK: Final = "U02BOHDAN"
BOHDAN_NAME: Final = "Bohdan Deactivated"

CHLOE_ROSTER_ID: Final = "c41b7f60-2e93-49aa-a0d7-5b6e83f1c208"
CHLOE_NAME: Final = "Chloe NoSlack"

#: A confirmer identifier the roster does not carry at all — reachable by
#: the one sanctioned route `design.md` names (`playbook-authoring`:107
#: case 2, a write with no roster supplied).
STRANGER_ROSTER_ID: Final = "0e5c8b31-4a77-4d2e-b118-6f9c0a3d7e52"

SUBMITTER_SLACK: Final = "U0SUBMITTER"

STEP_ID: Final = "listing.sub-category"

#: How the roster parameter may be spelled (INVENTED — see the module
#: docstring). Correction point for the implemented name.
_ROSTER_PARAMETER_NAMES: Final = (
    "roster",
    "read_people",
    "roster_reader",
    "people",
    "reader",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


@dataclass
class _Person:
    """The roster person shape, copied from `_Person` in
    `tests/unit/launch/application/test_automated_decision_roster_shape.py`
    rather than re-invented, so the two files correct together."""

    id: str
    display_name: str
    slack_identity: str | None
    active: bool = True
    clickup_user_id: str | None = None
    admin: bool = False


class _ReaderRoster:
    """A collaborator answering the one stated shape, `list_people()`, and
    nothing else — the narrowing `design.md` — Decision 2 fixed for the
    decision path, reused here because the delta says outright that the
    mention and the decision check resolve against the same pair."""

    def __init__(self, *people: _Person) -> None:
        self._people = list(people)
        self.reads = 0

    async def list_people(self) -> tuple[_Person, ...]:
        self.reads += 1
        return tuple(self._people)


class _StoreShapedRoster:
    """`load()`/`save()` and nothing else — the shape a composition root
    has actually injected by mistake once already (`proposal.md` for the
    decision path). A reader of the wrong shape, in the delta's terms."""

    def __init__(self) -> None:
        self.loads = 0

    async def load(self) -> tuple[tuple[Any, ...], int]:
        self.loads += 1
        return (), 7

    async def save(self, rows: Any, *, expected_version: int) -> None:
        return None


class _FailingRoster:
    def __init__(self) -> None:
        self.reads = 0

    async def list_people(self) -> tuple[_Person, ...]:
        self.reads += 1
        raise ConnectionError("simulated roster outage")


@dataclass(frozen=True)
class _Step:
    """Duck-typed against what mention resolution reads off a step: the
    confirmer it names, and the identifier a report can name it by."""

    confirmer: str | None
    identifier: str = STEP_ID
    name: str = "Choose the sub-category node"


def _roster() -> _ReaderRoster:
    """Alice: carried, active, with a Slack identity. Bohdan: carried,
    **deactivated**, with his Slack identity intact — `roster`:72 keeps it,
    which is exactly why the active condition has to be checked separately.
    Chloe: carried, active, with no Slack identity at all."""
    return _ReaderRoster(
        _Person(
            id=ALICE_ROSTER_ID, display_name=ALICE_NAME, slack_identity=ALICE_SLACK
        ),
        _Person(
            id=BOHDAN_ROSTER_ID,
            display_name=BOHDAN_NAME,
            slack_identity=BOHDAN_SLACK,
            active=False,
        ),
        _Person(id=CHLOE_ROSTER_ID, display_name=CHLOE_NAME, slack_identity=None),
    )


def _launch() -> Launch:
    return Launch(
        product_id=PRODUCT_ID,
        playbook_version="v1",
        current_gate="listable",
        launch_date=LAUNCH_DATE,
        submitter=SUBMITTER_SLACK,
    )


# ---------------------------------------------------------------------------
# The call, reached through one correction point
# ---------------------------------------------------------------------------

_UNSUPPLIED: Final = object()


async def _resolve(
    *,
    step: Any,
    roster: Any = _UNSUPPLIED,
    launch: Launch | None = None,
) -> str | None:
    """INVENTED call shape — the single correction point.

    The roster parameter's name is probed against the real signature
    rather than assumed, and a signature carrying none of the candidates
    fails loudly. That matters more than usual here: passing an argument
    the function silently ignores would let every test below pass by
    accident on the submitter fallback, which is the exact failure mode
    this file exists to prevent.

    `roster` left unsupplied means "no roster argument was given at all",
    as distinct from "the roster given is `None`" — the delta names both,
    and one object doing both jobs would make the absent-reader test
    unfalsifiable.
    """
    signature = inspect.signature(resolve_mention_target)
    parameters = signature.parameters

    supplied: dict[str, Any] = {"step": step}
    if roster is not _UNSUPPLIED:
        for name in _ROSTER_PARAMETER_NAMES:
            if name in parameters:
                supplied[name] = roster
                break
        else:
            pytest.fail(
                "`resolve_mention_target` accepts no roster reader under any "
                f"of {_ROSTER_PARAMETER_NAMES}; its parameters are "
                f"{tuple(parameters)}. `tasks.md` 3.1 requires one — correct "
                "`_ROSTER_PARAMETER_NAMES` to the implemented spelling"
            )

    return await resolve_mention_target(launch or _launch(), **supplied)


def _reports(caplog: pytest.LogCaptureFixture) -> str:
    """Everything reported at `WARNING` or above, as one string.

    INVENTED mechanism (see the module docstring): the delta says the gap
    "SHALL be reported" and `design.md` points at `_clickup_users`'s
    warnings as the model, but nothing fixes the channel. Correction point
    if the project reports gaps some other way.
    """
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# Scenario (both requirements): a confirmer the roster carries, active and
# with a Slack identity, is mentioned by that Slack identity
# ---------------------------------------------------------------------------


async def test_a_resolvable_confirmer_resolves_to_their_slack_identity() -> None:
    """Scenarios: *A tagged confirmer is mentioned by their Slack identity*
    and *A stuck step naming a confirmer tags that confirmer* — the
    resolution half both share.

    WHEN a pending result / report is delivered for a step naming a
    confirmer the roster carries, active and with a Slack identity
    THEN the message mentions that person by their Slack identity, and the
    roster's own identifier for them appears nowhere in it.

    SPECIFIED, and asserted in **both** directions. The positive
    assertion alone is satisfied by any implementation that happens to
    return the right string; the negative one is what the shipped defect
    would fail, because it returns `step.confirmer` — a roster identifier
    — unchanged.
    """
    roster = _roster()

    mention = await _resolve(step=_Step(confirmer=ALICE_ROSTER_ID), roster=roster)

    # SPECIFIED: the person's Slack identity.
    assert mention == ALICE_SLACK, (
        f"a resolvable confirmer resolved to {mention!r}, not to their Slack "
        f"identity {ALICE_SLACK!r}"
    )
    # SPECIFIED: and never the roster's own identifier for them. Slack
    # renders that as inert literal text and notifies nobody.
    assert mention != ALICE_ROSTER_ID
    # The roster really was read, so the answer cannot be explained by the
    # function having passed the confirmer straight through.
    assert roster.reads >= 1, (
        "the confirmer resolved without the roster ever being read, so the "
        "returned value cannot be a Slack identity the roster supplied"
    )


async def test_the_answer_is_never_a_roster_identifier() -> None:
    """Requirement statement (both requirements): the system "SHALL resolve
    the step's confirmer through the roster to that person's Slack
    identity", and `tasks.md` 3.7: the return is "a Slack identity usable
    in `<@…>` without further translation, or nothing".

    SPECIFIED, stated over the whole namespace rather than one case: no
    arrangement of the roster may make the resolver hand back an
    identifier from the roster's namespace. Parametrisation would obscure
    what this is — it is one property asserted across every reachable
    input, which is what makes it a namespace claim rather than four
    coincidences.
    """
    roster = _roster()
    identifiers = (
        ALICE_ROSTER_ID,
        BOHDAN_ROSTER_ID,
        CHLOE_ROSTER_ID,
        STRANGER_ROSTER_ID,
    )

    answers = [
        await _resolve(step=_Step(confirmer=identifier), roster=roster)
        for identifier in identifiers
    ]

    for identifier, mention in zip(identifiers, answers, strict=True):
        assert mention != identifier, (
            f"the confirmer {identifier!r} was handed back unchanged as the "
            "mention target; that is a roster identifier, which Slack leaves "
            "as inert literal text"
        )
    assert not (set(answers) & set(identifiers)), (
        f"an identifier from the roster's namespace reached a mention: {answers!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A confirmer the roster does not carry is not mentioned, and the
# gap is reported
# ---------------------------------------------------------------------------


async def test_a_confirmer_the_roster_does_not_carry_resolves_to_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: *A confirmer the roster does not carry is not mentioned,
    and the gap is reported* — its resolution half.

    WHEN a pending result is delivered for a step naming a confirmer the
    roster does not carry
    THEN the message […] carries no mention and does not tag the
    submitter, and the unresolvable confirmer is reported.

    SPECIFIED. The "does not tag the submitter" clause is asserted here as
    well as at the ask's own call site, because if the *resolver* returned
    the submitter there would be no way for either caller to tell "this
    step names no confirmer" from "this step's confirmer cannot be
    reached" — the distinction `design.md` builds both policies on.
    """
    roster = _roster()

    with caplog.at_level(logging.WARNING):
        mention = await _resolve(
            step=_Step(confirmer=STRANGER_ROSTER_ID), roster=roster
        )

    # SPECIFIED: no identity resolves.
    assert mention is None, (
        f"a confirmer the roster does not carry resolved to {mention!r}"
    )
    # SPECIFIED: and specifically not the submitter, which would collapse
    # two different facts into one message.
    assert mention != SUBMITTER_SLACK

    # SPECIFIED: the gap is reported, naming the step, the launch and the
    # unresolvable confirmer.
    reported = _reports(caplog)
    assert STRANGER_ROSTER_ID in reported, (
        f"the report does not name the unresolvable confirmer: {reported!r}"
    )
    assert STEP_ID in reported, f"the report does not name the step: {reported!r}"
    assert PRODUCT_ID.value in reported, (
        f"the report does not name the launch: {reported!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A deactivated confirmer is not mentioned, and the gap is
# reported
# ---------------------------------------------------------------------------


async def test_a_deactivated_confirmer_resolves_to_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: *A deactivated confirmer is not mentioned, and the gap is
    reported* — its resolution half.

    WHEN a pending result is delivered for a step whose named confirmer has
    been deactivated on the roster
    THEN the message is still delivered, carrying no mention and not
    tagging the submitter, and the deactivated confirmer is reported — the
    decision could not be accepted from them in any case.

    SPECIFIED, and the case the delta calls out as the reachable, durable
    one. Bohdan's Slack identity is intact on the roster — `roster`:72
    preserves it through deactivation — so an implementation that checked
    only "carried, with a Slack identity" would return `U02BOHDAN` here
    and pass every other test in this file. That is why the double carries
    his identity rather than omitting it.
    """
    roster = _roster()

    with caplog.at_level(logging.WARNING):
        mention = await _resolve(step=_Step(confirmer=BOHDAN_ROSTER_ID), roster=roster)

    # SPECIFIED: not resolvable for tagging, though the identity survives.
    assert mention is None, (
        f"a deactivated confirmer resolved to {mention!r}; a decision from "
        "them would be refused, so the mention is a guaranteed-refused summons"
    )
    assert mention != BOHDAN_SLACK, (
        "a deactivated confirmer's surviving Slack identity was used as the "
        "mention target"
    )
    assert mention != SUBMITTER_SLACK

    # SPECIFIED: the gap is reported.
    reported = _reports(caplog)
    assert BOHDAN_ROSTER_ID in reported, (
        f"the deactivated confirmer was not reported: {reported!r}"
    )


# ---------------------------------------------------------------------------
# Requirement statement: "carries them with a Slack identity"
# ---------------------------------------------------------------------------


async def test_a_confirmer_with_no_slack_identity_resolves_to_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Requirement statement (both requirements): resolvable for tagging
    only where the roster "carries them with a Slack identity".

    SPECIFIED as a condition, with no scenario of its own — the delta
    states the three conditions in the requirement body and gives scenarios
    to two of them. `design.md` explains why: `roster`:10 forbids this
    state and `Person.faults()` enforces it, so the branch is
    defence-in-depth rather than a state the specifications say occurs.
    Covered here rather than omitted so that the condition is observable
    at all, and recorded in `test-manifest.md` as the defence-in-depth
    branch it is.
    """
    roster = _roster()

    with caplog.at_level(logging.WARNING):
        mention = await _resolve(step=_Step(confirmer=CHLOE_ROSTER_ID), roster=roster)

    assert mention is None, (
        f"a confirmer the roster carries without a Slack identity resolved to "
        f"{mention!r}"
    )
    assert mention != SUBMITTER_SLACK
    assert CHLOE_ROSTER_ID in _reports(caplog), (
        "a confirmer carried without a Slack identity was not reported"
    )


# ---------------------------------------------------------------------------
# Scenario: A pending result is delivered untagged when the roster cannot be
# read  /  Scenario: A stuck step is reported to the submitter when the
# roster cannot be read — the resolution half both share
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "make_roster"),
    [
        pytest.param("absent", lambda: None, id="absent-reader"),
        pytest.param("wrong-shape", _StoreShapedRoster, id="store-shaped-reader"),
        pytest.param("failing", _FailingRoster, id="failing-reader"),
    ],
)
async def test_a_roster_that_cannot_be_read_resolves_no_identity_and_is_reported(
    label: str, make_roster: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenarios: *A pending result is delivered untagged when the roster
    cannot be read* and *A stuck step is reported to the submitter when the
    roster cannot be read* — the resolution half both share.

    WHEN […] the roster cannot be read at all
    THEN […] the roster failure is reported.

    SPECIFIED, over all three ways the delta names ("no reader, a reader of
    the wrong shape, or one that fails"). Each is parametrised rather than
    collapsed, because they fail at three different points and an
    implementation can easily catch one and not the others.

    SPECIFIED, and the assertion that matters most here: this **must not
    raise**. `design.md` is explicit that this is the opposite disposition
    from `_roster_or_fail` — there the roster read *is* the decision, here
    it is an embellishment on a message whose substance does not depend on
    it. A raised error would fail the whole delivery to avoid a degraded
    mention.
    """
    roster = make_roster()

    with caplog.at_level(logging.WARNING):
        mention = await _resolve(step=_Step(confirmer=ALICE_ROSTER_ID), roster=roster)

    # SPECIFIED: no identity resolves, and nothing is raised.
    assert mention is None, (
        f"an unreadable roster ({label}) resolved a mention anyway: {mention!r}"
    )
    # SPECIFIED: the roster failure is reported.
    assert _reports(caplog), (
        f"an unreadable roster ({label}) was not reported at all; the delta "
        "requires the failure to be reported, never silently swallowed"
    )


async def test_a_roster_argument_omitted_entirely_resolves_no_identity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Requirement statement: "no reader" is one of the three ways the
    roster cannot be read.

    SPECIFIED. Distinguished from `roster=None` above deliberately: a
    deployment where the composition root never assigned the module global
    reaches the function with the parameter at its default, which is a
    different code path from one passed `None` explicitly, and `tasks.md`
    3.6 names "absent (never injected)" as its own case.

    Also a regression guard on `tasks.md` 3.3: with no roster argument the
    function must still be *callable*, so the gate ask and the launch
    confirmation stay genuinely untouched.
    """
    with caplog.at_level(logging.WARNING):
        mention = await _resolve(step=_Step(confirmer=ALICE_ROSTER_ID))

    assert mention is None, (
        f"a confirmer resolved to {mention!r} with no roster reader supplied "
        "at all; nothing could have translated the identifier"
    )
    assert mention != ALICE_ROSTER_ID


# ---------------------------------------------------------------------------
# Scenario: A stuck step naming no confirmer tags the submitter — and the
# rule this change must not touch
# ---------------------------------------------------------------------------


async def test_a_step_naming_no_confirmer_yields_the_submitter_without_reading_the_roster(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: *A stuck step naming no confirmer tags the submitter*.

    WHEN a report is delivered for a stuck step that names no confirmer
    THEN the message tags the launch's submitter instead.

    SPECIFIED, and unchanged by this delta — `proposal.md` puts the
    `step`/no-`step` rule explicitly out of scope. Kept here as a
    regression guard, because the roster read this change adds is the
    obvious place to accidentally make every mention depend on the roster.

    SPECIFIED (`tasks.md` 3.4, from the delta's "The launch's submitter is
    already a Slack identity and needs no resolution, which is why a step
    naming no confirmer is unaffected by whether the roster can be read"):
    the roster is **not read** on this branch. Asserted rather than
    assumed, because "unaffected by whether the roster can be read" is a
    property no equality on the return value can observe.
    """
    roster = _roster()

    with caplog.at_level(logging.WARNING):
        mention = await _resolve(step=_Step(confirmer=None), roster=roster)

    assert mention == SUBMITTER_SLACK
    assert roster.reads == 0, (
        "the roster was read for a step naming no confirmer; the submitter "
        "needs no translation, and reading anyway makes this branch fail "
        "whenever the roster does"
    )
    assert not _reports(caplog), (
        f"a step naming no confirmer reported a gap: {_reports(caplog)!r}. "
        "There is no gap — this is the routine case, and it must not read in "
        "the record like a confirmer who cannot be reached"
    )


async def test_no_step_at_all_yields_the_submitter_without_reading_the_roster() -> None:
    """The gate-ask path: `gate_confirmation.py` calls with no step at all.

    SPECIFIED as unchanged (`proposal.md`: "The gate ask is **not**
    affected"; `tasks.md` 5.1). A regression guard on the one call site
    this change promises not to edit — if this starts touching the roster,
    a gate ask breaks during a roster outage for no reason of its own.
    """
    roster = _roster()

    mention = await _resolve(step=None, roster=roster)

    assert mention == SUBMITTER_SLACK
    assert roster.reads == 0


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That `resolve_mention_target`'s declared return type is `str | None`
#   (`tasks.md` 3.3). A static guarantee, verified by `uv run mypy`; no
#   runtime assertion can observe a type annotation without pinning the
#   annotation's spelling, which would fail for the wrong reason.
# - That the identifier match uses `person_identifier(person)` specifically
#   rather than reading `.id` directly (`tasks.md` 3.1). The double above
#   spells the field `id`, which both readings satisfy; distinguishing them
#   would mean asserting on the implementation's choice of helper rather
#   than on behaviour. What the requirement actually binds — that the
#   mention and the decision check never disagree about who the confirmer
#   is — is observable only across both paths, and is covered by the
#   identifier spelling being shared with
#   `test_automated_decision_roster_shape.py`'s `_Person`.
# ---------------------------------------------------------------------------
