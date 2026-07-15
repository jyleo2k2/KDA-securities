from decimal import ROUND_HALF_UP, Decimal

from .models import (
    AccountType,
    HistoricalReturnEvaluation,
    ProfitLockEvaluation,
    ProfitLockInput,
    ReturnSubperiod,
    RiskBudgetEvaluation,
    RiskBudgetInput,
)

ENGINE_NAME = "pension_strategy_policy"
ENGINE_VERSION = "2026-07-15.1"
POLICY_REFERENCE = "docs/team/주식 전략을 활용한 연금 포트폴리오 운용안.md"
PERCENT_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.01")
DC_IRP_RISK_LIMIT_PERCENT = Decimal("70")
FULL_PERCENT = Decimal("100")


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def evaluate_historical_returns(
    subperiods: list[ReturnSubperiod], *, periods_per_year: int = 252
) -> HistoricalReturnEvaluation:
    """Calculate historical TWR, volatility, and drawdown from flow boundaries.

    Each subperiod must start after the previous external flow and end before the
    next one. Contributions and withdrawals therefore cannot create performance.
    """

    if not subperiods:
        raise ValueError("at least one return subperiod is required")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be greater than zero")

    for previous, current in zip(subperiods, subperiods[1:], strict=False):
        if current.period_start < previous.period_end:
            raise ValueError("return subperiods must be ordered and non-overlapping")

    returns = [
        period.ending_value_before_flow_krw / period.beginning_value_krw
        - Decimal("1")
        for period in subperiods
    ]

    growth = Decimal("1")
    peak = Decimal("1")
    maximum_drawdown = Decimal("0")
    for period_return in returns:
        growth *= Decimal("1") + period_return
        peak = max(peak, growth)
        drawdown = growth / peak - Decimal("1")
        maximum_drawdown = min(maximum_drawdown, drawdown)

    mean_return = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = sum(
        ((period_return - mean_return) ** 2 for period_return in returns),
        Decimal("0"),
    ) / Decimal(len(returns))
    annualized_volatility = variance.sqrt() * Decimal(periods_per_year).sqrt()

    return HistoricalReturnEvaluation(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        method="time_weighted_return",
        subperiod_returns_percent=[
            _percent(period_return * FULL_PERCENT) for period_return in returns
        ],
        cumulative_return_percent=_percent((growth - Decimal("1")) * FULL_PERCENT),
        annualized_volatility_percent=_percent(
            annualized_volatility * FULL_PERCENT
        ),
        maximum_drawdown_percent=_percent(maximum_drawdown * FULL_PERCENT),
        periods_per_year=periods_per_year,
        policy_reference=POLICY_REFERENCE,
    )


def evaluate_risk_budget(inputs: RiskBudgetInput) -> RiskBudgetEvaluation:
    """Apply the document's CPPI-like policy using explicit user assumptions."""

    safe_rate = inputs.safe_rate_assumption_percent / FULL_PERCENT
    preservation_floor = inputs.minimum_target_at_55_krw / (
        (Decimal("1") + safe_rate) ** inputs.years_to_55
    )
    cushion = max(Decimal("0"), inputs.current_value_krw - preservation_floor)
    cushion_limit = (
        inputs.risk_multiplier * cushion / inputs.current_value_krw * FULL_PERCENT
    )
    account_limit = (
        DC_IRP_RISK_LIMIT_PERCENT
        if inputs.account_type in {AccountType.DC, AccountType.IRP}
        else FULL_PERCENT
    )
    allowed = min(
        account_limit,
        inputs.suitability_limit_percent,
        cushion_limit,
    )

    return RiskBudgetEvaluation(
        preservation_floor_krw=_money(preservation_floor),
        cushion_krw=_money(cushion),
        account_limit_percent=_percent(account_limit),
        suitability_limit_percent=_percent(inputs.suitability_limit_percent),
        cushion_limit_percent=_percent(cushion_limit),
        allowed_risky_percent=_percent(max(Decimal("0"), allowed)),
        assumption_notice=(
            "안전자산 수익률과 만 55세 목표금액을 사용자가 정한 가정으로 계산한 "
            "정책 한도이며 미래 수익 예측이나 원금보장이 아닙니다."
        ),
        policy_reference=POLICY_REFERENCE,
    )


def evaluate_profit_lock(inputs: ProfitLockInput) -> ProfitLockEvaluation:
    """Calculate one non-duplicated transfer when profit-lock rules overlap."""

    tactical_weight = inputs.tactical_value_krw / inputs.total_value_krw * FULL_PERCENT
    checkpoint_return = (
        inputs.tactical_value_krw / inputs.tactical_checkpoint_krw - Decimal("1")
    ) * FULL_PERCENT

    overweight_triggered = (
        tactical_weight - inputs.tactical_target_percent >= Decimal("5")
    )
    checkpoint_triggered = checkpoint_return >= Decimal("10")

    target_value = (
        inputs.total_value_krw * inputs.tactical_target_percent / FULL_PERCENT
    )
    overweight_transfer = (
        max(Decimal("0"), inputs.tactical_value_krw - target_value)
        if overweight_triggered
        else Decimal("0")
    )
    checkpoint_profit = max(
        Decimal("0"),
        inputs.tactical_value_krw - inputs.tactical_checkpoint_krw,
    )
    lock_rate = Decimal("0.70") if inputs.age >= 50 else Decimal("0.50")
    checkpoint_transfer = (
        checkpoint_profit * lock_rate if checkpoint_triggered else Decimal("0")
    )

    # Both triggers refer to the same tactical profit. Using the larger transfer
    # prevents the same gain from being counted and moved twice.
    transfer = min(
        inputs.tactical_value_krw,
        max(overweight_transfer, checkpoint_transfer),
    )

    return ProfitLockEvaluation(
        tactical_weight_percent=_percent(tactical_weight),
        checkpoint_return_percent=_percent(checkpoint_return),
        overweight_triggered=overweight_triggered,
        checkpoint_triggered=checkpoint_triggered,
        recommended_transfer_krw=_money(transfer),
        transfer_destination=(
            "stabilization" if inputs.age >= 50 else "core_and_stabilization"
        ),
        policy_reference=POLICY_REFERENCE,
    )
