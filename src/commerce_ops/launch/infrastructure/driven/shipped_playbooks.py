"""Driven adapter: resolves a launch's pinned playbook version.

Satisfies `launch.application`'s `Playbooks` port over the playbook this
project ships. The first concrete implementation of that port — slice 3
defined it and left every caller injecting its own, which the ClickUp
completion loop's two composition points can no longer do.

Only the shipped version resolves. A launch pinned to a version this build
does not carry is a rejection, not a silent fallback to the current one:
evaluating a launch against the wrong definition is exactly what pinning
exists to prevent.
"""

from __future__ import annotations

import functools

from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook
from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_shipped_playbook,
)


class UnknownPlaybookVersionError(LookupError):
    """A launch pinned a playbook version this build does not ship."""


@functools.lru_cache
def _shipped() -> LaunchPlaybook:
    # Cached: the loader parses and validates a YAML file, and every
    # launch in a reconciliation pass asks for the same version.
    return load_shipped_playbook()


class ShippedPlaybooks:
    """The `Playbooks` port over the shipped definition."""

    def get(self, version: str) -> LaunchPlaybook:
        playbook = _shipped()
        if playbook.version != version:
            raise UnknownPlaybookVersionError(
                f"this build ships playbook version '{playbook.version}' and "
                f"cannot resolve version '{version}'"
            )
        return playbook
