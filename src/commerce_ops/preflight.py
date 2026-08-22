"""Checks the runtime configuration before the container serves traffic.

Implements the `deploy-pipeline` delta's "Container Checks Its Runtime
Configuration Before Migrating And Serving" requirement. Runs from the
`Dockerfile`'s `CMD` chain, ahead of `alembic upgrade head`, as
`python -m commerce_ops.preflight`.

Two things about the exit status are load-bearing, and both are easy to get
wrong by writing less code:

- Pydantic *raises* rather than returning a report, so letting
  `ValidationError` escape would exit non-zero on any fault at all --
  silently turning a capability-scoped misconfiguration into a full
  outage, which is exactly what `runtime-configuration`'s "Only A
  Startup-Critical Fault Prevents Startup" forbids. The exception is
  caught, and the exit status is decided from which variables faulted.
- The report names faulting variables and only those. Listing the whole
  declaration would satisfy the letter of "reports every faulting
  variable" while destroying the distinction a reader needs.

This lives beside `main.py`, outside the three containers `.importlinter`
layers, so importing the settings declaration here violates no contract.
"""

from __future__ import annotations

import sys
from typing import Any

from pydantic import ValidationError

from commerce_ops.shared.application.settings import (
    STARTUP_CRITICAL_ENV_VARS,
    Settings,
    get_settings,
)


def _env_var_name(field_name: str) -> str:
    """The environment variable a declared field is populated from."""
    field: Any = Settings.model_fields.get(field_name)
    if field is not None:
        alias = (
            field.validation_alias
            if field.validation_alias is not None
            else (field.alias)
        )
        if isinstance(alias, str):
            return alias.upper()
    return field_name.upper()


def _faulting_env_vars(error: ValidationError) -> list[str]:
    """Every variable named in the validation error, deduplicated and sorted.

    Built from the error's own locations rather than from the declaration,
    so a variable that validated is never named.
    """
    names = {
        _env_var_name(str(detail["loc"][0]))
        for detail in error.errors()
        if detail["loc"]
    }
    return sorted(names)


def check() -> int:
    """Returns the process exit status; writes any report to stderr."""
    try:
        get_settings()
    except ValidationError as error:
        faulting = _faulting_env_vars(error)
        print(
            f"Runtime configuration check found {len(faulting)} faulting variable(s):",
            file=sys.stderr,
        )
        for name in faulting:
            print(f"  - {name}", file=sys.stderr)

        critical = [name for name in faulting if name in STARTUP_CRITICAL_ENV_VARS]
        if critical:
            print(
                "Cannot start: "
                f"{', '.join(critical)} must be set correctly before the "
                "database migration and the HTTP server can run.",
                file=sys.stderr,
            )
            return 1

        print(
            "Starting anyway: each variable above is scoped to one "
            "capability, which will fail when it is used. The application "
            "itself can serve.",
            file=sys.stderr,
        )
        return 0

    return 0


def main() -> None:
    raise SystemExit(check())


if __name__ == "__main__":
    main()
