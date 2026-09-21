from __future__ import annotations

import hashlib

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import DependencyNotReadyError


class RedisManager:
    """Owns the API process Redis client used only for readiness checks."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Redis | None = None

    async def connect(self) -> None:
        if not self._settings.redis_is_configured or self._client is not None:
            return
        self._client = Redis.from_url(
            self._settings.redis_url.get_secret_value(),
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )

    async def ping(self) -> None:
        if not self._settings.redis_is_configured:
            raise DependencyNotReadyError("REDIS_URL is not configured")
        await self.connect()
        if self._client is None or not await self._client.ping():
            raise DependencyNotReadyError("Redis is unavailable")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def consume_rate_limit(self, subject: str, limit: int, window_seconds: int) -> bool:
        """A fixed-window limiter that stores only a hash of the request subject."""
        if not self._settings.redis_is_configured:
            return True
        await self.connect()
        if self._client is None:
            return False
        digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        key = f"planproof:rate-limit:{digest}"
        count = await self._client.incr(key)
        if count == 1:
            await self._client.expire(key, window_seconds)
        return int(count) <= limit
