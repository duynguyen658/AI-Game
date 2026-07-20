from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI

from app.api.approvals import router as approvals_router
from app.api.agent_runs import router as agent_runs_router
from app.api.action_requests import router as action_requests_router
from app.api.agent_memory import router as agent_memory_router
from app.api.campaigns import router as campaigns_router
from app.api.exception_handlers import register_exception_handlers
from app.api.health import router as health_router
from app.api.workflows import router as workflows_router
from app.core.config import get_settings
from app.core.exceptions import DatabaseUnavailableError
from app.core.logging_config import configure_logging
from app.database.session import check_database_connection, dispose_database_engine

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "application_started",
        app_name=settings.app_name,
        environment=settings.app_env,
    )

    yield

    await dispose_database_engine()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(health_router)
app.include_router(campaigns_router)
app.include_router(workflows_router)
app.include_router(approvals_router)
app.include_router(agent_runs_router)
app.include_router(action_requests_router)
app.include_router(agent_memory_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "docs": "/docs",
    }


@app.get("/ready", tags=["Health"])
async def ready() -> dict[str, str]:
    try:
        await check_database_connection()
    except Exception as exc:
        raise DatabaseUnavailableError("Database is not ready") from exc
    return {"status": "ready", "database": "ok"}
