from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.engine.models import AccountType, SourceChip
from backend.app.engine.news_event_outcomes import HistoricalNewsEvent
from backend.app.portfolio_universe_repository import PortfolioUniverseRepository
from scripts.audit_news_event_outcome_coverage import (
    summarize_ledger_coverages,
    summarize_outcome_coverage,
)
from scripts.build_news_event_outcome_ledger import (
    HistoricalNewsEventLedger,
    build_outcome_evaluation,
    events_through,
    load_local_cache_universe,
)

_FOMC_LEDGER_PATH = Path("data/reference/fomc_policy_event_ledger_2011_2025.json")
_BOK_LEDGER_PATH = Path(
    "data/reference/bok_base_rate_change_event_ledger_2011_2025.json"
)


def _source() -> SourceChip:
    return SourceChip(
        label="official event",
        reference="https://example.test/event",
        as_of=date(2025, 1, 1),
    )


def test_build_outcome_evaluation_uses_only_explicit_event_peers() -> None:
    universe = PortfolioUniverseRepository(
        account_type=AccountType.PENSION_SAVINGS,
        products=[
            {"isu_code": "111111", "isu_name": "검증 ETF"},
            {"isu_code": "999999", "isu_name": "제외 ETF"},
        ],
        histories={
            "111111": {
                date(2025, 1, 2): Decimal("100"),
                date(2025, 2, 3): Decimal("110"),
                date(2025, 4, 1): Decimal("120"),
                date(2025, 7, 1): Decimal("130"),
            }
        },
        history_sources={"111111": "kis_adjusted_close_plus_kind_cash_distribution"},
        as_of=date(2025, 7, 1),
        source_path=None,  # type: ignore[arg-type]
    )
    event = HistoricalNewsEvent(
        event_id="fed-2025-01-01",
        occurred_on=date(2025, 1, 1),
        theme_id="bank_finance",
        peer_isu_codes=("111111",),
        source=_source(),
    )

    evaluation = build_outcome_evaluation(events=(event,), universe=universe)

    assert [outcome.isu_code for outcome in evaluation.outcomes] == ["111111"]
    assert [horizon.horizon_months for horizon in evaluation.outcomes[0].horizons] == [
        1,
        3,
        6,
    ]
    assert evaluation.is_forecast is False


def test_outcome_coverage_makes_missing_history_boundaries_explicit() -> None:
    universe = PortfolioUniverseRepository(
        account_type=AccountType.PENSION_SAVINGS,
        products=[{"isu_code": "111111", "isu_name": "검증 ETF"}],
        histories={
            "111111": {
                date(2025, 1, 2): Decimal("100"),
                date(2025, 2, 3): Decimal("110"),
            }
        },
        history_sources={"111111": "kis_adjusted_close_plus_kind_cash_distribution"},
        as_of=date(2025, 2, 3),
        source_path=None,  # type: ignore[arg-type]
    )
    event = HistoricalNewsEvent(
        event_id="fed-2025-01-01",
        occurred_on=date(2025, 1, 1),
        theme_id="bank_finance",
        peer_isu_codes=("111111",),
        source=_source(),
    )

    coverage = summarize_outcome_coverage(
        build_outcome_evaluation(events=(event,), universe=universe)
    )

    assert coverage["available_horizon_rows"] == {"1": 1, "3": 0, "6": 0}
    assert coverage["missing_horizon_rows"] == {"1": 0, "3": 1, "6": 1}
    assert coverage["gap_reasons"] == {"outcome_exceeds_history_coverage": 2}


def test_ledger_coverage_keeps_each_source_separate_and_totals_explicit() -> None:
    universe = PortfolioUniverseRepository(
        account_type=AccountType.PENSION_SAVINGS,
        products=[{"isu_code": "111111", "isu_name": "검증 ETF"}],
        histories={
            "111111": {
                date(2025, 1, 2): Decimal("100"),
                date(2025, 2, 3): Decimal("110"),
                date(2025, 4, 1): Decimal("120"),
                date(2025, 7, 1): Decimal("130"),
            }
        },
        history_sources={"111111": "kis_adjusted_close_plus_kind_cash_distribution"},
        as_of=date(2025, 7, 1),
        source_path=None,  # type: ignore[arg-type]
    )
    complete_event = HistoricalNewsEvent(
        event_id="fed-2025-01-01",
        occurred_on=date(2025, 1, 1),
        theme_id="bank_finance",
        peer_isu_codes=("111111",),
        source=_source(),
    )
    incomplete_event = HistoricalNewsEvent(
        event_id="bok-2025-05-01",
        occurred_on=date(2025, 5, 1),
        theme_id="bank_finance",
        peer_isu_codes=("111111",),
        source=_source(),
    )

    coverage = summarize_ledger_coverages(
        {
            "fomc": build_outcome_evaluation(
                events=(complete_event,), universe=universe
            ),
            "bok": build_outcome_evaluation(
                events=(incomplete_event,), universe=universe
            ),
        }
    )

    assert coverage["ledgers"]["fomc"]["available_horizon_rows"] == {
        "1": 1,
        "3": 1,
        "6": 1,
    }
    assert coverage["ledgers"]["bok"]["missing_horizon_rows"] == {
        "1": 1,
        "3": 1,
        "6": 1,
    }
    assert coverage["totals"] == {
        "available_horizon_rows": {"1": 1, "3": 1, "6": 1},
        "fully_covered_event_etf_pairs": 1,
        "gap_reasons": {"start_observation_unavailable": 3},
        "missing_horizon_rows": {"1": 1, "3": 1, "6": 1},
        "reviewed_event_count": 2,
        "reviewed_event_etf_pairs": 2,
    }


