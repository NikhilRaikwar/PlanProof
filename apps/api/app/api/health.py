import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.dependencies import get_mongo
from app.core.errors import DependencyNotReadyError
from app.db.indexes import ensure_indexes
from app.db.mongo import MongoManager

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger("planproof.health")


class HealthResponse(BaseModel):
    status: str
    mongo: str | None = None
    redis: str | None = None


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready(
    mongo: Annotated[MongoManager, Depends(get_mongo)], request: Request
) -> HealthResponse:
    try:
        await mongo.ping()
        await ensure_indexes(mongo.database())
    except DependencyNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="required dependency is not configured",
        ) from exc
    except Exception as exc:
        # Keep the public readiness response deliberately generic while retaining
        # a non-secret diagnostic category in structured application logs.
        logger.warning("readiness_mongo_unavailable error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="required dependency is unavailable",
        ) from exc
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        logger.warning("readiness_redis_unavailable error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="required dependency is unavailable",
        ) from exc
    return HealthResponse(status="ok", mongo="ok", redis="ok")
