"""`FakeSlackResponse`'s contract, stated directly.

**These are the primary check for this double, not a supplement.** It exposes no
instance method and constructs no state, so the lockstep proof of
`share-the-stateful-fakes` has nothing to intercept and does not run for it
(design.md Decision 2). What stands in its place is this module, the `dict` base
class, and the `_conforms` assignment in `tests/support/protocols.py`.
"""

from __future__ import annotations

from typing import Any

from tests.support.fakes import FakeSlackResponse


def test_reads_as_the_dict_the_slack_sdk_hands_back() -> None:
    """Indexing is the substance: the SDK's own response is read this way."""
    response = FakeSlackResponse({"ok": True, "view": {"id": "V0VIEW"}})

    assert response["ok"] is True
    assert response["view"] == {"id": "V0VIEW"}
    assert response.get("missing") is None
    assert len(response) == 2


def test_carries_the_whole_payload_under_the_sdk_s_own_spelling() -> None:
    payload: dict[str, Any] = {"ok": True, "ts": "1700000000.000100"}

    assert FakeSlackResponse(payload).data == payload


def test_answers_data_with_a_copy_rather_than_itself() -> None:
    """A caller that edits what it read must not edit the response.

    The local declarations all wrote `dict(self)` rather than returning `self`,
    and a shared double returning `self` would leave every assertion identical
    while handing out a mutable view of the response.
    """
    response = FakeSlackResponse({"ok": True})

    read = response.data
    read["ok"] = False

    assert response["ok"] is True


def test_an_empty_response_is_empty_rather_than_absent() -> None:
    response = FakeSlackResponse()

    assert response.data == {}
    assert not response


def test_builds_from_keywords_as_well_as_from_a_mapping() -> None:
    assert FakeSlackResponse(ok=True).data == FakeSlackResponse({"ok": True}).data
