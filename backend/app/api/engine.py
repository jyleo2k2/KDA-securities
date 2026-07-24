"""Engine tool endpoints (아키텍처.md §3 Engine tools).

Every endpoint is an input-driven call into a pure rule-engine function.
Except for the audited risk-cap path, nothing here authenticates or writes to
the database.
"""

import logging
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import require_supabase_user_id
from ..chat.scenarios import LocalScenarioRepository
from ..engine import (
    AccountDiagnosticsEvaluation,
    AccountInput,
    AggregationEvaluation,
    AggregationInput,
    AllocationExampleEvaluation,
    AllocationExampleInput,
    AssumptionScenario,
    CurrentHolding,
    EducationalPortfolioEvaluation,
    EducationalPortfolioInput,
    EtfPlanningAssessmentEvaluation,
    EtfPlanningReturnEvaluation,
    EtfPlanningReturnInput,
    NonPensionWithdrawalEvaluation,
    NonPensionWithdrawalInput,
    PensionCalculatorEvaluation,
    PensionCalculatorInput,
    PensionTaxCreditEvaluation,
    PensionTaxCreditInput,
    PortfolioInput,
    PortfolioPlanningEvaluation,
    ProfileEvaluation,
    ProfileSurveyInput,
    RiskCapEvaluation,
    ScenarioEvaluation,
    StrategyPlanningReturnEvaluation,
    aggregate_accounts,
    assess_etf_with_krx_evidence,
    build_allocation_example,
    build_educational_portfolio,
    calculate_current_holdings_planning_return,
    calculate_etf_planning_return,
    calculate_pension,
    calculate_pension_tax_credit,
    calculate_strategy_planning_returns,
    estimate_non_pension_withdrawal_tax,
    evaluate_account_diagnostics,
    evaluate_mock_scenario,
    evaluate_profile,
    evaluate_risk_cap,
)
from ..engine.audit import EngineAuditRepository
from ..engine.models import PensionCalculatorCombinedInput
from ..engine.pension_calculator import calculate_combined_pension
from ..etf_universe_database import PortfolioUniverseLoadError
from ..market_evidence_repository import KrxMarketEvidenceRepository
from ..settings import Settings, get_settings
from .deps import (
    get_engine_audit_repository,
    get_krx_market_evidence_repository,
    get_portfolio_universe_repository,
)
from .errors import ApiErrorCode, api_error

router = APIRouter(tags=["engine"])
logger = logging.getLogger(__name__)
PORTFOLIO_CMA_CALCULATOR_POLICY_VERSION = "2026-07-22.1"


class AuditedRiskCapResponse(BaseModel):
    run_id: UUID
    evaluation: RiskCapEvaluation


class PensionCalculatorPortfolioCmaRequest(BaseModel):
    calculator: PensionCalculatorInput
    current_holdings: list[CurrentHolding] = Field(min_length=1, max_length=50)


class PensionCalculatorPortfolioCmaEvaluation(BaseModel):
    calculator: PensionCalculatorEvaluation
    planning_return: PortfolioPlanningEvaluation


@router.get(
    "/engine/strategy-planning-returns",
    response_model=list[StrategyPlanningReturnEvaluation],
)
def strategy_planning_returns() -> list[StrategyPlanningReturnEvaluation]:
    """Return fixed CMA reference baskets for the ten home strategy cards."""

    return calculate_strategy_planning_returns()


@router.post("/engine/risk-cap", response_model=RiskCapEvaluation)
def risk_cap(portfolio: PortfolioInput) -> RiskCapEvaluation:
    """Unauthenticated demo calculation. It intentionally performs no DB write."""

    return evaluate_risk_cap(portfolio)


