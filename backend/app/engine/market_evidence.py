from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import SourceChip

ENGINE_NAME = "historical_etf_evidence"
ENGINE_VERSION = "2026-07-15.1"
TRADING_DAYS_PER_YEAR = Decimal("252")
PERCENT_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.01")


class EtfObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    close: Decimal = Field(gt=0, allow_inf_nan=False)
    nav: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    trading_value_krw: Decimal = Field(ge=0, allow_inf_nan=False)
    net_assets_krw: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    benchmark_close: Decimal | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )


class HistoricalEtfMetrics(BaseModel):
    engine_name: str
    engine_version: str
    history_start: date
    history_end: date
    observation_count: int
    trailing_return_3m_percent: Decimal | None
    trailing_return_6m_percent: Decimal | None
    trailing_return_12m_percent: Decimal | None
    annualized_volatility_percent: Decimal
    max_drawdown_percent: Decimal
    median_daily_trading_value_krw: Decimal
    median_net_assets_krw: Decimal | None
    median_abs_premium_discount_percent: Decimal | None
    tracking_error_proxy_percent: Decimal | None
    source: SourceChip
    warnings: list[str]


class KrxEtfEvidenceProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isu_code: str = Field(min_length=1)
    isu_name: str = Field(min_length=1)
    benchmark_name: str
    active_on_report_date: bool
    usable_on_report_date: bool
    blocked_name_pattern: bool
    eligibility_status: str
    historical_metrics: HistoricalEtfMetrics

    @model_validator(mode="after")
    def require_current_usable_observation(self) -> "KrxEtfEvidenceProduct":
        if not self.active_on_report_date or not self.usable_on_report_date:
            raise ValueError("KRX evidence product must be current and usable")
        if self.historical_metrics.observation_count < 253:
            raise ValueError("KRX evidence product requires at least 253 observations")
        return self


class RelativeEtfRiskPercentiles(BaseModel):
    engine_name: str
    engine_version: str
    as_of: date
    universe_count: int
    comparison_counts: dict[str, int]
    volatility_risk_percentile: Decimal
    drawdown_risk_percentile: Decimal
    low_liquidity_risk_percentile: Decimal
    small_size_risk_percentile: Decimal | None
    nav_deviation_risk_percentile: Decimal | None
    tracking_error_risk_percentile: Decimal | None
    source: SourceChip
    interpretation: str


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _returns(values: list[Decimal]) -> list[Decimal]:
    return [
        values[index] / values[index - 1] - Decimal("1")
        for index in range(1, len(values))
    ]


