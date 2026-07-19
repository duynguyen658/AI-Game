from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.exceptions import DatabaseUnavailableError
from app.database.session import check_database_connection

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    try:
        await check_database_connection()
    except Exception as exc:
        raise DatabaseUnavailableError("Database is not ready") from exc

    return {
        "status": "ready",
        "database": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
    }
