import json
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

from backend.app.style_planning_backtest import (
    _annualized_return,
    _forward_return,
    _total_return_series,
)


def test_total_return_series_maps_non_trading_distribution_to_next_date(
    tmp_path: Path,
) -> None:
    path = tmp_path / "069500.json"
    path.write_text(
        json.dumps(
            {
                "price_policy": {"FID_ORG_ADJ_PRC": "0"},
                "observations": [
                    {"date": "2024-01-05", "adjusted_close": "100"},
                    {"date": "2024-01-08", "adjusted_close": "100"},
                ],
            }
        ),
        encoding="utf-8",
    )

    dates, values = _total_return_series(
        path,
        {date(2024, 1, 6): Decimal("10")},
    )

    assert dates == [date(2024, 1, 5), date(2024, 1, 8)]
    assert values == [Decimal("100"), Decimal("110")]


def test_history_cutoff_is_strictly_before_formation_date() -> None:
    series = (
        [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
        [Decimal("100"), Decimal("110"), Decimal("1000")],
    )

    result = _annualized_return(
        series,
        formation_date=date(2024, 1, 3),
        periods=1,
    )

    with localcontext() as context:
        context.prec = 28
        expected = (
            (Decimal("1.1").ln() * Decimal("252")).exp() - Decimal("1")
        ) * Decimal("100")
    assert result == expected


def test_forward_window_starts_strictly_after_formation_date() -> None:
    series = (
        [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2025, 1, 2),
        ],
        [Decimal("90"), Decimal("100"), Decimal("110"), Decimal("121")],
    )

    result = _forward_return(series, date(2024, 1, 2))

    assert result == (
        date(2024, 1, 3),
        date(2025, 1, 2),
        Decimal("10.0"),
    )


def test_all_vintage_sources_are_available_by_formation_date() -> None:
    payload = json.loads(
        Path(
            "data/reference/style_planning_backtest_vintages_2022-2024.json"
        ).read_text(encoding="utf-8")
    )

    for vintage in payload["vintages"]:
        formation_date = date.fromisoformat(vintage["formation_date"])
        assert all(
            date.fromisoformat(source["as_of"]) <= formation_date
            for source in vintage["sources"]
        )

    assert [item["split"] for item in payload["vintages"]] == [
        "training",
        "training",
        "holdout",
    ]
