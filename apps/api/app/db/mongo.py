from __future__ import annotations

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.errors import DependencyNotReadyError


class MongoManager:
    """Owns one process-level async Mongo client and exposes explicit readiness checks."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncMongoClient | None = None

    @property
    def is_configured(self) -> bool:
        return self._settings.mongo_is_configured

    async def connect(self) -> None:
        if not self.is_configured or self._client is not None:
            return
        self._client = AsyncMongoClient(
            self._settings.mongodb_uri.get_secret_value(),
            appname="planproof-api",
            serverSelectionTimeoutMS=self._settings.mongo_server_selection_timeout_ms,
            connectTimeoutMS=self._settings.mongo_server_selection_timeout_ms,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def database(self) -> AsyncDatabase:
        if self._client is None:
            raise DependencyNotReadyError("MongoDB is not configured or connected")
        return self._client.get_database(self._settings.mongodb_database)

    async def ping(self) -> None:
        if not self.is_configured:
            raise DependencyNotReadyError("MONGODB_URI is not configured")
        await self.connect()
        await self.database().command("ping")
