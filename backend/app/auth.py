from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, Request, status

from .settings import Settings, get_settings


def get_auth_http_client(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "auth_http_client", None)


async def require_supabase_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    client: Annotated[
        httpx.AsyncClient | None, Depends(get_auth_http_client)
    ] = None,
) -> UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )
    if settings.supabase_url is None or settings.supabase_publishable_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is not configured",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=10.0) as fallback_client:
                response = await fallback_client.get(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                    headers={
                        "apikey": settings.supabase_publishable_key.get_secret_value(),
                        "Authorization": f"Bearer {token}",
                    },
                )
        else:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_publishable_key.get_secret_value(),
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth validation failed",
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase access token",
        )
    try:
        payload = response.json()
        return UUID(str(payload["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase Auth returned an invalid user payload",
        ) from exc
