from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.engine import EtfObservation, calculate_historical_etf_metrics


def _observation(
    offset: int,
    close: str,
    *,
    nav: str | None = None,
    benchmark: str | None = None,
    trading_value: str = "100",
) -> EtfObservation:
    return EtfObservation(
        as_of=date(2025, 1, 1) + timedelta(days=offset),
        close=Decimal(close),
        nav=Decimal(nav) if nav is not None else None,
        trading_value_krw=Decimal(trading_value),
        net_assets_krw=Decimal("1000000"),
        benchmark_close=(Decimal(benchmark) if benchmark is not None else None),
    )


def test_historical_metrics_compute_drawdown_and_medians() -> None:
    result = calculate_historical_etf_metrics(
        [
            _observation(0, "100", trading_value="100"),
            _observation(1, "120", trading_value="300"),
            _observation(2, "90", trading_value="200"),
        ]
    )

    assert result.max_drawdown_percent == Decimal("25.0000")
    assert result.median_daily_trading_value_krw == Decimal("200.00")
    assert result.annualized_volatility_percent > 0
    assert result.trailing_return_3m_percent is None
    assert "nav_missing" in result.warnings


def test_full_year_constant_series_is_deterministic_and_not_a_forecast() -> None:
    observations = [
        _observation(index, "100", nav="100", benchmark="100")
        for index in range(253)
    ]

    first = calculate_historical_etf_metrics(observations)
    second = calculate_historical_etf_metrics(observations)

    assert first == second
    assert first.trailing_return_3m_percent == Decimal("0.0000")
    assert first.trailing_return_6m_percent == Decimal("0.0000")
    assert first.trailing_return_12m_percent == Decimal("0.0000")
    assert first.annualized_volatility_percent == Decimal("0.0000")
    assert first.max_drawdown_percent == Decimal("0.0000")
    assert first.tracking_error_proxy_percent == Decimal("0.0000")
    assert "insufficient_12m_history" not in first.warnings
    assert "distribution_and_fee_data_not_in_krx_daily_api" in first.warnings


def test_duplicate_dates_and_single_observation_are_rejected() -> None:
    observation = _observation(0, "100")
    with pytest.raises(ValueError, match="at least two"):
        calculate_historical_etf_metrics([observation])
    with pytest.raises(ValueError, match="unique"):
        calculate_historical_etf_metrics([observation, observation])
