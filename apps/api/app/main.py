from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import evaluations, health, projects, snapshots, verification, workflow
from app.core.config import Settings, get_settings
from app.db.mongo import MongoManager
from app.db.redis import RedisManager
from app.observability import configure_observability

logger = logging.getLogger("planproof")


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    mongo = MongoManager(runtime_settings)
    redis = RedisManager(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            # Connection creation is lazy; this does not make /health/live depend on Atlas.
            await mongo.connect()
            yield
        finally:
            await redis.close()
            await mongo.close()

    app = FastAPI(
        title="PlanProof API",
        version="0.1.0",
        description="Authoritative API for verification runs and evidence.",
        lifespan=lifespan,
    )
    app.state.mongo = mongo
    app.state.redis = redis
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.web_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def production_boundaries(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                oversized = int(content_length) > runtime_settings.max_request_bytes
            except ValueError:
                return JSONResponse({"detail": "invalid content length"}, status_code=400)
            if oversized:
                return JSONResponse({"detail": "request payload is too large"}, status_code=413)
        if request.url.path not in {"/health/live", "/health/ready"}:
            client = request.client.host if request.client else "unknown"
            try:
                allowed = await request.app.state.redis.consume_rate_limit(
                    client,
                    runtime_settings.rate_limit_requests,
                    runtime_settings.rate_limit_window_seconds,
                )
            except Exception:
                logger.warning("rate_limit_dependency_unavailable path=%s", request.url.path)
                return JSONResponse(
                    {"detail": "required dependency is unavailable"}, status_code=503
                )
            if not allowed:
                return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "api_request method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.monotonic() - started) * 1000),
            request_id,
        )
        return response

    configure_observability(runtime_settings, app)
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(snapshots.router)
    app.include_router(verification.router)
    app.include_router(workflow.router)
    app.include_router(evaluations.router)
    return app


app = create_app()
