"""FastAPI application.

    uvicorn src.main:app --reload        # from the project root
    open http://localhost:8000/docs
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import __version__
from src.api.routes import health, runs
from src.config import get_settings
from src.observability.logging import configure_logging, get_logger
from src.persistence.database import dispose_engine, run_migrations

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    if settings.auto_migrate:
        applied = await asyncio.to_thread(run_migrations)
        if not applied:
            logger.warning("migrations_skipped", reason="alembic.ini not in working directory")
    logger.info("app_started", env=settings.app_env.value, version=__version__)
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("app_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SEO Agent",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
    )
    app.include_router(health.router)
    app.include_router(runs.router)
    return app


app = create_app()