def test_fomc_policy_ledger_uses_official_sources_and_explicit_bank_peers() -> None:
    ledger = HistoricalNewsEventLedger.model_validate_json(
        _FOMC_LEDGER_PATH.read_text(encoding="utf-8")
    )

    assert len(ledger.events) == 63
    assert len({event.event_id for event in ledger.events}) == 63
    assert ledger.events[0].occurred_on == date(2011, 8, 9)
    assert ledger.events[-1].occurred_on == date(2025, 12, 10)
    assert all(event.theme_id == "bank_finance" for event in ledger.events)
    assert all(
        event.peer_isu_codes == ("091170", "091220", "139270")
        for event in ledger.events
    )
    assert all(
        event.source.reference.startswith(
            "https://www.federalreserve.gov/monetarypolicy/"
        )
        for event in ledger.events
    )
    assert {
        event.occurred_on
        for event in ledger.events
        if date(2020, 1, 1) <= event.occurred_on <= date(2025, 12, 31)
    } == {
        date(2020, 1, 29),
        date(2020, 3, 2),
        date(2020, 3, 15),
        date(2020, 4, 29),
        date(2020, 6, 10),
        date(2020, 7, 29),
        date(2020, 9, 16),
        date(2020, 11, 5),
        date(2020, 12, 16),
        *(
            date(year, month, day)
            for year, month, day in (
                (2021, 1, 27), (2021, 3, 17), (2021, 4, 28),
                (2021, 6, 16), (2021, 7, 28), (2021, 9, 22),
                (2021, 11, 3), (2021, 12, 15),
                (2022, 1, 26), (2022, 3, 16), (2022, 5, 4),
                (2022, 6, 15), (2022, 7, 27), (2022, 9, 21),
                (2022, 11, 2), (2022, 12, 14),
                (2023, 2, 1), (2023, 3, 22), (2023, 5, 3),
                (2023, 6, 14), (2023, 7, 26), (2023, 9, 20),
                (2023, 11, 1), (2023, 12, 13),
                (2024, 1, 31), (2024, 3, 20), (2024, 5, 1),
                (2024, 6, 12), (2024, 7, 31), (2024, 9, 18),
                (2024, 11, 7), (2024, 12, 18),
                (2025, 1, 29), (2025, 3, 19), (2025, 5, 7),
                (2025, 6, 18), (2025, 7, 30), (2025, 9, 17),
                (2025, 10, 29), (2025, 12, 10),
            )
        ),
    }


def test_bok_base_rate_ledger_uses_official_sources_and_explicit_bank_peers() -> None:
    ledger = HistoricalNewsEventLedger.model_validate_json(
        _BOK_LEDGER_PATH.read_text(encoding="utf-8")
    )

    assert len(ledger.events) == 31
    assert len({event.event_id for event in ledger.events}) == 31
    assert ledger.events[0].occurred_on == date(2011, 1, 13)
    assert ledger.events[-1].occurred_on == date(2025, 5, 29)
    assert all(event.event_id.startswith("bok-base-rate-") for event in ledger.events)
    assert all(event.theme_id == "bank_finance" for event in ledger.events)
    assert all(
        event.peer_isu_codes == ("091170", "091220", "139270")
        for event in ledger.events
    )
    assert all(
        event.source.reference
        == "https://www.bok.or.kr/portal/singl/baseRate/list.do?menuNo=200656"
        for event in ledger.events
    )


def test_local_cache_universe_uses_explicit_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = object()
    captured: dict[str, object] = {}

    def fake_from_latest_cache(
        cls: type[PortfolioUniverseRepository],
        account_type: AccountType,
        **kwargs: Path,
    ) -> object:
        captured["account_type"] = account_type
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        PortfolioUniverseRepository,
        "from_latest_cache",
        classmethod(fake_from_latest_cache),
    )

    result = load_local_cache_universe(
        return_root=tmp_path / "returns",
        krx_root=tmp_path / "krx",
        adjusted_price_root=tmp_path / "adjusted-prices",
        event_root=tmp_path / "events",
    )

    assert result is expected
    assert captured == {
        "account_type": AccountType.PENSION_SAVINGS,
        "return_root": tmp_path / "returns",
        "krx_root": tmp_path / "krx",
        "adjusted_price_root": tmp_path / "adjusted-prices",
        "event_root": tmp_path / "events",
    }


def test_events_through_keeps_only_the_explicit_incremental_range() -> None:
    source = _source()
    events = (
        HistoricalNewsEvent(
            event_id="fed-2019-12-11",
            occurred_on=date(2019, 12, 11),
            theme_id="bank_finance",
            peer_isu_codes=("111111",),
            source=source,
        ),
        HistoricalNewsEvent(
            event_id="fed-2020-03-15",
            occurred_on=date(2020, 3, 15),
            theme_id="bank_finance",
            peer_isu_codes=("111111",),
            source=source,
        ),
    )

    assert [event.event_id for event in events_through(events, date(2019, 12, 31))] == [
        "fed-2019-12-11"
    ]
