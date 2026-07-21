from contextlib import asynccontextmanager
import secrets
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.approvals import router as approvals_router
from app.api.alerts import router as alerts_router
from app.api.agent_runs import router as agent_runs_router
from app.api.action_requests import router as action_requests_router
from app.api.agent_memory import router as agent_memory_router
from app.api.campaigns import router as campaigns_router
from app.api.exception_handlers import register_exception_handlers
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.operations import router as operations_router
from app.api.workflows import router as workflows_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.database.session import dispose_database_engine
from app.observability.middleware import OperationalMiddleware

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
    version=settings.application_version,
    lifespan=lifespan,
)

app.add_middleware(OperationalMiddleware, settings=settings)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Correlation-ID",
        "X-Actor-ID",
        "X-Actor-Role",
    ],
)

register_exception_handlers(app)
app.include_router(health_router)
app.include_router(campaigns_router)
app.include_router(workflows_router)
app.include_router(approvals_router)
app.include_router(agent_runs_router)
app.include_router(action_requests_router)
app.include_router(agent_memory_router)
app.include_router(jobs_router)
app.include_router(alerts_router)
app.include_router(evaluations_router)
app.include_router(operations_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "docs": "/docs",
    }


@app.get("/metrics", include_in_schema=False)
async def protected_metrics(
    authorization: str | None = Header(default=None),
) -> Response:
    expected = f"Bearer {settings.metrics_token.get_secret_value()}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail="Monitoring authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
