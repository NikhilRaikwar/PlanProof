from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.models import ModelRequest, ProviderGateway, parse_json_object


class FakeResponse:
    def __init__(self, status=200, content='{"ok":true}'):
        self.status_code, self._content = status, content
        self.request = httpx.Request("POST", "https://provider.test")
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "provider error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }


class FakeClient:
    responses = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, *args, **kwargs):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def settings() -> Settings:
    return Settings(
        openrouter_api_key=SecretStr("primary"),
        openrouter_primary_model="primary-model",
        aimlapi_api_key=SecretStr("fallback"),
        aimlapi_fallback_model="fallback-model",
    )


@pytest.mark.asyncio
async def test_primary_success_records_usage(monkeypatch) -> None:
    FakeClient.responses = [FakeResponse()]
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await ProviderGateway(settings()).complete(ModelRequest(system="s", user="u"))
    assert (result.provider, result.model, result.total_tokens, result.used_fallback) == (
        "openrouter",
        "primary-model",
        5,
        False,
    )


@pytest.mark.asyncio
async def test_transient_primary_retries_then_succeeds(monkeypatch) -> None:
    FakeClient.responses = [httpx.ConnectError("offline"), FakeResponse()]
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("app.services.models.asyncio.sleep", AsyncMock())
    result = await ProviderGateway(settings()).complete(ModelRequest(system="s", user="u"))
    assert result.retry_count == 1 and not result.used_fallback


@pytest.mark.asyncio
async def test_primary_exhaustion_uses_fallback(monkeypatch) -> None:
    FakeClient.responses = [
        httpx.ReadTimeout("timeout"),
        httpx.ReadTimeout("timeout"),
        FakeResponse(),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("app.services.models.asyncio.sleep", AsyncMock())
    result = await ProviderGateway(settings()).complete(ModelRequest(system="s", user="u"))
    assert result.provider == "aimlapi" and result.used_fallback


@pytest.mark.asyncio
async def test_both_providers_fail(monkeypatch) -> None:
    FakeClient.responses = [httpx.ConnectError("x") for _ in range(4)]
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr("app.services.models.asyncio.sleep", AsyncMock())
    with pytest.raises(httpx.TransportError):
        await ProviderGateway(settings()).complete(ModelRequest(system="s", user="u"))


def test_structured_response_rejects_invalid_json_and_non_object() -> None:
    with pytest.raises(ValueError):
        parse_json_object("not-json")
    with pytest.raises(ValueError):
        parse_json_object("[]")
