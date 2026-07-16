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
    EducationalPortfolioEvaluation,
    EducationalPortfolioInput,
    EtfPlanningAssessmentEvaluation,
    EtfPlanningReturnEvaluation,
    EtfPlanningReturnInput,
    NonPensionWithdrawalEvaluation,
    NonPensionWithdrawalInput,
    PensionTaxCreditEvaluation,
    PensionTaxCreditInput,
    PortfolioInput,
    ProfileEvaluation,
    ProfileSurveyInput,
    RiskCapEvaluation,
    ScenarioEvaluation,
    SimulationEvaluation,
    SimulationInput,
    aggregate_accounts,
    assess_etf_with_krx_evidence,
    build_allocation_example,
    build_educational_portfolio,
    calculate_etf_planning_return,
    calculate_pension_tax_credit,
    estimate_non_pension_withdrawal_tax,
    evaluate_account_diagnostics,
    evaluate_mock_scenario,
    evaluate_profile,
    evaluate_risk_cap,
    simulate_accumulation,
)
from ..engine.audit import EngineAuditRepository
from ..market_evidence_repository import KrxMarketEvidenceRepository
from .deps import (
    get_engine_audit_repository,
    get_krx_market_evidence_repository,
    get_portfolio_universe_repository,
)

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


@router.post(
    "/engine/etf-planning-return",
    response_model=EtfPlanningReturnEvaluation,
)
def etf_planning_return(
    assumption: EtfPlanningReturnInput,
) -> EtfPlanningReturnEvaluation:
    return calculate_etf_planning_return(assumption)


@router.post(
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


@router.post(
    "/engine/educational-portfolio",
    response_model=EducationalPortfolioEvaluation,
)
def educational_portfolio(
    request: EducationalPortfolioInput,
) -> EducationalPortfolioEvaluation:
    try:
        repository = get_portfolio_universe_repository(request.account_type)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account-specific ETF cost-return master is unavailable",
        ) from exc
    return build_educational_portfolio(
        request,
        products=repository.products,
        histories=repository.histories,
        source_as_of=repository.as_of,
        history_sources=repository.history_sources,
    )


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


@router.post(
    "/engine/pension-tax-credit",
    response_model=PensionTaxCreditEvaluation,
)
def pension_tax_credit(
    inputs: PensionTaxCreditInput,
) -> PensionTaxCreditEvaluation:
    """Calculate a 2026 educational tax-credit estimate without a DB write."""

    return calculate_pension_tax_credit(inputs)


@router.post(
    "/engine/non-pension-withdrawal-estimate",
    response_model=NonPensionWithdrawalEvaluation,
)
def non_pension_withdrawal_estimate(
    inputs: NonPensionWithdrawalInput,
) -> NonPensionWithdrawalEvaluation:
    """Estimate only the 16.5% other-income portion of a non-pension withdrawal."""

    return estimate_non_pension_withdrawal_tax(inputs)


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
