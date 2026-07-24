from datetime import date
from decimal import Decimal

from backend.app.engine.models import AccountType, SourceChip
from backend.app.engine.news_event_outcomes import HistoricalNewsEvent
from backend.app.portfolio_universe_repository import PortfolioUniverseRepository
from scripts.build_news_event_outcome_ledger import build_outcome_evaluation


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
