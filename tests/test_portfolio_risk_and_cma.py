from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.engine.educational_portfolio import (
    CMA_ASSUMPTIONS_PERCENT,
    CMA_HORIZON_MAX_YEARS,
    CMA_HORIZON_MIN_YEARS,
    CurrentHolding,
    StressLossPolicyStatus,
    _cma_mapping,
    calculate_current_holdings_planning_return,
    calculate_portfolio_planning_return,
    calculate_portfolio_risk,
)


@dataclass
class Candidate:
    isu_code: str
    isu_name: str
    sleeve: str
    target_percent: Decimal


def _history(seed: Decimal) -> dict[date, Decimal]:
    start = date(2025, 1, 1)
    value = Decimal("100")
    history = {start: value}
    for index in range(1, 91):
        daily = Decimal("0.001") * seed
        if index % 7 == 0:
            daily = Decimal("-0.004") * seed
        value *= Decimal("1") + daily
        history[start + timedelta(days=index)] = value
    return history


def test_cma_registry_is_versioned_and_not_a_forecast() -> None:
    assert CMA_ASSUMPTIONS_PERCENT["cash"] == Decimal("3.1")
    assert CMA_ASSUMPTIONS_PERCENT["global_equity"] == Decimal("7.0")
    assert (CMA_HORIZON_MIN_YEARS, CMA_HORIZON_MAX_YEARS) == (10, 15)


def test_cma_mapping_marks_korean_equity_as_global_proxy() -> None:
    assumption_code, proxy_used, warnings = _cma_mapping(
        {
            "asset_class": "equity",
            "strategy": "broad_market",
            "region": "south_korea",
            "currency_hedge": "not_applicable",
        }
    )

    assert assumption_code == "global_equity"
    assert proxy_used is True
    assert "asset_class_or_region_uses_cma_proxy" in warnings


def test_portfolio_risk_uses_history_only_for_risk_metrics() -> None:
    candidates = [
        Candidate("EQ", "Equity", "core_equity", Decimal("60")),
        Candidate("FI", "Bond", "fixed_income", Decimal("40")),
    ]
    result = calculate_portfolio_risk(
        candidates=candidates,
        histories={"EQ": _history(Decimal("2")), "FI": _history(Decimal("0.5"))},
        source_as_of=date(2026, 7, 16),
    )

    assert result.status == "complete"
    assert result.observation_count == 90
    assert result.maximum_drawdown_percent is not None
    assert result.maximum_drawdown_percent > 0
    assert result.historical_return_used_for_risk_only is True
    assert result.is_return_forecast is False
    assert result.stress_loss_limit_percent is None
    assert result.stress_loss_policy_status == StressLossPolicyStatus.NOT_EVALUATED


def test_portfolio_risk_marks_stress_loss_above_user_limit_for_review() -> None:
    candidate = Candidate("EQ", "Equity", "core_equity", Decimal("100"))

    result = calculate_portfolio_risk(
        candidates=[candidate],
        histories={"EQ": _history(Decimal("1"))},
        source_as_of=date(2026, 7, 16),
        loss_tolerance_percent=Decimal("20"),
    )

    assert result.worst_stress_loss_percent == Decimal("35.0000")
    assert result.stress_loss_limit_percent == Decimal("20")
    assert result.stress_loss_policy_status == StressLossPolicyStatus.REVIEW_REQUIRED
    assert "stress_loss_exceeds_user_tolerance_review_required" in result.warnings


