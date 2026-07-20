import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, HTTPException

import backend.app.auth as auth
import backend.app.main as main
from backend.app.settings import Settings

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        supabase_url="https://project.supabase.co",
        supabase_publishable_key="test-key",
    )


def _call(client: httpx.AsyncClient | None) -> UUID:
    return asyncio.run(
        auth.require_supabase_user_id(
            settings=_settings(),
            authorization="Bearer test-token",
            client=client,
        )
    )


def test_supabase_auth_returns_user_id_with_shared_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": str(USER_ID)})

    async def run() -> tuple[UUID, UUID]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _call_async(client), await _call_async(client)

    first, second = asyncio.run(run())

    assert (first, second) == (USER_ID, USER_ID)
    assert len(requests) == 2
    assert all(
        request.headers["authorization"] == "Bearer test-token" for request in requests
    )

async def _call_async(client: httpx.AsyncClient) -> UUID:
    return await auth.require_supabase_user_id(
        settings=_settings(),
        authorization="Bearer test-token",
        client=client,
    )


def test_supabase_auth_rejects_invalid_token() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(401))
        ) as client:
            with pytest.raises(HTTPException) as exc_info:
                await _call_async(client)
            assert exc_info.value.status_code == 401

    asyncio.run(run())


def test_supabase_auth_maps_network_error_to_service_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(HTTPException) as exc_info:
                await _call_async(client)
            assert exc_info.value.status_code == 503

    asyncio.run(run())


def test_supabase_auth_falls_back_to_request_scoped_client(monkeypatch) -> None:
    original_client = httpx.AsyncClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": str(USER_ID)})

    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    assert _call(None) == USER_ID
    assert len(requests) == 1


def test_lifespan_shares_and_closes_auth_http_client(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None))
    app = FastAPI()

    async def run() -> httpx.AsyncClient:
        async with main.lifespan(app):
            client = app.state.auth_http_client
            assert isinstance(client, httpx.AsyncClient)
            assert client is app.state.auth_http_client
            return client

    client = asyncio.run(run())

    assert client.is_closed is True
    assert app.state.auth_http_client is None
