"""Configures the application's logging from a single entry point.

Implements the `application-logging` capability
(`openspec/changes/configure-application-logging/specs/application-logging/spec.md`).

Attaches a formatting `StreamHandler` to the **root** logger, so records from
the application and from its dependencies are formatted alike, then sets two
levels independently: `commerce_ops` at the configured threshold, and root at
`WARNING`. Only a record's originating logger's own effective level gates
whether it is created; ancestor levels are not consulted after that -- so
this emits the application's own records at the configured threshold while
leaving an unconfigured dependency quiet below `WARNING` (design.md, "Set
root's level to WARNING and the commerce_ops logger's level to the
configured threshold").

The handler must stay a plain `StreamHandler`: it survives `dictConfig`
(e.g. uvicorn's) only because `StreamHandler.close()` is inherited as a
no-op, where a file- or queue-backed handler's real `close()` would break
silently under the same call (design.md, Context fact 3).
"""

from __future__ import annotations

import logging
import os
import sys

_HANDLER_SENTINEL_ATTR = "_commerce_ops_sentinel"

_DEFAULT_LEVEL = logging.INFO
_DEPENDENCY_LEVEL = logging.WARNING


def _resolve_threshold(app_logger: logging.Logger) -> int:
    """Reads `LOG_LEVEL`, falling back to the default on an unrecognized value.

    Absent or empty is "not configured" and produces no report. A present,
    non-empty value that names no recognized level -- including a numeric
    one, and including `NOTSET`, whose effect would silently restore the
    defect this capability fixes -- is reported through this same logger,
    never `print`, and falls back to the default rather than failing.
    """
    raw = os.environ.get("LOG_LEVEL")
    if not raw:
        return _DEFAULT_LEVEL

    candidate = raw.strip().upper()
    level = logging.getLevelNamesMapping().get(candidate)
    if level is None or level == logging.NOTSET:
        app_logger.warning("Unrecognized LOG_LEVEL %r; using INFO instead", raw)
        return _DEFAULT_LEVEL

    return level


def configure_logging() -> None:
    """Attaches a formatted handler to root and sets the two logger levels.

    Idempotent: a second call is a no-op, guarded by a sentinel attribute on
    the handler this function installs rather than by `basicConfig`'s
    implicit "root already has a handler" check.
    """
    root = logging.getLogger()
    if any(
        getattr(handler, _HANDLER_SENTINEL_ATTR, False) for handler in root.handlers
    ):
        return

    app_logger = logging.getLogger("commerce_ops")

    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _HANDLER_SENTINEL_ATTR, True)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)

    root.setLevel(_DEPENDENCY_LEVEL)
    app_logger.setLevel(_resolve_threshold(app_logger))


def _reset() -> None:
    """Detaches this module's sentinel handler only -- never touches levels.

    "Restore" has no single correct level to pick, so that is left to the
    caller (the test fixture in `test_logging.py` snapshots and restores
    `root.level` and `commerce_ops`'s level itself). Test-only seam.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_SENTINEL_ATTR, False):
            root.removeHandler(handler)
