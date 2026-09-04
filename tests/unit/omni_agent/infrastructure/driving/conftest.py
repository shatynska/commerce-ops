"""Shared harness for the Slack driving-adapter tests.

The wrapper and the argument for it are in `tests/support/slack.py`, which the
`launch/infrastructure/driving/` conftest also uses -- the two carried verbatim
copies of it, and one of them said so in its own docstring.
"""

from __future__ import annotations

from typing import Any

import pytest

from commerce_ops.main import app
from tests.support.slack import DrainsDeferredListeners


@pytest.fixture()
def slack_asgi_app() -> Any:
    """The application under test, with each request's deferred work drained.

    Pass this to `TestClient` instead of `commerce_ops.main.app` in any test
    that asserts on what a Slack listener did -- or did not do -- after the
    event was acknowledged.
    """
    return DrainsDeferredListeners(app)
