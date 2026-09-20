from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, projects
from app.core.config import Settings, get_settings
from app.db.indexes import ensure_indexes
from app.db.mongo import MongoManager


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    mongo = MongoManager(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            if mongo.is_configured:
                await mongo.connect()
                await ensure_indexes(mongo.database())
            yield
        finally:
            await mongo.close()

    app = FastAPI(
        title="PlanProof API",
        version="0.1.0",
        description="Authoritative API for verification runs and evidence.",
        lifespan=lifespan,
    )
    app.state.mongo = mongo
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(runtime_settings.planproof_web_origin).rstrip("/")],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    app.include_router(health.router)
    app.include_router(projects.router)
    return app


app = create_app()
