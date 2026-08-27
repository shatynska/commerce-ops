"""The `clickup-task-client` capability's Custom Field operations.

Derived strictly from the delta spec of the OpenSpec change
`record-gate-and-discipline-as-fields`:
`openspec/changes/record-gate-and-discipline-as-fields/specs/clickup-task-client/spec.md`

Covers, from the ADDED requirement *The Custom Fields available in a folder
can be read*:

- *A folder's Custom Fields are read*
- *A folder's fields are read completely*
- *A folder with no Custom Fields reads as empty*
- *A field the capability does not anticipate does not fail the read*
- *An uninterpretable field is distinguishable from one declaring no
  options*
- *A field declaring no options is reported as such*

From the ADDED requirement *A Custom Field value can be set on an existing
task*:

- *A value is set on a task*
- *An option value is named by the option's identifier*
- *Setting the same value twice is not an error*

From the MODIFIED requirement *The tasks of a list can be read*, the three
scenarios the delta adds:

- *Tasks returned with their Custom Field values*
- *A value the client cannot interpret does not fail the read*
- *An option value reads back as it would be written*

From the MODIFIED requirement *A failed ClickUp request is surfaced to the
caller*, the two scenarios the delta adds:

- *ClickUp rejects a read of a folder's Custom Fields*
- *ClickUp rejects a Custom Field write*

## What this file does NOT cover, and why that is not an omission

`The tasks of a list can be read` carries four further scenarios and
`A failed ClickUp request is surfaced to the caller` carries six. Every one
of them is carried into the delta **verbatim** (verified by diffing the
delta's requirement blocks against the predecessor's), so each stays
covered by the tests that already exist -- `test_clickup_client.py`,
`test_clickup_client_list_and_read.py` and `test_clickup_client_tags.py` --
and none of them is touched, duplicated or superseded here. The tag
operations are likewise untouched by this change: the REMOVED delta's
Migration says so in as many words ("The client's tag operations are
untouched and remain available"). See this change's `test-manifest.md` for
the full accounting.

## What is fixed, and what is INVENTED

Fixed by this change's `tasks.md`, so treated as SPECIFIED here:

- `folder_fields(folder_id)` over `GET /api/v2/folder/{folder_id}/field`
  (task 2.3), on
  `shared/infrastructure/driven/clickup_client.py`.
- `set_task_field(task_id, field_id, value)` over
  `POST /api/v2/task/{task_id}/field/{field_id}` (task 2.5).
- That a field definition carries "identifier, name, type, and options in
  declared order, each with identifier and name" (task 2.1) and that a
  field the read could not make sense of is marked **uninterpretable**
  (task 2.3a).

INVENTED, each read through a tolerant reader so no single attribute
spelling is pinned, and each recorded in the manifest as an unresolved
project question:

- The attribute names on a field definition, its options, and on the
  task's Custom Field values. `_field_id`, `_field_name`, `_field_type`,
  `_field_options`, `_uninterpretable`, `_option_id`, `_option_name` and
  `_custom_field_values` each probe a candidate set and fail with a
  directive rather than an `AttributeError`. Correcting one of them is a
  fixture correction.
- ClickUp's own response envelopes -- `{"fields": [...]}` for the folder
  read, and `custom_fields` on a task -- follow the adapter's existing
  `/api/v2/...` convention and ClickUp's documented payloads, which
  `test_clickup_client_list_and_read.py` already pins for the list read.
- The `get_client()` cached factory used as the substitution seam, exactly
  as `test_clickup_client.py` documents it.

## Two premises this change deliberately leaves unmeasured

`tasks.md` gates both behind a measurement taken before the code they
govern is written, so the tests below are written against the
requirement's stated **obligation** rather than against a guessed wire
shape. Both are flagged in the manifest.

1. **Whether `GET /folder/{id}/field` pages** (task 2.3b). The obligation
   is completeness: "Every field the folder declares SHALL be returned, not
   only those in a first page." `test_a_folders_fields_are_read_completely`
   asserts exactly that, and its scenario states the precondition in as
   many words ("WHEN the task system returns a folder's fields in pages").
   The paging *idiom* it scripts -- successive responses, the first marked
   `last_page: False` -- is DERIVED, transcribed from the list read that
   this capability already pins. If 2.3b measures that the endpoint does
   not page, the scenario's WHEN is never satisfied and this test is
   asserting a contract nobody measured; that is a finding for `tasks.md`
   to act on, not something to resolve by weakening the test here.

2. **ClickUp's wire form for a drop-down value** (task 2.4a). The
   requirement is written against the obligation -- "Where the task system
   reports such a value in some other form, the system SHALL normalise it
   to the option identifier" -- so `test_an_option_value_reads_back_as_the
   _option_identifier` is parametrised over the plausible forms rather than
   pinning one: the option's own identifier (already normalised) and the
   option's `orderindex` (normalised from the `type_config` the same task
   payload carries, which is what "performed from what the task payload
   itself carries" permits). A form that turns out to be neither still owes
   the same obligation, and the parametrisation is where it is added.

## `pytest.raises(Exception)` is deliberate

As in `test_clickup_client.py` and `test_clickup_client_list_and_read.py`:
the requirement says only that the caller "receives an error", and no
artifact names a type. Each block is scoped to the single call under test,
per `ai-toolkit:testing`.

## Expected first-run state

`folder_fields` and `set_task_field` do not exist, and `list_tasks` reports
no Custom Field values. Every test here is expected to fail on an **absent
target** (`ImportError`, or a missing attribute on the read result). Per
`ai-toolkit:testing` that failure establishes absence and nothing about
whether the assertions below are well-formed.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` at the worktree root --
1130 passed, 0 failed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Final

import httpx
import pytest

from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.clickup_client import list_tasks

pytestmark = pytest.mark.anyio

TOKEN: Final = "test-clickup-api-token-not-a-real-credential"

FOLDER_ID: Final = "90110042424"
LIST_ID: Final = "901234002"
TASK_ID: Final = "86a1b2c3d"

GATE_FIELD_ID: Final = "4bd1f0f9-6f2a-4f0e-9d5d-0f4a1c6b2e11"
DISCIPLINE_FIELD_ID: Final = "5ce2a1f0-7a3b-4b1f-8e6e-1a5b2d7c3f22"

# The option this file writes and reads back. Its identifier and its name
# are deliberately different words, so a client that reported the option's
# *name* where the identifier is required fails rather than passes.
LISTABLE_OPTION_ID: Final = "0f7e6d5c-4b3a-2918-8776-655443332211"
LISTABLE_OPTION_NAME: Final = "listable"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# The operations under test, imported lazily so that an absent target fails
# the test that needs it rather than collection of the whole module.
# ---------------------------------------------------------------------------


def _operation(name: str) -> Any:
    operation = getattr(clickup_client, name, None)
    if operation is None:
        pytest.fail(
            f"`shared/infrastructure/driven/clickup_client.py` exposes no "
            f"`{name}`. `tasks.md` 2.3/2.5 name it; until it lands this is "
            "an absent target and nothing below it has executed."
        )
    return operation


async def _folder_fields(folder_id: str) -> Sequence[Any]:
    return await _operation("folder_fields")(folder_id=folder_id)  # type: ignore[no-any-return]


async def _set_task_field(task_id: str, field_id: str, value: Any) -> Any:
    return await _operation("set_task_field")(
        task_id=task_id, field_id=field_id, value=value
    )


# ---------------------------------------------------------------------------
# Transport seam -- transcribed from `test_clickup_client_list_and_read.py`
# ---------------------------------------------------------------------------


def _clear_client_cache() -> None:
    factory = getattr(clickup_client, "get_client", None)
    cache_clear = getattr(factory, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


@pytest.fixture(autouse=True)
def _reset_client_cache() -> Iterator[None]:
    _clear_client_cache()
    yield
    _clear_client_cache()


@pytest.fixture()
def configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKUP_API_TOKEN", TOKEN)


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    original = getattr(clickup_client, "get_client", None)
    assert original is not None, (
        "expected a `get_client()` cached factory in "
        "`shared/infrastructure/driven/clickup_client.py` -- the seam "
        "`test_clickup_client.py` already substitutes through"
    )
    monkeypatch.setattr(
        clickup_client,
        "get_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def recording_handler(
    response: httpx.Response,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return response

    return handler, captured


def paging_handler(
    pages: list[httpx.Response],
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """Serves `pages` in request order, repeating the last one.

    Keyed off request order rather than a paging parameter, for the reason
    `test_clickup_client_list_and_read.py` records: no artifact fixes
    ClickUp's paging parameter name, so keying on it would assert a
    contract nobody stated.
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return pages[min(len(captured) - 1, len(pages) - 1)]

    return handler, captured


