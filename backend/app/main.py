from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from .auth import require_supabase_user_id
from .chat import ChatRequest, ChatResponse, ChatService
from .chat.disclosures import DisclosureReadRepository
from .chat.knowledge import LocalMarkdownKnowledgeRepository
from .chat.models import ChatCapabilities, ScenarioSummary
from .chat.narrator import ClaudeNarrator
from .chat.scenarios import LocalScenarioRepository
from .engine import PortfolioInput, RiskCapEvaluation
from .engine.audit import EngineAuditRepository
from .engine.portfolio import evaluate_risk_cap
from .retrieval.repository import RetrievalRepository
from .settings import Settings, get_settings

app = FastAPI(title="Pension Copilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class AuditedRiskCapResponse(BaseModel):
    run_id: UUID
    evaluation: RiskCapEvaluation


def get_engine_audit_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EngineAuditRepository:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Engine audit database is not configured",
        )
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Engine audit database is not configured",
        )
    return EngineAuditRepository(database_url)


def get_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatService:
    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    retrieval = RetrievalRepository(database_url) if database_url else None
    disclosures = DisclosureReadRepository(database_url) if database_url else None
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        disclosures=disclosures,
        news=retrieval,
    )


def get_chat_narrator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClaudeNarrator | None:
    if settings.anthropic_api_key is None:
        return None
    api_key = settings.anthropic_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return ClaudeNarrator(api_key=api_key, model=settings.anthropic_model)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/chat/demo/capabilities", response_model=ChatCapabilities)
def chat_capabilities(
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatCapabilities:
    return service.capabilities()


@app.get("/chat/demo/scenarios", response_model=list[ScenarioSummary])
def chat_scenarios() -> list[ScenarioSummary]:
    return LocalScenarioRepository().list()


@app.post("/chat/demo", response_model=ChatResponse)
def chat_demo(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    narrator: Annotated[ClaudeNarrator | None, Depends(get_chat_narrator)],
) -> ChatResponse:
    """Unauthenticated MVP using mock accounts and read-only verified evidence."""

    response = service.ask(request)
    return narrator.narrate(response) if narrator is not None else response


@app.post("/engine/risk-cap", response_model=RiskCapEvaluation)
def risk_cap(portfolio: PortfolioInput) -> RiskCapEvaluation:
    """Unauthenticated demo calculation. It intentionally performs no DB write."""

    return evaluate_risk_cap(portfolio)


@app.post("/engine/risk-cap/audited", response_model=AuditedRiskCapResponse)
def risk_cap_audited(
    portfolio: PortfolioInput,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    recorder: Annotated[EngineAuditRepository, Depends(get_engine_audit_repository)],
) -> AuditedRiskCapResponse:
    evaluation = evaluate_risk_cap(portfolio)
    run_id = recorder.record(evaluation, owner_id=owner_id)
    return AuditedRiskCapResponse(run_id=run_id, evaluation=evaluation)
