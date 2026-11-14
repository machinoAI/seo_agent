"""Database engine, sessions and migrations.

Default: a local SQLite file (`data/seo_agent.db`), so nothing needs to be installed or
running. Set DATABASE_URL to `postgresql+psycopg://...` for production (install the
`postgres` extra). The same SQLAlchemy models and Alembic migrations serve both.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings

_ALEMBIC_INI = Path("alembic.ini")


def _enable_sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs unless asked
    cursor.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


@lru_cache
def get_engine() -> AsyncEngine:
    """Process-wide async engine (cached). Connections open lazily."""
    settings = get_settings()
    url = settings.database_url.get_secret_value()
    if settings.is_sqlite:
        Path(url.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(url)
        event.listen(engine.sync_engine, "connect", _enable_sqlite_pragmas)
        return engine
    return create_async_engine(url, pool_size=10, max_overflow=5, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """Unit of work: commit on success, roll back on any exception."""
    async with get_session_factory()() as session, session.begin():
        yield session


async def ping() -> None:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def run_migrations() -> bool:
    """Apply Alembic migrations up to head (blocking; call via a thread from async code).

    Returns False if `alembic.ini` isn't in the working directory (run from the project
    root, or apply migrations separately with `alembic upgrade head`).
    """
    if not _ALEMBIC_INI.exists():
        return False
    from alembic import command
    from alembic.config import Config

    config = Config(str(_ALEMBIC_INI))
    config.attributes["configure_logging"] = False  # keep the app's logging setup
    command.upgrade(config, "head")
    return True
