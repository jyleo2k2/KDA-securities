from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.etf_cost_return_report import (
    _effective_cost_fields,
    _period_result,
    _validate_operational_cost_report,
)


def test_effective_cost_prefers_kofia_ter_and_keeps_manager_identity() -> None:
    result = _effective_cost_fields(
        kofia_cost={
            "asset_manager": "테스트자산운용",
            "ter_percent": "0.21",
        },
        kis_product={
            "asset_manager": "KIS 표시 운용사",
            "total_expense_ratio_percent": "0.15",
        },
        kofia_cost_as_of="2026-07-22",
        kis_cost_as_of="2026-06-30",
    )

    assert result == {
        "asset_manager": "테스트자산운용",
        "asset_manager_source": "kofia_fund_fee_cost_comparison",
        "effective_total_cost_percent": "0.21",
        "effective_total_cost_status": "kofia_reported_ter",
        "effective_total_cost_as_of": "2026-07-22",
    }


def test_effective_cost_uses_explicit_kis_fallback_when_kofia_is_missing() -> None:
    result = _effective_cost_fields(
        kofia_cost=None,
        kis_product={
            "asset_manager": "테스트자산운용",
            "total_expense_ratio_percent": "0.15",
        },
        kofia_cost_as_of="2026-07-22",
        kis_cost_as_of="2026-06-30",
    )

    assert result["effective_total_cost_percent"] == "0.15"
    assert result["effective_total_cost_status"] == (
        "kis_stated_total_expense_ratio"
    )
    assert result["effective_total_cost_as_of"] == "2026-06-30"


def test_operational_cost_report_requires_complete_verified_evidence() -> None:
    report = {
        "eligible_source_product_count": 1,
        "product_count": 1,
        "missing_history_count": 0,
        "products": [
            {
                "isu_code": "123456",
                "cost": {
                    "asset_manager": "테스트자산운용",
                    "effective_total_cost_percent": "0.21",
                    "effective_total_cost_status": "kofia_reported_ter",
                    "kofia_reported_ter_percent": "0.21",
                    "kofia_reported_stated_fee_total_percent": "0.15",
                    "kofia_reported_other_cost_percent": "0.06",
                    "kofia_ter_reconciliation_difference_percent_points": "0",
                    "kofia_reported_brokerage_commission_percent": "0.01",
                    "brokerage_commission_included_in_planning_return": False,
                    "tracking_cost_percent": None,
                    "tracking_cost_status": "not_quantified_overlap_not_verified",
                    "tracking_cost_included_in_planning_return": False,
                },
                "implementation_metrics": {
                    "tracking_error_diagnostic_percent": "0.20",
                    "tracking_error_diagnostic_source": (
                        "kis_current_tracking_error"
                    ),
                },
            }
        ],
    }

    _validate_operational_cost_report(report)


def test_operational_cost_report_rejects_incomplete_or_double_counted_costs() -> None:
    report = {
        "eligible_source_product_count": 1,
        "product_count": 1,
        "missing_history_count": 0,
        "products": [
            {
                "isu_code": "123456",
                "cost": {
                    "asset_manager": None,
                    "effective_total_cost_percent": "0.21",
                    "effective_total_cost_status": "kofia_reported_ter",
                    "kofia_reported_ter_percent": "0.21",
                    "kofia_reported_stated_fee_total_percent": "0.15",
                    "kofia_reported_other_cost_percent": "0.04",
                    "kofia_ter_reconciliation_difference_percent_points": "-0.02",
                    "kofia_reported_brokerage_commission_percent": None,
                    "brokerage_commission_included_in_planning_return": True,
                    "tracking_cost_percent": "0.10",
                    "tracking_cost_status": "included",
                    "tracking_cost_included_in_planning_return": False,
                },
                "implementation_metrics": {},
            }
        ],
    }

    with pytest.raises(ValueError, match="operational cost master validation failed"):
        _validate_operational_cost_report(report)


def _observation(day: date, close: str) -> dict[str, object]:
    value = Decimal(close)
    return {
        "date": day,
        "close": value,
        "nav": value,
        "benchmark_close": value,
    }


def test_total_return_reinvests_distribution_on_next_observation() -> None:
    start = date(2026, 1, 1)
    observations = [
        _observation(start, "100"),
        _observation(start + timedelta(days=1), "90"),
        _observation(start + timedelta(days=4), "99"),
    ]
    events = [
        {
            "record_date": start + timedelta(days=2),
            "application_date": start + timedelta(days=2),
            "amount": Decimal("10"),
            "timing_basis": "record_date_fallback",
        }
    ]

    result = _period_result(
        observations,
        events,
        periods=2,
        coverage_start=start,
        source_complete=True,
    )

    assert result["status"] == "complete"
    assert result["price_return_percent"] == "-1.0000"
    assert result["distribution_reinvested_total_return_percent"] == "9.0000"
    assert result["distribution_event_count"] == 1
    assert result["record_date_fallback_event_count"] == 1


def test_total_return_prefers_exact_ex_distribution_date() -> None:
    start = date(2026, 1, 1)
    observations = [
        _observation(start, "100"),
        _observation(start + timedelta(days=1), "90"),
        _observation(start + timedelta(days=4), "99"),
    ]
    events = [
        {
            "record_date": start + timedelta(days=2),
            "application_date": start + timedelta(days=1),
            "amount": Decimal("10"),
            "timing_basis": "exact_kind_ex_distribution_date",
        }
    ]

    result = _period_result(
        observations,
        events,
        periods=2,
        coverage_start=start,
        source_complete=True,
    )

    assert result["distribution_reinvested_total_return_percent"] == "10.0000"
    assert result["exact_ex_date_event_count"] == 1


def test_total_return_is_not_claimed_outside_kind_coverage() -> None:
    observations = [
        _observation(date(2025, 12, 31), "100"),
        _observation(date(2026, 1, 2), "110"),
    ]

    result = _period_result(
        observations,
        [],
        periods=1,
        coverage_start=date(2026, 1, 1),
        source_complete=True,
    )

    assert result["status"] == "distribution_coverage_insufficient"
    assert result["price_return_percent"] == "10.0000"
    assert result["distribution_reinvested_total_return_percent"] is None
