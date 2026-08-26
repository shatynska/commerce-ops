"""The shared guarded route serving the admin surfaces' presentation
assets (`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/admin-presentation-vocabulary/specs/playbook-admin/spec.md`
— ADDED *The presentation assets stay behind the admin guard and need no
build step*, all three scenarios. The scenario *No build artifact stands
between source and response* has a second half — "the admin surfaces load
their stylesheet successfully" — which is about the pages rather than the
route, and is covered in
`tests/unit/launch/infrastructure/driving/
test_admin_surface_navigation_and_assets.py`. The roster surface's own
copy of the refusal scenario lives in
`tests/unit/access/infrastructure/driving/
test_roster_admin_presentation_vocabulary.py`, driven from the href that
page renders.

The manifest at
`openspec/changes/admin-presentation-vocabulary/test-manifest.md` records
every scenario, every assertion's classification, and the project
questions this file answered by assumption.

**Level.** The route alone, mounted in an app of its own with its guard
injected. The requirement is about the route's guard and its bytes;
nothing about a page is needed to observe either, and mounting a page
would only add a way for this to fail for an unrelated reason.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- That the route lives in
  `commerce_ops.shared.infrastructure.driving.admin_assets`, exposes
  `router`, and takes its guard from a module-level `verify` the
  composition root injects — and that an **un-injected** `verify`
  refuses rather than serving (`tasks.md` 1.2, 1.2a; `design.md` — *The
  shared asset route lives in `shared`, with its guard injected*, which
  states the reason: a route failing open would answer 200 to an
  anonymous caller while every other admin path answered 404, an
  existence oracle for the admin surface).
- That refusal is the app's own 404, identical to an unregistered route.
- That the assets are served from
  `src/commerce_ops/shared/infrastructure/driving/static/`, and that
  `pico.min.css` moves there while `htmx.min.js` stays in `launch`
  (`tasks.md` 1.1; `proposal.md` — Impact).
- That the stylesheet the vocabulary adds is `vocabulary.css`
  (`tasks.md` 2.1).
- That the traversal guard from `playbook_admin`'s `static_asset` is
  copied verbatim (`tasks.md` 1.3).

INVENTED, each recorded in the manifest with its correction point:

- The session cookie name and the shape of the verification call, taken
  from the sibling admin-page tests. Correction points: `_SESSION_COOKIE`,
  `_fake_verify`.

## What this file deliberately does NOT cover

- **The traversal guard** `tasks.md` 1.3 asks be copied verbatim. Every
  probe that would exercise it is normalised away before the route sees
  it: `TestClient` unquotes the path, so `..%2Ffoo` arrives as two
  segments and never matches the single-segment route, and a literal
  `..` is collapsed by the client. A test written against it would pass
  on the router's own path matching rather than on the guard — a pass
  for the wrong reason. The guard is a code-review obligation here, not
  a testable one. Recorded in the manifest as deliberately untested.
- That no build step exists **in general**. A test can establish that the
  asset is committed and that what a running application serves is those
  same bytes with nothing run in between; it cannot prove the absence of
  a step nobody wrote. `tasks.md` 7.2's grep and the reviewer reading the
  diff carry the rest.

## Expected first-run state

`commerce_ops.shared.infrastructure.driving.admin_assets` does not exist,
so every test here fails at the *absent-target* state, each with that
message. The assertions never execute, so nothing below has been
exercised and none of it is evidence about the route yet.

The module is resolved by name rather than imported at the top of the
file deliberately: a hard import would make its absence a **collection
error**, and pytest stops the whole run on one — which would leave the
951 tests that have nothing to do with this change unreported while it
is missing.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 954 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26).
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

#: The route under test. Resolved by name rather than imported, so that
#: its absence fails each test here with its own message instead of
#: interrupting collection for the whole suite — the absent-target state
#: is reported either way, and this way the rest of the suite still runs.
_ROUTE_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"


def _assets_module() -> ModuleType:
    try:
        return importlib.import_module(_ROUTE_MODULE_NAME)
    except ModuleNotFoundError:
        pytest.fail(
            f"{_ROUTE_MODULE_NAME} does not exist — the absent-target state. "
            "Nothing below has executed, so none of this file's assertions "
            "have been exercised and none of them is evidence about the "
            "route yet."
        )


PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

#: tests/unit/shared/infrastructure/driving/<this file>
_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_ASSET_DIR: Final = _REPO_ROOT / "src/commerce_ops/shared/infrastructure/driving/static"

#: The assets the admin surfaces load from the shared route: the
#: vocabulary this change adds, and the substrate it layers over, which
#: moves here so both surfaces can reach it.
_SHARED_ASSETS: Final = ("vocabulary.css", "pico.min.css")


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    """Answers the principal only for the one known session value,
    whatever the verification call shape is."""
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _client(monkeypatch: pytest.MonkeyPatch, *, signed: bool) -> TestClient:
    module = _assets_module()
    monkeypatch.setattr(module, "verify", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    if signed:
        client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _unguarded_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The route as a mis-wired composition root would leave it: `verify`
    still at its un-injected default."""
    module = _assets_module()
    monkeypatch.setattr(module, "verify", None)
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


