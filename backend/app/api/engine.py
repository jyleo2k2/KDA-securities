"""Engine tool endpoints (아키텍처.md §3 Engine tools).

Every endpoint is an input-driven call into a pure rule-engine function.
Except for the audited risk-cap path, nothing here authenticates or writes to
the database.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_supabase_user_id
from ..chat.scenarios import LocalScenarioRepository
from ..engine import (
    AccountDiagnosticsEvaluation,
    AccountInput,
    AggregationEvaluation,
    AggregationInput,
    AllocationExampleEvaluation,
    AllocationExampleInput,
    PortfolioInput,
    ProfileEvaluation,
    ProfileSurveyInput,
    RiskCapEvaluation,
    ScenarioEvaluation,
    SimulationEvaluation,
    SimulationInput,
    aggregate_accounts,
    build_allocation_example,
    evaluate_account_diagnostics,
    evaluate_mock_scenario,
    evaluate_profile,
    evaluate_risk_cap,
    simulate_accumulation,
)
from ..engine.audit import EngineAuditRepository
from .deps import get_engine_audit_repository

router = APIRouter(tags=["engine"])


class AuditedRiskCapResponse(BaseModel):
    run_id: UUID
    evaluation: RiskCapEvaluation


@router.post("/engine/risk-cap", response_model=RiskCapEvaluation)
def risk_cap(portfolio: PortfolioInput) -> RiskCapEvaluation:
    """Unauthenticated demo calculation. It intentionally performs no DB write."""

    return evaluate_risk_cap(portfolio)


@router.post("/engine/risk-cap/audited", response_model=AuditedRiskCapResponse)
def risk_cap_audited(
    portfolio: PortfolioInput,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    recorder: Annotated[EngineAuditRepository, Depends(get_engine_audit_repository)],
) -> AuditedRiskCapResponse:
    evaluation = evaluate_risk_cap(portfolio)
    run_id = recorder.record(evaluation, owner_id=owner_id)
    return AuditedRiskCapResponse(run_id=run_id, evaluation=evaluation)


@router.post("/engine/profile", response_model=ProfileEvaluation)
def profile(survey: ProfileSurveyInput) -> ProfileEvaluation:
    """Score the risk-profile survey with the provisional rule set."""

    return evaluate_profile(survey)


@router.post("/engine/diagnostics", response_model=AccountDiagnosticsEvaluation)
def diagnostics(account: AccountInput) -> AccountDiagnosticsEvaluation:
    """Run per-account checks; risk-cap judgement is delegated internally."""

    return evaluate_account_diagnostics(account)


@router.post("/engine/aggregation", response_model=AggregationEvaluation)
def aggregation(inputs: AggregationInput) -> AggregationEvaluation:
    """Aggregate accounts for display without judging combined rules."""

    return aggregate_accounts(inputs)


@router.post("/engine/simulation", response_model=SimulationEvaluation)
def simulation(inputs: SimulationInput) -> SimulationEvaluation:
    """Project balances under approved assumption scenarios (not forecasts)."""

    return simulate_accumulation(inputs)


@router.post(
    "/engine/allocation-example", response_model=AllocationExampleEvaluation
)
def allocation_example(
    inputs: AllocationExampleInput,
) -> AllocationExampleEvaluation:
    """Return the approved asset-class example for the profile and account."""

    return build_allocation_example(inputs)


@router.get("/engine/mock-scenario/{scenario_code}", response_model=ScenarioEvaluation)
def mock_scenario(scenario_code: str) -> ScenarioEvaluation:
    """Evaluate a curated mock scenario (data/mock/chatbot_scenarios.json).

    Frontend용 시연 데이터 연결 지점. 실계좌 연동 전까지 홈 화면은 이 엔드포인트로
    목시나리오를 엔진에 태워 표시한다(실/목 경계는 응답의
    evidence/data_boundary로 표시).
    """

    scenario = LocalScenarioRepository().get(scenario_code)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown scenario_code: {scenario_code}",
        )
    return evaluate_mock_scenario(scenario)
