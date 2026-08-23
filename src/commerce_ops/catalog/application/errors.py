"""Rejections the catalog use cases surface to their callers."""

from __future__ import annotations


class DuplicateSkuError(Exception):
    """A registration was rejected: the SKU already belongs to an existing
    product, and nothing was persisted."""


class ProductNotFoundError(Exception):
    """An operation targeted a product identifier that no registered
    product has."""