def raising_handler(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


# ---------------------------------------------------------------------------
# Tolerant readers -- see the module docstring
# ---------------------------------------------------------------------------


_MISSING: Final = object()


def _first_attribute(subject: Any, names: Sequence[str], what: str) -> Any:
    for name in names:
        value = getattr(subject, name, _MISSING)
        if value is not _MISSING:
            return value
    if isinstance(subject, Mapping):
        for name in names:
            if name in subject:
                return subject[name]
    pytest.fail(
        f"cannot read {what} off {subject!r}: none of {list(names)} is "
        "present. Correct the reader to the implemented attribute name -- "
        "this is a fixture correction, not a change to what is asserted."
    )


def _field_id(field: Any) -> str:
    return str(_first_attribute(field, ("id", "identifier", "field_id"), "a field id"))


def _field_name(field: Any) -> str:
    return str(_first_attribute(field, ("name", "field_name"), "a field name"))


def _field_type(field: Any) -> str:
    value = _first_attribute(field, ("type", "field_type", "kind"), "a field type")
    return str(getattr(value, "value", value))


def _field_options(field: Any) -> Sequence[Any]:
    value = _first_attribute(
        field, ("options", "field_options", "choices"), "a field's options"
    )
    return tuple(value or ())


def _option_id(option: Any) -> str:
    return str(
        _first_attribute(option, ("id", "identifier", "option_id"), "an option id")
    )


def _option_name(option: Any) -> str:
    return str(_first_attribute(option, ("name", "label"), "an option name"))


def _uninterpretable(field: Any) -> bool:
    """Whether the read marked this field as one it could not make sense of.

    Probed across the spellings an implementation might plausibly choose,
    including the inverse (`interpretable`) and a status/marker string.
    Fails with a directive rather than defaulting to `False`, because a
    silent `False` would make the two scenarios that turn on this
    distinction pass against a client that draws none.
    """
    for name in ("uninterpretable", "is_uninterpretable", "unreadable"):
        value = getattr(field, name, _MISSING)
        if value is not _MISSING:
            return bool(value)
    for name in ("interpretable", "understood"):
        value = getattr(field, name, _MISSING)
        if value is not _MISSING:
            return not bool(value)
    for name in ("status", "marker", "state"):
        value = getattr(field, name, _MISSING)
        if value is not _MISSING:
            return "uninterpret" in str(getattr(value, "value", value)).lower()
    pytest.fail(
        f"the field definition {field!r} carries no marker distinguishing a "
        "field the read could not interpret from one it could. `tasks.md` "
        "2.3a requires such a field to be reported 'marked uninterpretable' "
        "and the gap definition requires it to be distinguishable from a "
        "field declaring no options."
    )


def _custom_field_values(task: Any) -> Mapping[str, Any]:
    value = _first_attribute(
        task,
        ("custom_fields", "custom_field_values", "fields", "field_values"),
        "a task's Custom Field values",
    )
    if isinstance(value, Mapping):
        return value
    pytest.fail(
        f"a task's Custom Field values came back as {value!r}, which is not "
        "keyed by field identifier. The delta requires each value to be "
        "'identified by that field's identifier'."
    )


def _by_id(fields: Sequence[Any]) -> dict[str, Any]:
    return {_field_id(field): field for field in fields}


# ---------------------------------------------------------------------------
# ClickUp payload fixtures -- DERIVED (see the module docstring)
# ---------------------------------------------------------------------------


def _option_json(identifier: str, name: str, orderindex: int) -> dict[str, Any]:
    return {"id": identifier, "name": name, "orderindex": orderindex, "color": None}


def _drop_down_json(
    identifier: str, name: str, options: Sequence[tuple[str, str]]
) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "type": "drop_down",
        "type_config": {
            "options": [
                _option_json(option_id, option_name, index)
                for index, (option_id, option_name) in enumerate(options)
            ]
        },
    }


