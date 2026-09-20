from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.domain.verification import ModelCall
from app.repositories.verification import VerificationRepository


class ModelRequest(BaseModel):
    system: str = Field(max_length=4000)
    user: str = Field(max_length=12000)
    schema_version: str = "v1"


class ModelResult(BaseModel):
    provider: str
    model: str
    content: str
    latency_ms: int
    retry_count: int
    used_fallback: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ModelGateway(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResult: ...


class ProviderGateway:
    def __init__(
        self, settings: Settings, repository: VerificationRepository | None = None
    ) -> None:
        self.settings, self.repository = settings, repository

    async def complete(self, request: ModelRequest) -> ModelResult:
        try:
            result = await self._attempt(
                "openrouter",
                self.settings.openrouter_base_url,
                self.settings.openrouter_api_key,
                self.settings.openrouter_primary_model,
                request,
            )
        except (httpx.TimeoutException, httpx.TransportError, RuntimeError):
            result = await self._attempt(
                "aimlapi",
                self.settings.aimlapi_base_url,
                self.settings.aimlapi_api_key,
                self.settings.aimlapi_fallback_model,
                request,
                fallback=True,
            )
        if self.repository:
            await self.repository.create_model_call(
                ModelCall(
                    provider=result.provider,
                    model=result.model,
                    request_schema_version=request.schema_version,
                    response_schema_version="v1",
                    latency_ms=result.latency_ms,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                    retry_count=result.retry_count,
                    used_fallback=result.used_fallback,
                )
            )
        return result

    async def _attempt(
        self, provider: str, base_url, key, model: str | None, request: ModelRequest, fallback=False
    ) -> ModelResult:
        if not key or not model:
            raise RuntimeError(f"{provider} is not configured")
        started = time.monotonic()
        for retry in range(2):
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    response = await client.post(
                        f"{str(base_url).rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                        json={
                            "model": model,
                            "temperature": 0,
                            "messages": [
                                {"role": "system", "content": request.system},
                                {"role": "user", "content": request.user},
                            ],
                        },
                    )
                response.raise_for_status()
                body = response.json()
                usage = body.get("usage", {})
                return ModelResult(
                    provider=provider,
                    model=model,
                    content=body["choices"][0]["message"]["content"],
                    latency_ms=int((time.monotonic() - started) * 1000),
                    retry_count=retry,
                    used_fallback=fallback,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if retry == 1:
                    raise
                await asyncio.sleep((0.1 * (2**retry)) + random.uniform(0, 0.05))
        raise RuntimeError("unreachable")


def parse_json_object(content: str) -> dict:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    return value