def test_portfolio_planning_return_uses_cma_minus_verified_cost() -> None:
    candidates = [
        Candidate("EQ", "Equity", "core_equity", Decimal("60")),
        Candidate("CASH", "Cash", "cash", Decimal("40")),
    ]
    products = {
        "EQ": {
            "classification": {
                "asset_class": "equity",
                "strategy": "broad_market",
                "region": "united_states",
                "classification_confidence": "high",
                "currency_hedge": "hedged",
            },
            "cost": {
                "asset_manager": "주식자산운용",
                "effective_total_cost_percent": "0.20",
                "effective_total_cost_status": "kofia_reported_ter",
                "effective_total_cost_as_of": "2026-07-22",
                "kofia_reported_stated_fee_total_percent": "0.15",
                "kofia_reported_other_cost_percent": "0.05",
                "kofia_reported_brokerage_commission_percent": "0.03",
                "tracking_cost_percent": None,
                "tracking_cost_status": "not_quantified_overlap_not_verified",
            },
            "implementation_metrics": {
                "tracking_error_diagnostic_percent": "0.42",
                "tracking_error_diagnostic_source": "kis_current_tracking_error",
            },
        },
        "CASH": {
            "classification": {
                "asset_class": "cash_equivalent",
                "strategy": "money_market",
                "region": "south_korea",
                "classification_confidence": "high",
                "currency_hedge": "not_applicable",
            },
            "cost": {
                "asset_manager": "현금자산운용",
                "effective_total_cost_percent": "0.10",
                "effective_total_cost_status": "kofia_reported_ter",
                "effective_total_cost_as_of": "2026-07-22",
            },
        },
    }
    result = calculate_portfolio_planning_return(
        candidates=candidates,
        products=products,
        retirement_start_age=60,
        portfolio_horizon_years=35,
        source_as_of=date(2026, 7, 16),
    )

    assert result.gross_planning_return_percent == Decimal("5.2600")
    assert result.net_planning_return_percent == Decimal("5.1000")
    assert result.weighted_annual_cost_drag_percent == Decimal("0.1600")
    assert result.conservative_planning_return_percent == Decimal("4.9100")
    assert result.base_planning_return_percent == Decimal("5.1000")
    assert result.historical_performance_used is False
    assert result.is_forecast is False
    equity_cost = result.components[0].cost_evidence
    assert equity_cost.asset_manager == "주식자산운용"
    assert equity_cost.stated_fee_total_percent == Decimal("0.15")
    assert equity_cost.other_cost_percent == Decimal("0.05")
    assert equity_cost.effective_total_cost_percent == Decimal("0.2000")
    assert equity_cost.brokerage_commission_percent == Decimal("0.03")
    assert equity_cost.brokerage_commission_included is False
    assert equity_cost.tracking_error_diagnostic_percent == Decimal("0.42")
    assert equity_cost.tracking_error_diagnostic_source == (
        "kis_current_tracking_error"
    )
    assert equity_cost.tracking_cost_percent is None
    assert equity_cost.tracking_cost_status == (
        "not_quantified_overlap_not_verified"
    )
    assert equity_cost.tracking_cost_included is False
    assert "portfolio_horizon_outside_cma_source_horizon" in result.warnings
    assert "central_value_is_cma_minus_verified_annual_cost_only" in result.warnings


def test_portfolio_planning_return_rejects_missing_verified_cost() -> None:
    candidate = Candidate("EQ", "Equity", "core_equity", Decimal("100"))
    products = {
        "EQ": {
            "classification": {
                "asset_class": "equity",
                "strategy": "broad_market",
                "region": "united_states",
                "classification_confidence": "high",
                "currency_hedge": "not_applicable",
            },
            "cost": {},
        },
    }

    with pytest.raises(ValueError, match="verified annual cost is required"):
        calculate_portfolio_planning_return(
            candidates=[candidate],
            products=products,
            retirement_start_age=60,
            portfolio_horizon_years=10,
            source_as_of=date(2026, 7, 16),
        )


def test_holdings_planning_return_uses_actual_weights_and_verified_costs() -> None:
    products = {
        "EQ": {
            "isu_name": "Equity ETF",
            "classification": {
                "asset_class": "equity",
                "strategy": "broad_market",
                "region": "united_states",
                "currency_hedge": "hedged",
            },
            "cost": {"effective_total_cost_percent": "0.20"},
        },
        "CASH": {
            "isu_name": "Cash ETF",
            "classification": {
                "asset_class": "cash_equivalent",
                "strategy": "money_market",
                "region": "south_korea",
                "currency_hedge": "not_applicable",
            },
            "cost": {"effective_total_cost_percent": "0.10"},
        },
    }

    result = calculate_current_holdings_planning_return(
        holdings=[
            CurrentHolding(isu_code="EQ", amount_krw=Decimal("6000000")),
            CurrentHolding(isu_code="CASH", amount_krw=Decimal("4000000")),
        ],
        products=products,
        retirement_start_age=60,
        portfolio_horizon_years=35,
        source_as_of=date(2026, 7, 16),
    )

    assert result.coverage_weight_percent == Decimal("100.0000")
    assert result.net_planning_return_percent == Decimal("5.1000")
    assert [item.annual_cost_drag_percent for item in result.components] == [
        Decimal("0.2000"),
        Decimal("0.1000"),
    ]


def test_current_holdings_planning_return_rejects_missing_verified_cost() -> None:
    products = {
        "EQ": {
            "isu_name": "Equity ETF",
            "classification": {
                "asset_class": "equity",
                "strategy": "broad_market",
                "region": "united_states",
            },
            "cost": {},
        },
    }

    try:
        calculate_current_holdings_planning_return(
            holdings=[CurrentHolding(isu_code="EQ", amount_krw=Decimal("1000000"))],
            products=products,
            retirement_start_age=60,
            portfolio_horizon_years=25,
            source_as_of=date(2026, 7, 16),
        )
    except ValueError as exc:
        assert str(exc) == "verified ETF cost is unavailable: EQ"
    else:
        raise AssertionError("missing verified ETF cost must reject the calculation")
