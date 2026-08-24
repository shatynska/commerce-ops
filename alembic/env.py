import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# The models modules are imported for their registrations alone: importing
# one is what adds its tables to the shared `Base` metadata autogenerate
# compares. They look unused, which is exactly the kind of import a later
# cleanup removes -- without them, autogenerate would emit a drop for every
# table it could no longer see.
from commerce_ops.access.infrastructure.driven import (
    models as _access_models,  # noqa: F401
)
from commerce_ops.catalog.infrastructure.driven import (
    models as _catalog_models,  # noqa: F401
)
from commerce_ops.launch.infrastructure.driven import (
    models as _products_models,  # noqa: F401
)
from commerce_ops.shared.infrastructure.driven.alembic_include import include_name
from commerce_ops.shared.infrastructure.driven.orm import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `DATABASE_URL` overrides `alembic.ini`'s placeholder `sqlalchemy.url` --
# this project has one Postgres database, read the same way the app and
# `tests/integration/products/` do (see tasks.md 1.2/4.1).
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # The job runner's tables live in the database and in no metadata, so
        # without this autogenerate proposes dropping them -- and the run
        # history with them. Passed at both configure calls so the offline and
        # online paths cannot diverge (tasks.md 1.6b).
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # See the offline path: the same exclusion, deliberately duplicated
        # rather than shared, because Alembic configures the two separately.
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