def _asset_path() -> str:
    """The route's own path template, with its one parameter left to be
    filled — discovered rather than spelled, so a moved URL fails here
    with its own message."""
    candidates = [
        path
        for route in _assets_module().router.routes
        if (path := getattr(route, "path", None))
        and "GET" in (getattr(route, "methods", None) or set())
        and "{" in path
    ]
    if len(candidates) != 1:
        pytest.fail(
            f"the shared asset router exposes {len(candidates)} parameterised "
            f"GET routes ({candidates}); this file expects exactly one — "
            "correct `_asset_path` to the implemented router"
        )
    return str(candidates[0])


def _url_for(asset: str) -> str:
    path = _asset_path()
    start = path.index("{")
    end = path.index("}", start)
    return path[:start] + asset + path[end + 1 :]


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


def _committed(asset: str) -> bytes:
    path = _ASSET_DIR / asset
    if not path.is_file():
        pytest.fail(
            f"{path} is not in the repository, so there is nothing committed "
            "for the route to serve as committed — correct `_ASSET_DIR` or "
            "`_SHARED_ASSETS` to where the change put the assets"
        )
    return path.read_bytes()


# ---------------------------------------------------------------------------
# ADDED requirement: The presentation assets stay behind the admin guard
# and need no build step
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("asset", _SHARED_ASSETS)
def test_the_stylesheet_is_refused_without_an_admin_session(
    monkeypatch: pytest.MonkeyPatch, asset: str
) -> None:
    """Scenario: The stylesheet is refused without an admin session.

    WHEN the stylesheet is requested with no admin session cookie
    THEN the response is the same 404 an unregistered route returns
    AND carries no stylesheet content.

    Parametrised over both assets the shared route serves: a guard
    applied to the new stylesheet while `pico.min.css` moved out from
    behind `launch`'s guard and lost it would satisfy the scenario as
    written and still open the admin surface's substrate to anyone.
    """
    anonymous = _client(monkeypatch, signed=False)
    signed = _client(monkeypatch, signed=True)

    nothing = _shape(anonymous.get("/a-route-that-was-never-registered"))
    refused = anonymous.get(_url_for(asset))
    served = signed.get(_url_for(asset))

    # DERIVED guard: the asset really is served to an admin, so the
    # refusal below is the guard and not a dead route.
    assert served.status_code == 200, (
        f"{asset} is not served even to an admin, so the refusal says nothing "
        "about the guard"
    )
    # SPECIFIED: the same 404 an unregistered route returns.
    assert _shape(refused) == nothing, (
        f"{asset} answers {refused.status_code} to an anonymous caller, which "
        "differs from what an unregistered route answers — an existence "
        "oracle for the admin surface"
    )
    # SPECIFIED: and carries no stylesheet content.
    assert served.content not in refused.content, (
        f"the refusal for {asset} carries the asset itself"
    )


