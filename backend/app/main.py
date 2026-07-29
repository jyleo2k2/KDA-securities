import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, request_response

from .api import (
    benchmark,
    chat,
    disclosures,
    engine,
    investment_profile,
    macro,
    market,
    pension_accounts,
    rebalancing_reminders,
    retrieval,
    system,
)
from .api.deps import (
    clear_chat_dependencies,
    get_chat_narrator,
    get_chat_service,
    precompute_chat_narrations,
    warm_chat_dependencies,
)
from .api.engine import (
    etf_planning_assessment,
    etf_planning_return,
    risk_cap,
    risk_cap_audited,
)
from .api.system import health
from .database import close_pool, get_database_pool
from .llm_usage import close_llm_usage_recorders
from .settings import get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "app",
    "create_app",
    "etf_planning_assessment",
    "etf_planning_return",
    "get_chat_narrator",
    "get_chat_service",
    "health",
    "risk_cap",
    "risk_cap_audited",
]


def _include_eagerly(app: FastAPI, router: APIRouter) -> None:
    # include_router는 이 FastAPI 버전에서 지연 등록이라 app.routes에 경로가
    # 노출되지 않는다. 계약 테스트가 app.routes의 path를 검사하므로 즉시 등록한다.
    # 단독 생성된 APIRouter의 라우트는 overrides provider가 없어
    # app.dependency_overrides가 무시된다. provider를 앱으로 바꾸고,
    # 핸들러가 생성 시점에 provider를 캡처하므로 핸들러도 재빌드한다.
    for route in router.routes:
        if isinstance(route, APIRoute):
            route.dependency_overrides_provider = app
            route.app = request_response(route.get_route_handler())
    app.router.routes.extend(router.routes)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    auth_http_client = httpx.AsyncClient(
        timeout=10.0,
        limits=httpx.Limits(
            max_keepalive_connections=10,
            max_connections=20,
            keepalive_expiry=30.0,
        ),
    )
    app.state.auth_http_client = auth_http_client
    pool = None
    if settings.database_url is not None:
        database_url = settings.database_url.get_secret_value().strip()
        if database_url:
            pool = get_database_pool(
                database_url,
                max_size=settings.database_pool_max_size,
            )
            pool.open(wait=False)
    precompute_task = None
    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            await asyncio.to_thread(warm_chat_dependencies, settings)
        except Exception:
            logger.warning(
                "Chat embedding prewarm failed; full-text search remains available"
            )
        precompute_task = asyncio.create_task(
            asyncio.to_thread(precompute_chat_narrations, settings)
        )
    try:
        yield
    finally:
        if precompute_task is not None and not precompute_task.done():
            precompute_task.cancel()
            with suppress(asyncio.CancelledError):
                await precompute_task
        narrator = get_chat_narrator(settings)
        if narrator is not None:
            await asyncio.to_thread(narrator.flush_cache)
        clear_chat_dependencies()
        await asyncio.to_thread(close_llm_usage_recorders)
        close_pool(pool)
        get_database_pool.cache_clear()
        await auth_http_client.aclose()
        app.state.auth_http_client = None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pension Copilot API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    )
    _include_eagerly(app, system.router)
    _include_eagerly(app, engine.router)
    _include_eagerly(app, retrieval.router)
    _include_eagerly(app, disclosures.router)
    _include_eagerly(app, benchmark.router)
    _include_eagerly(app, pension_accounts.router)
    _include_eagerly(app, investment_profile.router)
    _include_eagerly(app, rebalancing_reminders.router)
    _include_eagerly(app, market.router)
    _include_eagerly(app, macro.router)
    _include_eagerly(app, chat.router)
    return app


app = create_app()
