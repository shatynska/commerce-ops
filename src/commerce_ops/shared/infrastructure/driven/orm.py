"""The one SQLAlchemy declarative base for the one database.

Every module's ORM models register on this `Base` so they share a single
`MetaData`: cross-module foreign keys (e.g. `launch_positions.product_id`
→ the catalog-owned `products.id`) can only resolve inside one metadata,
and Alembic autogenerate compares one complete picture of the schema.
This is a shared-kernel infrastructure concern, so it lives in
`shared.infrastructure` where every module's own infrastructure layer may
import it; `shared` itself still never imports a business module.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
