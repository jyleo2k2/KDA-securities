from pydantic import BaseModel

from .market_evidence import (
    HistoricalEtfMetrics,
    KrxEtfEvidenceProduct,
    RelativeEtfRiskPercentiles,
    calculate_relative_etf_risk_percentiles,
)
from .planning_return import (
    EtfPlanningReturnEvaluation,
    EtfPlanningReturnInput,
    calculate_etf_planning_return,
)


class EtfPlanningAssessmentEvaluation(BaseModel):
    planning_return: EtfPlanningReturnEvaluation
    krx_product: KrxEtfEvidenceProduct
    relative_risk: RelativeEtfRiskPercentiles
    portfolio_candidate_status: str
    used_as_risk_evidence: list[str]
    displayed_as_historical_reference_only: list[str]
    excluded_from_planning_return: list[str]
    warnings: list[str]


def assess_etf_with_krx_evidence(
    assumption: EtfPlanningReturnInput,
    *,
    product: KrxEtfEvidenceProduct,
    universe: list[HistoricalEtfMetrics],
) -> EtfPlanningAssessmentEvaluation:
    """Join planning assumptions to KRX evidence without forward extrapolation."""

    if assumption.etf_code != product.isu_code:
        raise ValueError("planning assumption ETF code does not match KRX evidence")

    planning_return = calculate_etf_planning_return(assumption)
    relative_risk = calculate_relative_etf_risk_percentiles(
        product.historical_metrics,
        universe,
    )

    if product.blocked_name_pattern:
        candidate_status = "quarantine_required"
    elif product.eligibility_status != "verified":
        candidate_status = "account_eligibility_verification_required"
    else:
        candidate_status = "risk_review_ready"

    warnings = list(product.historical_metrics.warnings)
    warnings.extend(
        [
            "krx_trailing_returns_are_not_forward_return_inputs",
            "relative_risk_percentiles_are_not_product_rankings",
            "fees_and_account_eligibility_require_verified_external_data",
        ]
    )

    return EtfPlanningAssessmentEvaluation(
        planning_return=planning_return,
        krx_product=product,
        relative_risk=relative_risk,
        portfolio_candidate_status=candidate_status,
        used_as_risk_evidence=[
            "annualized_volatility_percent",
            "max_drawdown_percent",
            "median_daily_trading_value_krw",
            "median_net_assets_krw",
            "median_abs_premium_discount_percent",
            "tracking_error_proxy_percent",
        ],
        displayed_as_historical_reference_only=[
            "trailing_return_3m_percent",
            "trailing_return_6m_percent",
            "trailing_return_12m_percent",
        ],
        excluded_from_planning_return=[
            "trailing_return_3m_percent",
            "trailing_return_6m_percent",
            "trailing_return_12m_percent",
            "annualized_volatility_percent",
            "max_drawdown_percent",
        ],
        warnings=sorted(set(warnings)),
    )
