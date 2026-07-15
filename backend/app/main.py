from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat, disclosures, engine, retrieval, system
from .api.deps import get_chat_narrator, get_chat_service
from .api.engine import AuditedRiskCapResponse, risk_cap, risk_cap_audited
from .api.system import health
from .settings import get_settings

__all__ = [
    "AuditedRiskCapResponse",
    "app",
    "create_app",
    "get_chat_narrator",
    "get_chat_service",
    "health",
    "risk_cap",
    "risk_cap_audited",
]


def _include_eagerly(app: FastAPI, router: APIRouter) -> None:
    # include_router는 이 FastAPI 버전에서 지연 등록이라 app.routes에 경로가
    # 노출되지 않는다. 계약 테스트가 app.routes의 path를 검사하므로 즉시 등록한다.
    app.router.routes.extend(router.routes)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pension Copilot API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    _include_eagerly(app, system.router)
    _include_eagerly(app, engine.router)
    _include_eagerly(app, retrieval.router)
    _include_eagerly(app, disclosures.router)
    _include_eagerly(app, chat.router)
    return app


app = create_app()
