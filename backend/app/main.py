from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, request_response

from .api import chat, disclosures, engine, retrieval, system
from .api.deps import (
    get_chat_narrator,
    get_chat_service,
    get_krx_market_evidence_repository,
    get_portfolio_universe_repository,
)
from .api.engine import (
    AuditedRiskCapResponse,
    educational_portfolio,
    etf_planning_assessment,
    etf_planning_return,
    risk_cap,
    risk_cap_audited,
)
from .api.system import health
from .settings import get_settings

__all__ = [
    "AuditedRiskCapResponse",
    "app",
    "create_app",
    "educational_portfolio",
    "etf_planning_assessment",
    "etf_planning_return",
    "get_chat_narrator",
    "get_chat_service",
    "get_krx_market_evidence_repository",
    "get_portfolio_universe_repository",
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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pension Copilot API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    )
    _include_eagerly(app, system.router)
    _include_eagerly(app, engine.router)
    _include_eagerly(app, retrieval.router)
    _include_eagerly(app, disclosures.router)
    _include_eagerly(app, chat.router)
    return app


app = create_app()