def _gate_field_json(names: Sequence[str] = ("listable", "live")) -> dict[str, Any]:
    return _drop_down_json(
        GATE_FIELD_ID,
        "Gate",
        [
            (
                LISTABLE_OPTION_ID if name == LISTABLE_OPTION_NAME else f"opt-{name}",
                name,
            )
            for name in names
        ],
    )


def _clickup_task_json(
    identifier: str,
    *,
    custom_fields: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": identifier,
        "name": f"task {identifier}",
        "status": {"status": "to do", "type": "open", "orderindex": 1},
        "due_date": None,
        "tags": [],
    }
    if custom_fields is not None:
        payload["custom_fields"] = list(custom_fields)
    return payload


def _task_field_json(
    field_id: str,
    *,
    options: Sequence[tuple[str, str]] | None = None,
    value: Any = _MISSING,
    field_type: str = "drop_down",
) -> dict[str, Any]:
    """One entry of a task's `custom_fields` array.

    ClickUp carries the field's own definition alongside the task's value,
    which is what makes the delta's "performed from what the task payload
    itself carries" satisfiable without a second request.
    """
    payload: dict[str, Any] = {
        "id": field_id,
        "name": "Gate",
        "type": field_type,
    }
    if options is not None:
        payload["type_config"] = {
            "options": [
                _option_json(option_id, option_name, index)
                for index, (option_id, option_name) in enumerate(options)
            ]
        }
    if value is not _MISSING:
        payload["value"] = value
    return payload