def _sample_std(values: list[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(
        ((value - mean) ** 2 for value in values),
        Decimal("0"),
    ) / Decimal(len(values) - 1)
    return variance.sqrt()


def _relative_risk_percentile(
    values: list[Decimal],
    target: Decimal | None,
    *,
    higher_is_worse: bool,
) -> Decimal | None:
    if target is None or not values:
        return None
    riskier_or_equal = sum(
        value <= target if higher_is_worse else value >= target
        for value in values
    )
    return _percent(
        Decimal(riskier_or_equal) / Decimal(len(values)) * Decimal("100")
    )


def _trailing_return(values: list[Decimal], periods: int) -> Decimal | None:
    if len(values) <= periods:
        return None
    return _percent(
        (values[-1] / values[-periods - 1] - Decimal("1")) * Decimal("100")
    )


def _max_drawdown(values: list[Decimal]) -> Decimal:
    peak = values[0]
    maximum = Decimal("0")
    for value in values:
        peak = max(peak, value)
        drawdown = (peak - value) / peak
        maximum = max(maximum, drawdown)
    return _percent(maximum * Decimal("100"))


def calculate_historical_etf_metrics(
    observations: list[EtfObservation],
) -> HistoricalEtfMetrics:
    """Calculate historical evidence only; this is not a return forecast."""

    if len(observations) < 2:
        raise ValueError("at least two ETF observations are required")
    ordered = sorted(observations, key=lambda item: item.as_of)
    dates = [item.as_of for item in ordered]
    if len(set(dates)) != len(dates):
        raise ValueError("ETF observation dates must be unique")

    closes = [item.close for item in ordered]
    daily_returns = _returns(closes)
    annualized_volatility = (
        _sample_std(daily_returns)
        * TRADING_DAYS_PER_YEAR.sqrt()
        * Decimal("100")
    )

    trading_value_median = _median(
        [item.trading_value_krw for item in ordered]
    )
    if trading_value_median is None:
        raise RuntimeError("trading value median cannot be empty")
    net_asset_median = _median(
        [item.net_assets_krw for item in ordered if item.net_assets_krw is not None]
    )
    premium_discounts = [
        (item.close / item.nav - Decimal("1")).copy_abs() * Decimal("100")
        for item in ordered
        if item.nav is not None
    ]
    premium_discount_median = _median(premium_discounts)

    active_returns: list[Decimal] = []
    for index in range(1, len(ordered)):
        previous = ordered[index - 1]
        current = ordered[index]
        if (
            previous.nav is None
            or current.nav is None
            or previous.benchmark_close is None
            or current.benchmark_close is None
        ):
            continue
        nav_return = current.nav / previous.nav - Decimal("1")
        benchmark_return = (
            current.benchmark_close / previous.benchmark_close - Decimal("1")
        )
        active_returns.append(nav_return - benchmark_return)

    tracking_error = None
    if len(active_returns) >= 20:
        tracking_error = _percent(
            _sample_std(active_returns)
            * TRADING_DAYS_PER_YEAR.sqrt()
            * Decimal("100")
        )

    warnings: list[str] = []
    if len(ordered) < 253:
        warnings.append("insufficient_12m_history")
    if len(premium_discounts) != len(ordered):
        warnings.append("nav_missing")
    if tracking_error is None:
        warnings.append("tracking_error_proxy_insufficient")
    warnings.append("distribution_and_fee_data_not_in_krx_daily_api")
    warnings.append("account_eligibility_requires_separate_verified_master")

    return HistoricalEtfMetrics(
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        history_start=ordered[0].as_of,
        history_end=ordered[-1].as_of,
        observation_count=len(ordered),
        trailing_return_3m_percent=_trailing_return(closes, 63),
        trailing_return_6m_percent=_trailing_return(closes, 126),
        trailing_return_12m_percent=_trailing_return(closes, 252),
        annualized_volatility_percent=_percent(annualized_volatility),
        max_drawdown_percent=_max_drawdown(closes),
        median_daily_trading_value_krw=_money(trading_value_median),
        median_net_assets_krw=(
            _money(net_asset_median) if net_asset_median is not None else None
        ),
        median_abs_premium_discount_percent=(
            _percent(premium_discount_median)
            if premium_discount_median is not None
            else None
        ),
        tracking_error_proxy_percent=tracking_error,
        source=SourceChip(
            label="KRX ETF 일별매매정보",
            reference="https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd",
            as_of=ordered[-1].as_of,
        ),
        warnings=warnings,
    )


def calculate_relative_etf_risk_percentiles(
    target: HistoricalEtfMetrics,
    universe: list[HistoricalEtfMetrics],
) -> RelativeEtfRiskPercentiles:
    """Compare risk and implementation quality without creating a return rank."""

    if not universe:
        raise ValueError("KRX comparison universe must not be empty")
    if target.history_end not in {item.history_end for item in universe}:
        raise ValueError("target must belong to the KRX comparison report date")

    volatility = [item.annualized_volatility_percent for item in universe]
    drawdown = [item.max_drawdown_percent for item in universe]
    liquidity = [item.median_daily_trading_value_krw for item in universe]
    size = [
        item.median_net_assets_krw
        for item in universe
        if item.median_net_assets_krw is not None
    ]
    nav_deviation = [
        item.median_abs_premium_discount_percent
        for item in universe
        if item.median_abs_premium_discount_percent is not None
    ]
    tracking_error = [
        item.tracking_error_proxy_percent
        for item in universe
        if item.tracking_error_proxy_percent is not None
    ]

    size_percentile = _relative_risk_percentile(
        size,
        target.median_net_assets_krw,
        higher_is_worse=False,
    )
    nav_percentile = _relative_risk_percentile(
        nav_deviation,
        target.median_abs_premium_discount_percent,
        higher_is_worse=True,
    )
    tracking_percentile = _relative_risk_percentile(
        tracking_error,
        target.tracking_error_proxy_percent,
        higher_is_worse=True,
    )

    return RelativeEtfRiskPercentiles(
        engine_name="relative_etf_risk_evidence",
        engine_version="2026-07-15.1",
        as_of=target.history_end,
        universe_count=len(universe),
        comparison_counts={
            "volatility": len(volatility),
            "drawdown": len(drawdown),
            "liquidity": len(liquidity),
            "net_assets": len(size),
            "nav_deviation": len(nav_deviation),
            "tracking_error": len(tracking_error),
        },
        volatility_risk_percentile=(
            _relative_risk_percentile(
                volatility,
                target.annualized_volatility_percent,
                higher_is_worse=True,
            )
            or Decimal("0")
        ),
        drawdown_risk_percentile=(
            _relative_risk_percentile(
                drawdown,
                target.max_drawdown_percent,
                higher_is_worse=True,
            )
            or Decimal("0")
        ),
        low_liquidity_risk_percentile=(
            _relative_risk_percentile(
                liquidity,
                target.median_daily_trading_value_krw,
                higher_is_worse=False,
            )
            or Decimal("0")
        ),
        small_size_risk_percentile=size_percentile,
        nav_deviation_risk_percentile=nav_percentile,
        tracking_error_risk_percentile=tracking_percentile,
        source=target.source,
        interpretation=(
            "higher percentile means higher observed risk or weaker implementation "
            "quality versus the current listed, observation-sufficient universe"
        ),
    )
