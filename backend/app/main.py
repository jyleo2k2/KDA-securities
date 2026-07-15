from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import disclosures, engine, retrieval, system
from .api.engine import AuditedRiskCapResponse, risk_cap, risk_cap_audited
from .api.system import health
from .settings import get_settings

__all__ = [
    "AuditedRiskCapResponse",
    "app",
    "create_app",
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
        allow_origins=[
            origin.strip()
            for origin in settings.cors_allow_origins.split(",")
            if origin.strip()
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _include_eagerly(app, system.router)
    _include_eagerly(app, engine.router)
    _include_eagerly(app, retrieval.router)
    _include_eagerly(app, disclosures.router)
    # NOTE: chatbot-mvp 브랜치 병합 시 backend/app/api/chat.py 라우터로 이식해
    # 여기서 include한다 (main.py 인라인 엔드포인트 금지).
    return app


app = create_app()
