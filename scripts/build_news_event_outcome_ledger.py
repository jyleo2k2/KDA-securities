"""Build a descriptive historical-news ETF outcome report from verified inputs.

The input is a reviewed event ledger.  This command never creates events from
headlines, forecasts returns, or produces allocation/rebalancing signals.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, ConfigDict, Field

from backend.app.engine.models import AccountType, SourceChip
from backend.app.engine.news_event_outcomes import (
    HistoricalNewsEvent,
    NewsEventOutcomeEvaluation,
    calculate_news_event_outcomes,
)
from backend.app.etf_universe_database import PostgresPortfolioUniverseRepository
from backend.app.portfolio_universe_repository import PortfolioUniverseRepository
from backend.app.settings import get_settings

_TOTAL_RETURN_SOURCE_URL = "https://apiportal.koreainvestment.com/"
_TOTAL_RETURN_SOURCE_LABEL = "한투 수정주가·KIND 현금분배 결합 총수익률"


class HistoricalNewsEventLedger(BaseModel):
    """Reviewed source events supplied by an operator; no implicit selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    events: tuple[HistoricalNewsEvent, ...] = Field(min_length=1)


def build_outcome_evaluation(
    *,
    events: tuple[HistoricalNewsEvent, ...],
    universe: PortfolioUniverseRepository,
) -> NewsEventOutcomeEvaluation:
    """Evaluate only the explicitly supplied event/ETF pairs against past history."""

    requested_codes = {
        code for event in events for code in event.peer_isu_codes
    }
    products_by_code = {
        str(product["isu_code"]): product
        for product in universe.products
        if isinstance(product.get("isu_code"), str)
    }
    names_by_code = {
        code: str(product.get("isu_name") or code)
        for code, product in products_by_code.items()
    }
    histories, history_sources = universe.load_total_return_histories(requested_codes)
    source_chips = {
        code: SourceChip(
            label=_TOTAL_RETURN_SOURCE_LABEL,
            reference=_TOTAL_RETURN_SOURCE_URL,
            as_of=max(history),
        )
        for code, history in histories.items()
        if history
    }
    return calculate_news_event_outcomes(
        events=list(events),
        names_by_code=names_by_code,
        histories=histories,
        history_sources=history_sources,
        source_chips=source_chips,
    )


def _database_url() -> str:
    settings = get_settings()
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is required")
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    return database_url


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build realized 1/3/6-month outcomes for reviewed news events."
    )
    parser.add_argument(
        "events", type=Path, help="reviewed historical event ledger JSON"
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    ledger = HistoricalNewsEventLedger.model_validate_json(
        args.events.read_text(encoding="utf-8")
    )
    universe = PostgresPortfolioUniverseRepository(_database_url()).latest(
        AccountType.PENSION_SAVINGS
    )
    evaluation = build_outcome_evaluation(events=ledger.events, universe=universe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(evaluation.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "event_count": len(ledger.events),
                "outcome_count": len(evaluation.outcomes),
                "output": args.output.as_posix(),
                "verified_horizon_rows": sum(
                    len(outcome.horizons) for outcome in evaluation.outcomes
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
