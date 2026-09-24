from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.domain.verification import ModelCall
from app.repositories.verification import VerificationRepository


class ModelBudgetExceededError(RuntimeError):
    pass


class ProviderUnavailable(RuntimeError):
    pass


class ModelRequest(BaseModel):
    system: str = Field(max_length=8000)
    user: str = Field(max_length=32000)
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
    async def complete(
        self, request: ModelRequest, run_id: str | None = None, purpose: str | None = None
    ) -> ModelResult: ...


class ProviderGateway:
    def __init__(
        self,
        settings: Settings,
        verification: VerificationRepository | None = None,
    ) -> None:
        self.settings = settings
        self.verification = verification

    async def complete(
        self,
        request: ModelRequest,
        run_id: str | None = None,
        purpose: str | None = None,
    ) -> ModelResult:
        # Pre-call budget enforcement
        if run_id and self.verification:
            run_doc = await self.verification.database.verification_runs.find_one({"id": run_id})
            if run_doc:
                current_count = run_doc.get("model_call_count", 0)
                if current_count >= self.settings.verification_max_model_calls:
                    raise ModelBudgetExceededError(
                        f"run model call budget exceeded (max {self.settings.verification_max_model_calls})"
                    )

        try:
            result = await self._attempt(
                "openrouter",
                self.settings.openrouter_base_url,
                self.settings.openrouter_api_key,
                self.settings.openrouter_primary_model,
                request,
                run_id=run_id,
            )
        except Exception:
            if not self.settings.aimlapi_api_key:
                raise
            result = await self._attempt(
                "aimlapi",
                self.settings.aimlapi_base_url,
                self.settings.aimlapi_api_key,
                self.settings.aimlapi_fallback_model,
                request,
                run_id=run_id,
                fallback=True,
            )

        if self.verification:
            # Authoritative accounting in single location
            if run_id:
                inc_dict: dict[str, int] = {"model_call_count": 1}
                if result.prompt_tokens:
                    inc_dict["prompt_tokens"] = result.prompt_tokens
                if result.completion_tokens:
                    inc_dict["completion_tokens"] = result.completion_tokens
                await self.verification.database.verification_runs.update_one(
                    {"id": run_id}, {"$inc": inc_dict}
                )

            await self.verification.create_model_call(
                ModelCall(
                    run_id=run_id,
                    provider=result.provider,
                    model=result.model,
                    purpose=purpose or "OBLIGATION_EXTRACTION",
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

    async def complete_structured(
        self,
        prompt: str,
        schema: type[Any],
        system: str = "",
        run_id: str | None = None,
        purpose: str | None = None,
    ) -> Any:
        sys_prompt = system or "You are a helpful software verification assistant."
        if "json" not in sys_prompt.lower():
            sys_prompt = f"{sys_prompt} Output a valid JSON object."
        schema_json = json.dumps(schema.model_json_schema())
        user_prompt = f"{prompt}\n\nReturn a valid JSON object matching this schema:\n{schema_json}"
        req = ModelRequest(
            system=sys_prompt[:8000],
            user=user_prompt[:32000],
        )
        result = await self.complete(req, run_id=run_id, purpose=purpose)
        data = parse_json_object(result.content)
        return schema.model_validate(data)

    async def _authorize_provider_attempt(self, run_id: str | None) -> None:
        """Check and increment provider attempt budget before each outbound HTTP call."""
        if run_id and self.verification:
            run_doc = await self.verification.database.verification_runs.find_one({"id": run_id})
            if run_doc:
                attempts = run_doc.get("provider_attempts", 0)
                if attempts >= self.settings.planproof_max_provider_attempts_per_run:
                    raise ModelBudgetExceededError(
                        f"run provider attempts budget exceeded (max {self.settings.planproof_max_provider_attempts_per_run})"
                    )
                await self.verification.database.verification_runs.update_one(
                    {"id": run_id}, {"$inc": {"provider_attempts": 1}}
                )

    async def _attempt(
        self,
        provider: str,
        base_url: Any,
        key: Any,
        model: str | None,
        request: ModelRequest,
        run_id: str | None = None,
        fallback: bool = False,
    ) -> ModelResult:
        if not key or not model:
            raise RuntimeError(f"{provider} is not configured")
        started = time.monotonic()
        payload: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "max_tokens": self.settings.planproof_max_model_output_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        if "json" in request.system.lower() or "json" in request.user.lower():
            payload["response_format"] = {"type": "json_object"}
        for retry in range(2):
            await self._authorize_provider_attempt(run_id)
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    response = await client.post(
                        f"{str(base_url).rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                        json=payload,
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
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {408, 429, 500, 502, 503, 504}:
                    raise
                if retry == 1:
                    raise ProviderUnavailable(provider) from exc
                await asyncio.sleep((0.1 * (2**retry)) + random.uniform(0, 0.05))
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
