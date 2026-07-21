from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app.api.dependencies import SessionDependency
from app.core.config import get_settings
from app.operations.health import readiness_report

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get("/live")
async def liveness_check() -> dict[str, str]:
    return {
        "status": "alive",
        "version": settings.application_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "version": settings.application_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
@router.get("/health/ready", include_in_schema=False)
async def readiness_check(
    session: SessionDependency, response: Response
) -> dict[str, object]:
    ready, checks = await readiness_report(session)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "version": settings.application_version,
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    }
