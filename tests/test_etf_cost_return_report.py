from datetime import date, timedelta
from decimal import Decimal

from backend.app.etf_cost_return_report import _period_result


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
