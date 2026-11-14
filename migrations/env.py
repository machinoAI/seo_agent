"""Alembic migration environment.

Uses a synchronous connection (sqlite / psycopg) derived from DATABASE_URL, so it works
both from the CLI and when the app applies migrations on startup.

    alembic upgrade head
    alembic revision --autogenerate -m "describe the change"
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

from seo_agent.config import get_settings
from seo_agent.persistence.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
DATABASE_URL = settings.sync_database_url
target_metadata = Base.metadata

if settings.is_sqlite:
    Path(DATABASE_URL.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Only manage our own tables, so autogenerate never touches LangGraph's checkpoint
    tables when they share the PostgreSQL database."""
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    """Emit SQL without a live connection: `alembic upgrade head --sql`."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=settings.is_sqlite,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=settings.is_sqlite,  # SQLite needs batch mode for ALTER TABLE
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
