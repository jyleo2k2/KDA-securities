from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from .auth import require_supabase_user_id
from .engine import (
    EtfPlanningAssessmentEvaluation,
    EtfPlanningReturnEvaluation,
    EtfPlanningReturnInput,
    PortfolioInput,
    RiskCapEvaluation,
    assess_etf_with_krx_evidence,
    calculate_etf_planning_return,
)
from .engine.audit import EngineAuditRepository
from .engine.portfolio import evaluate_risk_cap
from .market_evidence_repository import KrxMarketEvidenceRepository
from .settings import Settings, get_settings

app = FastAPI(title="Pension Copilot API", version="0.1.0")


class AuditedRiskCapResponse(BaseModel):
    run_id: UUID
    evaluation: RiskCapEvaluation


def get_krx_market_evidence_repository() -> KrxMarketEvidenceRepository:
    try:
        return KrxMarketEvidenceRepository.from_latest_cache()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Current KRX market evidence is not available",
        ) from exc


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/engine/risk-cap", response_model=RiskCapEvaluation)
def risk_cap(portfolio: PortfolioInput) -> RiskCapEvaluation:
    """Unauthenticated demo calculation. It intentionally performs no DB write."""

    return evaluate_risk_cap(portfolio)


@app.post(
    "/engine/etf-planning-return",
    response_model=EtfPlanningReturnEvaluation,
)
def etf_planning_return(
    assumption: EtfPlanningReturnInput,
) -> EtfPlanningReturnEvaluation:
    return calculate_etf_planning_return(assumption)


@app.post(
    "/engine/etf-planning-assessment",
    response_model=EtfPlanningAssessmentEvaluation,
)
def etf_planning_assessment(
    assumption: EtfPlanningReturnInput,
    repository: Annotated[
        KrxMarketEvidenceRepository,
        Depends(get_krx_market_evidence_repository),
    ],
) -> EtfPlanningAssessmentEvaluation:
    try:
        product = repository.get(assumption.etf_code)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return assess_etf_with_krx_evidence(
        assumption,
        product=product,
        universe=repository.universe,
    )


@app.post("/engine/risk-cap/audited", response_model=AuditedRiskCapResponse)
def risk_cap_audited(
    portfolio: PortfolioInput,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    recorder: Annotated[EngineAuditRepository, Depends(get_engine_audit_repository)],
) -> AuditedRiskCapResponse:
    evaluation = evaluate_risk_cap(portfolio)
    run_id = recorder.record(evaluation, owner_id=owner_id)
    return AuditedRiskCapResponse(run_id=run_id, evaluation=evaluation)
