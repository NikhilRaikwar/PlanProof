from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    evaluations,
    github,
    health,
    internal_tasks,
    projects,
    snapshots,
    verification,
    workflow,
)
from app.core.config import Settings, get_settings
from app.db.mongo import MongoManager
from app.observability import configure_observability

logger = logging.getLogger("planproof")


class InMemoryRateLimiter:
    """Lightweight in-memory sliding-window rate limiter for defensive edge protection."""

    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = {}

    def is_allowed(
        self,
        key: str,
        max_requests: int = 10,
        window_seconds: int = 60,
        limit: int | None = None,
    ) -> bool:
        effective_max = limit if limit is not None else max_requests
        now = time.monotonic()
        cutoff = now - window_seconds
        records = self._requests.setdefault(key, [])
        records[:] = [t for t in records if t > cutoff]
        if len(records) >= effective_max:
            return False
        records.append(now)
        if len(self._requests) > 10_000:
            self._requests = {k: v for k, v in self._requests.items() if v}
        return True


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    mongo = MongoManager(runtime_settings)
    rate_limiter = InMemoryRateLimiter()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        try:
            # Connection creation is lazy; this does not make /health/live depend on Atlas.
            await mongo.connect()
            yield
        finally:
            await mongo.close()

    docs_url = None if runtime_settings.planproof_env == "production" else "/docs"
    redoc_url = None if runtime_settings.planproof_env == "production" else "/redoc"
    openapi_url = None if runtime_settings.planproof_env == "production" else "/openapi.json"

    app = FastAPI(
        title="PlanProof API",
        version="0.1.0",
        description="Authoritative API for verification runs and evidence.",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.mongo = mongo
    app.state.rate_limiter = rate_limiter
    app.state.settings = runtime_settings

    @app.middleware("http")
    async def production_boundaries(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]

        # 1. Bounded Request Body Size Boundary (Works for declared Content-Length and chunked/missing)
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > runtime_settings.max_request_bytes:
                        return JSONResponse(
                            {"detail": "request payload is too large"}, status_code=413
                        )
                except ValueError:
                    return JSONResponse({"detail": "invalid content length"}, status_code=400)

            # Consume body and verify true byte length (cached in request._body for downstream handlers)
            body = await request.body()
            if len(body) > runtime_settings.max_request_bytes:
                return JSONResponse({"detail": "request payload is too large"}, status_code=413)

        # 2. CSRF defense: Reject cross-site mutating requests with untrusted Origin or missing Origin when cookie-authenticated
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            has_session_cookie = (
                "__session" in request.cookies or "planproof_session" in request.cookies or "planproof_github_state" in request.cookies
            )
            if origin:
                if origin not in runtime_settings.web_origins:
                    return JSONResponse({"detail": "cross-site mutation forbidden"}, status_code=403)
            elif has_session_cookie:
                referer = request.headers.get("referer")
                if referer:
                    from urllib.parse import urlparse

                    ref_parsed = urlparse(referer)
                    ref_origin = f"{ref_parsed.scheme}://{ref_parsed.netloc}"
                    if ref_origin not in runtime_settings.web_origins:
                        return JSONResponse({"detail": "cross-site mutation forbidden"}, status_code=403)
                else:
                    return JSONResponse(
                        {"detail": "missing origin header on authenticated mutation"},
                        status_code=403,
                    )

        # 3. Fast Edge / IP Abuse Rate Limiting (In-memory defensive limiter for read traffic)
        if request.url.path not in {"/health/live", "/health/ready"}:
            forwarded_for = request.headers.get("x-forwarded-for", "")
            client = forwarded_for.split(",", 1)[0].strip() or (
                request.client.host if request.client else "unknown"
            )
            if hasattr(request.app.state, "rate_limiter"):
                allowed = request.app.state.rate_limiter.is_allowed(
                    client,
                    runtime_settings.rate_limit_requests,
                    runtime_settings.rate_limit_window_seconds,
                )
                if not allowed:
                    return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # 4. Production Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if runtime_settings.planproof_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        if not request.url.path.startswith("/health/"):
            response.headers["Cache-Control"] = "private, no-store"

        logger.info(
            "api_request method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.monotonic() - started) * 1000),
            request_id,
        )
        return response

    # Register CORS after the boundary middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.web_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    configure_observability(runtime_settings, app)
    app.include_router(health.router)

    if runtime_settings.planproof_runtime_role == "api":
        app.include_router(github.router)
        app.include_router(projects.router)
        app.include_router(snapshots.router)
        app.include_router(verification.router)
        app.include_router(workflow.router)
        app.include_router(evaluations.router)
    elif runtime_settings.planproof_runtime_role == "worker":
        app.include_router(internal_tasks.router)
    else:
        if runtime_settings.planproof_env == "production":
            raise ValueError(
                f"invalid PLANPROOF_RUNTIME_ROLE={runtime_settings.planproof_runtime_role}; must be 'api' or 'worker'"
            )
        # Development fallback: mount all routes for testing
        app.include_router(github.router)
        app.include_router(projects.router)
        app.include_router(snapshots.router)
        app.include_router(verification.router)
        app.include_router(workflow.router)
        app.include_router(evaluations.router)
        app.include_router(internal_tasks.router)
    return app


app = create_app()
