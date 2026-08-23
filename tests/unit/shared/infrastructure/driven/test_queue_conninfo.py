"""Regression guard: the queue's connection string survives a real password.

NOT derived from a spec scenario, and deliberately so -- this guards a defect
found in production, not a requirement. `replace-cron-with-job-runner` shipped
a `queue_conninfo()` that swapped the `postgresql+asyncpg://` prefix for
`postgresql://` and handed the remainder to psycopg. With the deployment's
actual `POSTGRES_PASSWORD`, which contains a `/`, libpq's URI parser read the
username as the host and part of the password as the port:

    WARNING psycopg.pool error connecting in 'pool-1': failed to resolve host
    'commerce_ops': [Errno -8] Servname not supported for ai_socktype

The worker could not reach the queue at all, while `app` stayed healthy --
SQLAlchemy parses the same URL itself and never hands the raw string to libpq,
so nothing else in the deployment showed the fault. Every test in the suite
used an alphanumeric password, which is why none of them caught it.
"""

from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.engine import make_url

from commerce_ops.shared.infrastructure.driven.job_runner import queue_conninfo

# Characters that carry meaning inside a URI and must survive anyway. The
# first is the one the deployment actually used.
HOSTILE_PASSWORDS = (
    "sla/sh",
    "a/b+c",
    "has:colon",
    "q?uery",
    "hash#mark",
    "sp ace",
    "amp&ersand",
    "eq=uals",
    "plus+sign",
)

# The two characters that genuinely cannot survive unencoded, because the URL
# itself becomes ambiguous: `@` separates userinfo from host, and `%`
# introduces a percent-escape. Both must be encoded by whatever builds
# `DATABASE_URL`. They are listed to mark the boundary, not to excuse it --
# see the test at the bottom, which pins that the application's own engine
# reads them exactly as wrongly, so this is a deployment constraint rather
# than a defect in the queue's derivation.
AMBIGUOUS_IN_A_URL = ("p@ssword", "per%cent")


def _url(password: str) -> str:
    return f"postgresql+asyncpg://commerce_ops:{password}@postgres:5432/commerce_ops"


@pytest.mark.parametrize("password", HOSTILE_PASSWORDS)
def test_the_connection_details_survive_a_password_with_uri_syntax(
    password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every component arrives intact, whatever the password contains.

    Asserted component by component rather than as one string: the failure
    this guards against did not produce an error at construction, it produced
    a *plausible* connection string aimed at the wrong host.
    """
    monkeypatch.setenv("DATABASE_URL", _url(password))

    parsed = conninfo_to_dict(queue_conninfo())

    assert parsed["host"] == "postgres", (
        f"a password containing {password!r} moved the host to "
        f"{parsed['host']!r}; the queue would connect somewhere else entirely"
    )
    assert str(parsed["port"]) == "5432"
    assert parsed["user"] == "commerce_ops"
    assert parsed["dbname"] == "commerce_ops"
    assert parsed["password"] == password, (
        "the password was altered in transit, so authentication would fail "
        "even once the host is right"
    )


def test_an_absent_database_url_is_reported_rather_than_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No silent fallback to libpq's own defaults.

    Without this, an unset `DATABASE_URL` would let psycopg fall back to
    PG* environment variables or local socket defaults -- connecting to
    *something*, which is worse than not connecting at all.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        queue_conninfo()


@pytest.mark.parametrize("password", AMBIGUOUS_IN_A_URL)
def test_an_ambiguous_password_misleads_the_application_engine_too(
    password: str,
) -> None:
    """The boundary, pinned rather than assumed.

    `@` and `%` cannot be recovered from an unencoded URL by anything reading
    it, so the queue's derivation is not what would need fixing. This asserts
    that SQLAlchemy -- which builds the application's own engine from the same
    variable -- reads such a URL just as wrongly. If a future SQLAlchemy makes
    this work, this test fails and the queue's derivation should be revisited
    to match, rather than the two quietly diverging.
    """
    url = make_url(_url(password))

    assert (url.host, url.password) != ("postgres", password), (
        f"SQLAlchemy now recovers {password!r} from an unencoded URL; the "
        "queue's own derivation should be revisited to match"
    )
