from datetime import date
from decimal import Decimal

from backend.app.engine.models import SourceChip
from backend.app.engine.news_event_outcomes import (
    HistoricalNewsEvent,
    calculate_news_event_outcomes,
)


def _source(label: str, as_of: date) -> SourceChip:
    return SourceChip(
        label=label,
        reference="https://example.test/official",
        as_of=as_of,
    )


def _history(values: list[str]) -> dict[date, Decimal]:
    dates = [
        date(2024, 1, 2),
        date(2024, 2, 1),
        date(2024, 3, 1),
        date(2024, 4, 1),
        date(2024, 5, 1),
        date(2024, 6, 3),
        date(2024, 7, 1),
    ]
    return {
        observed_on: Decimal(value)
        for observed_on, value in zip(dates, values, strict=True)
    }


def test_news_event_outcomes_are_descriptive_and_compare_peer_median() -> None:
    event = HistoricalNewsEvent(
        event_id="news:official-2024-01-01",
        occurred_on=date(2024, 1, 1),
        theme_id="semiconductors",
        peer_isu_codes=("111111", "222222"),
        source=_source("official event", date(2024, 1, 2)),
    )
    result = calculate_news_event_outcomes(
        events=[event],
        names_by_code={"111111": "ETF A", "222222": "ETF B"},
        histories={
            "111111": _history(["100", "110", "90", "120", "130", "140", "150"]),
            "222222": _history(["100", "100", "100", "100", "100", "100", "100"]),
        },
        history_sources={
            "111111": "kis_adjusted_close_plus_kind_cash_distribution",
            "222222": "kis_adjusted_close_plus_kind_cash_distribution",
        },
        source_chips={
            "111111": _source("verified total return", date(2024, 7, 1)),
            "222222": _source("verified total return", date(2024, 7, 1)),
        },
    )

    first = result.outcomes[0].horizons[0]
    assert result.is_forecast is False
    assert result.planning_return_input is False
    assert result.allocation_weight_input is False
    assert result.rebalancing_trigger_input is False
    assert first.horizon_months == 1
    assert first.total_return_percent == Decimal("10.0000")
    assert first.maximum_drawdown_percent == Decimal("0.0000")
    assert first.peer_median_total_return_percent == Decimal("5.0000")
    assert first.peer_sample_count == 2
    assert result.summaries[0].event_sample_count == 1
    assert result.summaries[0].etf_outcome_sample_count == 2


def test_news_event_outcomes_keep_unverified_or_missing_history_as_gaps() -> None:
    event = HistoricalNewsEvent(
        event_id="news:official-2024-01-01",
        occurred_on=date(2024, 1, 1),
        theme_id="semiconductors",
        peer_isu_codes=("111111", "222222"),
        source=_source("official event", date(2024, 1, 2)),
    )
    result = calculate_news_event_outcomes(
        events=[event],
        names_by_code={},
        histories={
            "111111": _history(["100", "110", "120", "130", "140", "150", "160"])
        },
        history_sources={"111111": "kis_adjusted_close"},
        source_chips={"111111": _source("price only", date(2024, 7, 1))},
    )

    assert result.outcomes[0].horizons == []
    assert [gap.reason for gap in result.outcomes[0].gaps] == [
        "verified_total_return_basis_unavailable",
        "verified_total_return_basis_unavailable",
        "verified_total_return_basis_unavailable",
    ]
    assert result.outcomes[1].horizons == []
    assert result.summaries[0].etf_outcome_sample_count == 0
