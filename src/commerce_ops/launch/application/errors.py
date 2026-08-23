"""Errors the launch use cases raise beyond the domain's own rejections."""

from __future__ import annotations


class LaunchNotFoundError(Exception):
    """A use case targeted a product that has no launch record."""


class GraduationStampError(Exception):
    """The launch graduated but the catalog rejected the steady-state
    stamp. The advance stands; the message names the manual catalog
    correction required."""