@pytest.mark.parametrize("asset", _SHARED_ASSETS)
def test_an_uninjected_guard_refuses_rather_than_serving(
    monkeypatch: pytest.MonkeyPatch, asset: str
) -> None:
    """`tasks.md` 1.2a and `design.md` — *The shared asset route lives in
    `shared`, with its guard injected*: an **un-injected** `verify` SHALL
    refuse with the same bare 404.

    This is the requirement's own reasoning made assertable — "the
    stylesheet SHALL be served only to a caller holding a valid admin
    session". A route defaulting to serving when the composition root
    forgot to wire it serves a caller holding no session at all, which is
    the guarantee's failure and not an edge case outside it. Absent a
    guard is not the same as passing one.

    SPECIFIED by the requirement, through the design decision `tasks.md`
    1.2a records; it carries no scenario of its own.
    """
    unguarded = _unguarded_client(monkeypatch)

    nothing = _shape(unguarded.get("/a-route-that-was-never-registered"))
    response = unguarded.get(_url_for(asset))

    assert _shape(response) == nothing, (
        f"with `verify` un-injected the route answers {response.status_code} "
        f"for {asset} rather than the app's own 404 — a mis-wired composition "
        "root would leave the admin surface's assets open to anyone while "
        "every other admin path answered 404"
    )


@pytest.mark.parametrize("asset", _SHARED_ASSETS)
def test_the_stylesheet_is_served_to_an_admin(
    monkeypatch: pytest.MonkeyPatch, asset: str
) -> None:
    """Scenario: The stylesheet is served to an admin.

    WHEN the stylesheet is requested with a valid admin session
    THEN it is served
    AND its bytes are those of the file committed to the repository.
    """
    signed = _client(monkeypatch, signed=True)
    committed = _committed(asset)

    response = signed.get(_url_for(asset))

    # SPECIFIED: it is served.
    assert response.status_code == 200, (
        f"{asset} answers {response.status_code} to an admin: {response.text[:400]}"
    )
    # SPECIFIED: and its bytes are those of the file committed to the
    # repository — what a reviewer reads in the diff is what a browser
    # receives.
    assert response.content == committed, (
        f"what the route serves for {asset} is not byte-identical to "
        f"{(_ASSET_DIR / asset)} — something stands between the source and "
        f"the response ({len(response.content)} bytes served against "
        f"{len(committed)} committed)"
    )


@pytest.mark.parametrize("asset", _SHARED_ASSETS)
def test_no_build_artifact_stands_between_source_and_response(
    monkeypatch: pytest.MonkeyPatch, asset: str
) -> None:
    """Scenario: No build artifact stands between source and response.

    WHEN the repository is checked out and the application is started
    with no build or asset step run
    THEN the admin surfaces load their stylesheet successfully.

    The premise holds by construction: this test process runs no build,
    compile, bundle or subsetting step — it imports the application and
    asks the route for the asset. What the scenario then needs is that
    the thing served is a *committed* file rather than something a step
    would have had to produce, which is what the tracked-in-git check
    below establishes. The other half of the THEN — that the *pages*
    load it — is asserted in
    `test_admin_surface_navigation_and_assets.py`, over the hrefs the
    templates actually render.
    """
    if shutil.which("git") is None:
        pytest.skip(
            "git is not on PATH, so whether the asset is committed cannot be "
            "established here; re-run where git is available, or check by "
            "hand that "
            f"{(_ASSET_DIR / asset).relative_to(_REPO_ROOT)} is tracked"
        )
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(_ASSET_DIR / asset)],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    # SPECIFIED: what is served comes from the repository, not from a
    # step. An asset a build produces is not tracked.
    assert tracked.returncode == 0, (
        f"{(_ASSET_DIR / asset)} is not tracked by git, so it is not "
        "committed to the repository — whatever serves it depends on a step "
        f"someone has to remember to run ({tracked.stderr.decode()[:200]})"
    )
    # SPECIFIED: and with no such step run, the route serves it.
    signed = _client(monkeypatch, signed=True)
    response = signed.get(_url_for(asset))
    assert response.status_code == 200, (
        f"{asset} is not served in a checkout with no build step run: "
        f"{response.status_code}"
    )
    assert response.content == _committed(asset)