@router.post(
    "/engine/risk-cap/audited",
    response_model=AuditedRiskCapResponse,
    status_code=status.HTTP_201_CREATED,
)
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
        logger.warning(
            "krx_evidence_etf_not_found etf_code=%s", assumption.etf_code
        )
        raise api_error(
            ApiErrorCode.RESOURCE_NOT_FOUND,
            "Requested ETF is not in the KRX evidence universe",
            status.HTTP_404_NOT_FOUND,
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
    settings: Annotated[Settings, Depends(get_settings)],
) -> EducationalPortfolioEvaluation:
    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    try:
        repository = get_portfolio_universe_repository(
            request.account_type,
            database_url,
        )
    except (
        FileNotFoundError,
        ValueError,
        PortfolioUniverseLoadError,
        psycopg.Error,
    ) as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Account-specific ETF universe is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return build_educational_portfolio(
        request,
        products=repository.products,
        histories=repository.histories,
        source_as_of=repository.as_of,
        history_sources=repository.history_sources,
        history_as_of=getattr(repository, "latest_history_as_of", repository.as_of),
        score_cache=getattr(repository, "score_cache", None),
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


@router.post(
    "/engine/pension-calculator",
    response_model=PensionCalculatorEvaluation,
)
def pension_calculator(
    inputs: PensionCalculatorInput,
) -> PensionCalculatorEvaluation:
    """Calculate an educational accumulation and pension payout scenario."""

    return calculate_pension(inputs)


@router.post(
    "/engine/pension-calculator/combined",
    response_model=PensionCalculatorEvaluation,
)
def pension_calculator_combined(
    inputs: PensionCalculatorCombinedInput,
) -> PensionCalculatorEvaluation:
    """Calculate owned account balances separately and combine the result."""

    return calculate_combined_pension(inputs)


@router.post(
    "/engine/pension-calculator/portfolio-cma",
    response_model=PensionCalculatorPortfolioCmaEvaluation,
)
def pension_calculator_portfolio_cma(
    request: PensionCalculatorPortfolioCmaRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PensionCalculatorPortfolioCmaEvaluation:
    """Calculate from the user's ETF weights with verified costs and CMA mappings."""

    if request.calculator.scenario != AssumptionScenario.BASE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Portfolio CMA calculator supports the base planning scenario only",
        )

    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    try:
        repository = get_portfolio_universe_repository(
            request.calculator.account_type,
            database_url,
        )
    except (
        FileNotFoundError,
        ValueError,
        PortfolioUniverseLoadError,
        psycopg.Error,
    ) as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Account-specific ETF universe is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc

    products = {product["isu_code"]: product for product in repository.products}
    try:
        planning_return = calculate_current_holdings_planning_return(
            holdings=request.current_holdings,
            products=products,
            retirement_start_age=request.calculator.contribution_end_age,
            portfolio_horizon_years=(
                request.calculator.contribution_end_age - request.calculator.current_age
            ),
            source_as_of=repository.as_of,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if planning_return.net_planning_return_percent is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Portfolio CMA planning return could not be calculated",
        )

    calculator = calculate_pension(
        request.calculator,
        annual_return_override_percent=planning_return.net_planning_return_percent,
        assumption_source=planning_return.sources[0],
        assumption_version=PORTFOLIO_CMA_CALCULATOR_POLICY_VERSION,
        assumption_notice=(
            "현재 보유 ETF 비중을 고정한 CMA 매핑·검증 비용·불확실성 할인 기반 "
            "장기 계획가정입니다. 미래 수익률 예측이 아닙니다."
        ),
        additional_warnings=(
            "portfolio_cma_current_holding_weights_held_constant",
            "portfolio_cma_selected_strategy_rate_only; "
            "other strategy rows use the standard bucket comparison",
            *planning_return.warnings,
        ),
    )
    return PensionCalculatorPortfolioCmaEvaluation(
        calculator=calculator,
        planning_return=planning_return,
    )


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
        raise api_error(
            ApiErrorCode.RESOURCE_NOT_FOUND,
            f"Unknown scenario_code: {scenario_code}",
            status.HTTP_404_NOT_FOUND,
        )
    return evaluate_mock_scenario(scenario)