# ---------------------------------------------------------------------------
# ADDED Requirement: The Custom Fields available in a folder can be read
# ---------------------------------------------------------------------------


async def test_a_folders_custom_fields_are_read(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A folder's Custom Fields are read.

    WHEN the Custom Fields of a folder are read
    THEN the caller receives each field's identifier, name and type
    AND each option of a field that declares options, with its identifier
    and name, in the order the field declares them.
    """
    declared = ("commit", "order", "listable")
    handler, captured = recording_handler(
        httpx.Response(
            200,
            json={
                "fields": [
                    _gate_field_json(declared),
                    _drop_down_json(
                        DISCIPLINE_FIELD_ID,
                        "Discipline",
                        [("opt-listing", "listing"), ("opt-finance", "finance")],
                    ),
                ]
            },
        )
    )
    install_transport(monkeypatch, handler)

    fields = await _folder_fields(FOLDER_ID)

    # SPECIFIED: the read is made at *folder* scope, naming that folder --
    # "Reading at folder scope rather than list scope is what lets a caller
    # learn the configuration without a list existing."
    assert captured, "no request was sent to ClickUp"
    assert captured[0].method == "GET"
    assert FOLDER_ID in captured[0].url.path, (
        f"the request did not name the folder: {captured[0].url}"
    )
    assert "folder" in captured[0].url.path.lower(), (
        "the read was not made at folder scope; `tasks.md` 2.3 names "
        f"`GET /api/v2/folder/{{folder_id}}/field` -- got {captured[0].url}"
    )

    by_id = _by_id(fields)
    # SPECIFIED: each field's identifier, name and type.
    assert set(by_id) == {GATE_FIELD_ID, DISCIPLINE_FIELD_ID}
    assert _field_name(by_id[GATE_FIELD_ID]) == "Gate"
    assert _field_type(by_id[GATE_FIELD_ID]) == "drop_down"

    # SPECIFIED: each option with its identifier and name, *in the order the
    # field declares them*. Asserted as a sequence, not a set: the order is
    # the whole reason this change prefers a field to a tag.
    options = _field_options(by_id[GATE_FIELD_ID])
    assert [_option_name(option) for option in options] == list(declared)
    assert _option_id(options[2]) == LISTABLE_OPTION_ID


async def test_a_folders_fields_are_read_completely(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A folder's fields are read completely.

    WHEN the task system returns a folder's fields in pages, and the Custom
    Fields of a folder declaring more fields than one page are read
    THEN every field the folder declares is returned.

    SPECIFIED: completeness. DERIVED: the paging idiom -- see premise (1)
    in the module docstring. Gated by `tasks.md` 2.3b, which takes that
    measurement before the code is written.
    """
    first = [
        _drop_down_json(f"field-{index:03d}", f"Field {index}", [("o", "option")])
        for index in range(100)
    ]
    second = [
        _drop_down_json(f"field-{index:03d}", f"Field {index}", [("o", "option")])
        for index in (100, 101)
    ]
    handler, captured = paging_handler(
        [
            httpx.Response(200, json={"fields": first, "last_page": False}),
            httpx.Response(200, json={"fields": second, "last_page": True}),
        ]
    )
    install_transport(monkeypatch, handler)

    fields = await _folder_fields(FOLDER_ID)

    identifiers = [_field_id(field) for field in fields]
    # SPECIFIED: every field the folder declares is returned, "not only
    # those in a first page".
    assert len(identifiers) == 102, (
        "the folder's fields were read incompletely -- a configured field "
        "missing from the result is reported as absent, which withholds "
        f"every write for it (got {len(identifiers)} of 102, over "
        f"{len(captured)} request(s))"
    )
    assert set(identifiers) == {f"field-{index:03d}" for index in range(102)}


async def test_a_folder_with_no_custom_fields_reads_as_empty(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A folder with no Custom Fields reads as empty.

    WHEN the Custom Fields of a folder that has none are read
    THEN the caller receives an empty result, not an error.
    """
    handler, _ = recording_handler(
        httpx.Response(200, json={"fields": [], "last_page": True})
    )
    install_transport(monkeypatch, handler)

    fields = await _folder_fields(FOLDER_ID)

    # SPECIFIED: an empty result, not an error.
    assert list(fields) == []


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        (
            "a type this capability does not anticipate",
            {
                "id": "field-formula",
                "name": "Days in gate",
                "type": "formula",
                "type_config": {"formula": 'field("due") - field("start")'},
            },
        ),
        (
            "a declared option set of a shape it was not written against",
            {
                "id": "field-formula",
                "name": "Days in gate",
                "type": "drop_down",
                "type_config": {"options": "commit,order,listable"},
            },
        ),
        (
            "an option of a shape it was not written against",
            {
                "id": "field-formula",
                "name": "Days in gate",
                "type": "drop_down",
                "type_config": {"options": [1, 2, 3]},
            },
        ),
    ],
)
async def test_a_field_the_capability_does_not_anticipate_does_not_fail_the_read(
    label: str,
    payload: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A field the capability does not anticipate does not fail
    the read.

    WHEN the Custom Fields of a folder are read and one field is of a type
    this capability does not anticipate, or carries a shape it was not
    written against
    THEN the read completes and reports every other field
    AND that field is reported with the identifier, name and type it
    carries, marked as **uninterpretable**.

    Three shapes, per `tasks.md` 2.3a ("Test with an unanticipated field
    shape alongside two well-formed ones"). Whether a *well-formed* field
    of a type that declares no options -- the first case -- is
    uninterpretable or merely optionless is an ambiguity in the delta,
    recorded in the manifest as an unresolved project question; the
    requirement's own example list names "a formula, a relationship" among
    the types it does not anticipate, which is the reading taken here.
    """
    handler, _ = recording_handler(
        httpx.Response(
            200,
            json={
                "fields": [
                    _gate_field_json(),
                    payload,
                    _drop_down_json(
                        DISCIPLINE_FIELD_ID, "Discipline", [("opt-listing", "listing")]
                    ),
                ],
                "last_page": True,
            },
        )
    )
    install_transport(monkeypatch, handler)

    # SPECIFIED: "no field SHALL cause it to raise" -- the read completes.
    fields = await _folder_fields(FOLDER_ID)

    by_id = _by_id(fields)
    # SPECIFIED: it reports every other field.
    assert {GATE_FIELD_ID, DISCIPLINE_FIELD_ID} <= set(by_id), (
        "an unanticipated field took the other fields away with it; the "
        "read must not stop them being reported"
    )
    assert "field-formula" in by_id, (
        "the unanticipated field was dropped rather than reported; the "
        "delta requires it to be reported with what it does carry"
    )

    odd = by_id["field-formula"]
    # SPECIFIED: reported with the identifier, name and type it carries.
    assert _field_name(odd) == "Days in gate"
    assert _field_type(odd) == payload["type"]
    # SPECIFIED: marked as uninterpretable.
    assert _uninterpretable(odd) is True, (
        f"a field carrying {label} was not marked uninterpretable"
    )
    # SPECIFIED, by contrast: a well-formed field is not.
    assert _uninterpretable(by_id[GATE_FIELD_ID]) is False


async def test_an_uninterpretable_field_is_distinguishable_from_an_optionless_one(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An uninterpretable field is distinguishable from one
    declaring no options.

    WHEN the Custom Fields of a folder are read and it holds both a field
    the capability cannot interpret and a field that genuinely declares no
    options
    THEN a caller can tell the two apart from what it receives
    AND neither is reported as the other.

    The control against vacuity is the well-formed gate field in the same
    read: an implementation marking *every* field uninterpretable would
    satisfy "the two differ" while telling a caller nothing.
    """
    handler, _ = recording_handler(
        httpx.Response(
            200,
            json={
                "fields": [
                    _gate_field_json(),
                    {
                        "id": "field-empty",
                        "name": "Unfilled drop-down",
                        "type": "drop_down",
                        "type_config": {"options": []},
                    },
                    {
                        "id": "field-odd",
                        "name": "Rollup",
                        "type": "drop_down",
                        "type_config": {"options": "not a list of options"},
                    },
                ],
                "last_page": True,
            },
        )
    )
    install_transport(monkeypatch, handler)

    by_id = _by_id(await _folder_fields(FOLDER_ID))

    # SPECIFIED: neither is reported as the other.
    assert _uninterpretable(by_id["field-odd"]) is True
    assert _uninterpretable(by_id["field-empty"]) is False, (
        "a field that genuinely declares no options was reported as "
        "uninterpretable; the delta forbids collapsing the two, because a "
        "caller would then tell somebody to add options to a field that "
        "already has eight"
    )
    # SPECIFIED: a caller can tell the two apart -- the optionless field is
    # reported as declaring none, which is a different fact.
    assert list(_field_options(by_id["field-empty"])) == []
    # Control: the well-formed field is neither.
    assert _uninterpretable(by_id[GATE_FIELD_ID]) is False
    assert len(_field_options(by_id[GATE_FIELD_ID])) == 2


async def test_a_field_declaring_no_options_is_reported_as_such(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A field declaring no options is reported as such.

    WHEN the Custom Fields of a folder are read and one field declares no
    options
    THEN that field is reported with no options rather than omitted or
    reported as an error.
    """
    handler, _ = recording_handler(
        httpx.Response(
            200,
            json={
                "fields": [
                    {
                        "id": "field-empty",
                        "name": "Unfilled drop-down",
                        "type": "drop_down",
                        "type_config": {"options": []},
                    }
                ],
                "last_page": True,
            },
        )
    )
    install_transport(monkeypatch, handler)

    # SPECIFIED: not reported as an error.
    fields = await _folder_fields(FOLDER_ID)

    by_id = _by_id(fields)
    # SPECIFIED: not omitted.
    assert set(by_id) == {"field-empty"}
    # SPECIFIED: reported with no options.
    assert list(_field_options(by_id["field-empty"])) == []


# ---------------------------------------------------------------------------
# ADDED Requirement: A Custom Field value can be set on an existing task
# ---------------------------------------------------------------------------


async def test_a_value_is_set_on_a_task(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A value is set on a task.

    WHEN a Custom Field value is set on a task by the task's identifier and
    the field's identifier
    THEN ClickUp receives a set-value request for that task and that field
    carrying that value.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)

    assert len(captured) == 1
    request = captured[0]
    # SPECIFIED: a set-value request for that task and that field.
    assert TASK_ID in request.url.path, (
        f"the request did not name the task: {request.url}"
    )
    assert GATE_FIELD_ID in request.url.path, (
        f"the request did not name the field: {request.url}"
    )
    # SPECIFIED: carrying that value. Asserted on the decoded body without
    # pinning the key name, which no artifact fixes.
    assert LISTABLE_OPTION_ID in request.content.decode(), (
        f"the set-value request body does not carry the value: {request.content!r}"
    )


async def test_an_option_value_is_named_by_the_options_identifier(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An option value is named by the option's identifier.

    WHEN a value drawn from a field's declared option set is set on a task
    THEN the request names that value by the option's identifier, the same
    representation the read of a list's tasks reports it in.

    Discriminating because the option's identifier and its name are
    different words here: a client sending the *name* passes
    `test_a_value_is_set_on_a_task` and fails this.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)

    body = captured[0].content.decode()
    # SPECIFIED: named by the option's identifier.
    assert LISTABLE_OPTION_ID in body
    assert LISTABLE_OPTION_NAME not in body, (
        "the set-value request named the option by its *name*; the delta "
        "requires the option's identifier, because that is the "
        "representation the read reports and the caller compares against"
    )


async def test_setting_the_same_value_twice_is_not_an_error(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Setting the same value twice is not an error.

    WHEN a Custom Field value is set on a task that already holds it
    THEN the caller receives no error.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)
    # SPECIFIED: no error on the second write of the same value.
    await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)

    assert len(captured) == 2


# ---------------------------------------------------------------------------
# MODIFIED Requirement: The tasks of a list can be read
#
# Only the three scenarios this change adds. The four carried into the
# delta verbatim stay covered by `test_clickup_client_list_and_read.py` and
# `test_clickup_client_tags.py`, untouched.
# ---------------------------------------------------------------------------


async def test_tasks_are_returned_with_their_custom_field_values(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Tasks returned with their Custom Field values.

    WHEN the tasks of a list are read and a task holds a value for a Custom
    Field
    THEN that value is reported with the task, identified by that field's
    identifier
    AND a task holding no Custom Field value is reported with none, not an
    error.
    """
    handler, _ = recording_handler(
        httpx.Response(
            200,
            json={
                "tasks": [
                    _clickup_task_json(
                        "task-valued",
                        custom_fields=[
                            _task_field_json(
                                GATE_FIELD_ID,
                                options=[(LISTABLE_OPTION_ID, LISTABLE_OPTION_NAME)],
                                value=LISTABLE_OPTION_ID,
                            )
                        ],
                    ),
                    # A field object carrying no value at all -- `tasks.md`
                    # 2.4 requires the parse to tolerate it.
                    _clickup_task_json(
                        "task-unvalued",
                        custom_fields=[
                            _task_field_json(
                                GATE_FIELD_ID,
                                options=[(LISTABLE_OPTION_ID, LISTABLE_OPTION_NAME)],
                            )
                        ],
                    ),
                ],
                "last_page": True,
            },
        )
    )
    install_transport(monkeypatch, handler)

    tasks = {task.id: task for task in await list_tasks(list_id=LIST_ID)}

    # SPECIFIED: reported with the task, identified by that field's
    # identifier.
    valued = _custom_field_values(tasks["task-valued"])
    assert GATE_FIELD_ID in valued, (
        "the task's Custom Field value is not keyed by the field's "
        f"identifier: {dict(valued)!r}"
    )
    assert valued[GATE_FIELD_ID] == LISTABLE_OPTION_ID

    # SPECIFIED: a task holding no value is reported with none, not an
    # error -- the read returned, and the field carries no value for it.
    unvalued = _custom_field_values(tasks["task-unvalued"])
    assert unvalued.get(GATE_FIELD_ID) is None, (
        "a field object carrying no value was reported as holding one: "
        f"{dict(unvalued)!r}"
    )


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("a value naming no option the field declares", "9999-not-an-option"),
        ("a value carrying several values", ["opt-a", "opt-b"]),
        ("a value of a shape this capability does not anticipate", {"nested": 7}),
    ],
)
async def test_a_value_the_client_cannot_interpret_does_not_fail_the_read(
    label: str,
    value: Any,
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A value the client cannot interpret does not fail the read.

    WHEN the tasks of a list are read and a task holds a Custom Field value
    that names no declared option, or carries several values, or is of a
    shape this capability does not anticipate
    THEN the read completes and returns every task
    AND that value is reported as the payload carries it, neither raising
    nor being reported as absent.

    Covers `tasks.md` 2.4b, which names the multi-valued and the malformed
    cases specifically.
    """
    handler, _ = recording_handler(
        httpx.Response(
            200,
            json={
                "tasks": [
                    _clickup_task_json(
                        "task-odd",
                        custom_fields=[
                            _task_field_json(
                                GATE_FIELD_ID,
                                options=[(LISTABLE_OPTION_ID, LISTABLE_OPTION_NAME)],
                                value=value,
                            )
                        ],
                    ),
                    _clickup_task_json("task-plain", custom_fields=[]),
                ],
                "last_page": True,
            },
        )
    )
    install_transport(monkeypatch, handler)

    # SPECIFIED: the read completes -- "no Custom Field value SHALL cause
    # it to raise". This read gates a launch's projection and its
    # completion intake, so a value the client cannot make sense of must
    # not be able to stop either.
    tasks = {task.id: task for task in await list_tasks(list_id=LIST_ID)}

    # SPECIFIED: returns every task.
    assert set(tasks) == {"task-odd", "task-plain"}, (
        f"{label} took another task away with it"
    )

    values = _custom_field_values(tasks["task-odd"])
    # SPECIFIED: not reported as absent -- reporting absence would destroy
    # the caller's ability to tell "nothing set" from "something the client
    # did not recognise".
    assert GATE_FIELD_ID in values and values[GATE_FIELD_ID] is not None, (
        f"{label} was reported as absent rather than as it stands: {dict(values)!r}"
    )
    # SPECIFIED: reported as the payload carries it, unnormalised.
    assert values[GATE_FIELD_ID] == value, (
        f"{label} was altered rather than reported as the payload carries "
        f"it: {values[GATE_FIELD_ID]!r} != {value!r}"
    )


@pytest.mark.parametrize(
    ("label", "reported"),
    [
        ("the option's identifier", LISTABLE_OPTION_ID),
        ("the option's orderindex", 0),
        ("the option's orderindex as a string", "0"),
    ],
)
async def test_an_option_value_reads_back_as_the_option_identifier(
    label: str,
    reported: Any,
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An option value reads back as it would be written.

    WHEN a value is set on a task from a field's declared option set, and
    the tasks of that list are then read
    THEN the value reported for that task and that field is the same option
    identifier that was written
    AND a caller comparing the two finds them equal.

    Parametrised over the plausible wire forms rather than pinning one --
    see premise (2) in the module docstring. What is SPECIFIED is the
    obligation: "Where the task system reports such a value in some other
    form, the system SHALL normalise it to the option identifier". Each
    form here is normalisable "from what the task payload itself carries",
    which is the constraint the delta puts on how.

    This is the test that stands between the change and its worst failure
    mode: a read and a write that speak different representations produce a
    successful write per task per pass, forever, changing nothing.
    """
    written: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        if "field" in request.url.path and request.method != "GET":
            written["body"] = json.loads(request.content or b"{}")
        return httpx.Response(200, json={})

    read_response = httpx.Response(
        200,
        json={
            "tasks": [
                _clickup_task_json(
                    TASK_ID,
                    custom_fields=[
                        _task_field_json(
                            GATE_FIELD_ID,
                            options=[
                                (LISTABLE_OPTION_ID, LISTABLE_OPTION_NAME),
                                ("opt-live", "live"),
                            ],
                            value=reported,
                        )
                    ],
                )
            ],
            "last_page": True,
        },
    )

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if f"/list/{LIST_ID}" in request.url.path or request.url.path.endswith("/task"):
            return read_response
        return _capture(request)

    install_transport(monkeypatch, handler)

    await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)
    tasks = {task.id: task for task in await list_tasks(list_id=LIST_ID)}

    values = _custom_field_values(tasks[TASK_ID])
    # SPECIFIED: the value reported is the same option identifier that was
    # written, whichever form ClickUp reported it in.
    assert values[GATE_FIELD_ID] == LISTABLE_OPTION_ID, (
        f"a drop-down value ClickUp reported as {label} did not normalise "
        f"to the option identifier: {values[GATE_FIELD_ID]!r}"
    )
    # SPECIFIED: a caller comparing the two finds them equal -- stated over
    # what was actually written, so this is a round trip and not two
    # independent assertions about a constant.
    assert LISTABLE_OPTION_ID in json.dumps(written.get("body")), (
        "the write did not send the option identifier, so nothing here "
        f"establishes that the two ends agree: {written!r}"
    )
    # DERIVED: the normalisation made no second request -- the delta
    # forbids obtaining a field definition separately, which would turn one
    # read into two.
    assert sum(1 for request in captured if request.method == "GET") == 1, (
        "reading the list's tasks made more than one GET; the delta "
        "forbids a second request to obtain a field definition"
    )


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A failed ClickUp request is surfaced to the caller
#
# Only the two scenarios this change adds. The enumeration now names seven
# operations; the other five stay covered by `test_clickup_client.py`,
# `test_clickup_client_list_and_read.py` and `test_clickup_client_tags.py`.
# ---------------------------------------------------------------------------


async def test_a_rejected_read_of_a_folders_custom_fields_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects a read of a folder's Custom Fields.

    WHEN ClickUp responds to a request for a folder's Custom Fields with a
    non-success status
    THEN the caller receives an error and no fields.

    `tasks.md` 2.6: the client leaves this uncaught. The pass's own
    tolerance of an unreachable ClickUp is a *caller-side* rule, covered at
    the job level, and depends on this failure actually propagating.
    """
    handler, captured = recording_handler(
        httpx.Response(401, json={"err": "Team not authorized", "ECODE": "OAUTH_017"})
    )
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified
        await _folder_fields(FOLDER_ID)

    assert len(captured) == 1


async def test_a_rejected_custom_field_write_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects a Custom Field write.

    WHEN ClickUp responds to a set-Custom-Field-value request with a
    non-success status
    THEN the caller receives an error and no result.
    """
    handler, captured = recording_handler(
        httpx.Response(400, json={"err": "Field not found", "ECODE": "FIELD_007"})
    )
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified
        await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)

    assert len(captured) == 1


async def test_the_new_operations_raise_when_clickup_is_unreachable(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable -- the two *new* operations only.

    WHEN any of the client's requests cannot reach ClickUp at all (a
    connection failure or timeout, with no response received)
    THEN the caller receives an error and no result.

    The scenario is carried into the delta verbatim and is already covered
    for the five earlier operations. It is stated over "any of the client's
    requests", and the delta's requirement statement adds two operations to
    the enumeration -- so the two new ones are covered here rather than
    left to the word "any".
    """
    install_transport(
        monkeypatch, raising_handler(httpx.ConnectError("simulated ClickUp outage"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified
        await _folder_fields(FOLDER_ID)

    install_transport(
        monkeypatch,
        raising_handler(httpx.TimeoutException("simulated ClickUp timeout")),
    )

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified
        await _set_task_field(TASK_ID, GATE_FIELD_ID, LISTABLE_OPTION_ID)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - "Authentication is configured independently of any one caller" is an
#   existing, unmodified requirement of this capability, and the delta does
#   not restate its two scenarios over the two new operations. No
#   credential-absence test is written for `folder_fields` /
#   `set_task_field` here, exactly as
#   `test_clickup_client_list_and_read.py` records for `create_list` /
#   `list_tasks`.
# - The concrete type `folder_fields` returns (sequence, tuple, iterator),
#   and what the field-definition value object is called. The delta states
#   only what each field carries.
# - What `set_task_field` returns. The delta states only that a rejection
#   reaches the caller as an error and that a repeat write is not one.
# ---------------------------------------------------------------------------
