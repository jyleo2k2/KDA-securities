from decimal import ROUND_HALF_UP, Decimal

from .models import (
    AccountType,
    PortfolioInput,
    RiskCapEvaluation,
    RiskCapEvidence,
    RiskTreatment,
    RuleStatus,
    SourceChip,
)

ENGINE_NAME = "portfolio_risk_cap"
ENGINE_VERSION = "2026-07-14.1"
RULE_VERSION = "2026-07-13"
GENERAL_RISK_LIMIT_PERCENT = Decimal("70.00")
MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")
RULE_SOURCE = SourceChip(
    label="연금 기초 §4-2",
    reference="docs/20_리서치/연금_기초.md#4-2-세-계좌의-비세금-핵심-비교-2026-07-13-기준",
    as_of=RULE_VERSION,
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _sum_by_treatment(portfolio: PortfolioInput, treatment: RiskTreatment) -> Decimal:
    return _money(
        sum(
            (
                holding.amount_krw
                for holding in portfolio.holdings
                if holding.risk_treatment == treatment
            ),
            start=Decimal("0"),
        )
    )


def evaluate_risk_cap(portfolio: PortfolioInput) -> RiskCapEvaluation:
    """Evaluate account risk-cap rules without using an LLM or inferred eligibility."""

    capital_preservation = _sum_by_treatment(
        portfolio, RiskTreatment.CAPITAL_PRESERVATION
    )
    general_risky = _sum_by_treatment(portfolio, RiskTreatment.GENERAL_RISKY)
    statutory_exception = _sum_by_treatment(
        portfolio, RiskTreatment.STATUTORY_EXCEPTION
    )
    total = _money(capital_preservation + general_risky + statutory_exception)
    ratio = (
        _percent(general_risky / total * Decimal("100"))
        if total > 0
        else Decimal("0.00")
    )

    if portfolio.account_type in {AccountType.DC, AccountType.IRP}:
        limit_percent: Decimal | None = GENERAL_RISK_LIMIT_PERCENT
        limit_amount = total * GENERAL_RISK_LIMIT_PERCENT / Decimal("100")
        excess: Decimal | None = _money(max(general_risky - limit_amount, Decimal("0")))
        within_limit: bool | None = general_risky <= limit_amount
        status = RuleStatus.PASS if within_limit else RuleStatus.FAIL
        rule_code = "GENERAL_RISK_ASSET_CAP"
    else:
        limit_percent = None
        excess = None
        within_limit = None
        status = RuleStatus.NOT_APPLICABLE
        rule_code = "GENERAL_RISK_ASSET_CAP"

    evidence = RiskCapEvidence(
        rule_code=rule_code,
        rule_version=RULE_VERSION,
        source=RULE_SOURCE,
        numerator_general_risky_krw=general_risky,
        denominator_total_krw=total,
        statutory_exception_krw=statutory_exception,
        limit_percent=limit_percent,
    )

    return RiskCapEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        evaluated_input=portfolio,
        total_amount_krw=total,
        capital_preservation_amount_krw=capital_preservation,
        general_risky_amount_krw=general_risky,
        statutory_exception_amount_krw=statutory_exception,
        general_risky_ratio_percent=ratio,
        limit_percent=limit_percent,
        excess_general_risky_amount_krw=excess,
        within_limit=within_limit,
        status=status,
        evidence=[evidence],
    )
