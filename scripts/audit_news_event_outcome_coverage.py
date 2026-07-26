"""Measure how much of a reviewed news-event ledger has realized ETF outcomes.

The command is read-only. It turns missing total-return boundaries into an
explicit backfill queue and never promotes a news event into an allocation or
rebalancing input.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.engine.models import AccountType
from backend.app.engine.news_event_outcomes import NewsEventOutcomeEvaluation
from backend.app.etf_universe_database import PostgresPortfolioUniverseRepository
from scripts.build_news_event_outcome_ledger import (
    HistoricalNewsEventLedger,
    _database_url,
    build_outcome_evaluation,
)


def summarize_outcome_coverage(
    evaluation: NewsEventOutcomeEvaluation,
) -> dict[str, object]:
    """Return gap reasons and realized-horizon counts for an explicit ledger."""

    available_by_horizon: Counter[int] = Counter()
    missing_by_horizon: Counter[int] = Counter()
    gap_reasons: Counter[str] = Counter()
    fully_covered_pairs = 0
    for outcome in evaluation.outcomes:
        available_by_horizon.update(
            horizon.horizon_months for horizon in outcome.horizons
        )
        missing_by_horizon.update(gap.horizon_months for gap in outcome.gaps)
        gap_reasons.update(gap.reason for gap in outcome.gaps)
        if not outcome.gaps:
            fully_covered_pairs += 1

    return {
        "available_horizon_rows": {
            str(months): available_by_horizon[months]
            for months in (1, 3, 6)
        },
        "fully_covered_event_etf_pairs": fully_covered_pairs,
        "gap_reasons": dict(sorted(gap_reasons.items())),
        "missing_horizon_rows": {
            str(months): missing_by_horizon[months]
            for months in (1, 3, 6)
        },
        "reviewed_event_count": len(
            {outcome.event_id for outcome in evaluation.outcomes}
        ),
        "reviewed_event_etf_pairs": len(evaluation.outcomes),
    }


def summarize_ledger_coverages(
    evaluations: dict[str, NewsEventOutcomeEvaluation],
) -> dict[str, object]:
    """Combine separate reviewed ledgers without blending their coverage gaps."""

    ledgers = {
        label: summarize_outcome_coverage(evaluation)
        for label, evaluation in sorted(evaluations.items())
    }
    available_by_horizon: Counter[int] = Counter()
    missing_by_horizon: Counter[int] = Counter()
    gap_reasons: Counter[str] = Counter()
    fully_covered_pairs = 0
    reviewed_event_count = 0
    reviewed_event_etf_pairs = 0
    for coverage in ledgers.values():
        available_by_horizon.update(
            {
                int(months): count
                for months, count in coverage["available_horizon_rows"].items()
            }
        )
        missing_by_horizon.update(
            {
                int(months): count
                for months, count in coverage["missing_horizon_rows"].items()
            }
        )
        gap_reasons.update(coverage["gap_reasons"])
        fully_covered_pairs += coverage["fully_covered_event_etf_pairs"]
        reviewed_event_count += coverage["reviewed_event_count"]
        reviewed_event_etf_pairs += coverage["reviewed_event_etf_pairs"]

    return {
        "ledgers": ledgers,
        "totals": {
            "available_horizon_rows": {
                str(months): available_by_horizon[months] for months in (1, 3, 6)
            },
            "fully_covered_event_etf_pairs": fully_covered_pairs,
            "gap_reasons": dict(sorted(gap_reasons.items())),
            "missing_horizon_rows": {
                str(months): missing_by_horizon[months] for months in (1, 3, 6)
            },
            "reviewed_event_count": reviewed_event_count,
            "reviewed_event_etf_pairs": reviewed_event_etf_pairs,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit realized-outcome coverage for reviewed news events."
    )
    parser.add_argument(
        "events",
        type=Path,
        nargs="+",
        help="one or more reviewed event ledger JSON files",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    universe = PostgresPortfolioUniverseRepository(_database_url()).latest(
        AccountType.PENSION_SAVINGS
    )
    evaluations: dict[str, NewsEventOutcomeEvaluation] = {}
    for events_path in args.events:
        label = events_path.stem
        if label in evaluations:
            raise ValueError(f"duplicate ledger label: {label}")
        ledger = HistoricalNewsEventLedger.model_validate_json(
            events_path.read_text(encoding="utf-8")
        )
        evaluations[label] = build_outcome_evaluation(
            events=ledger.events, universe=universe
        )
    coverage = (
        summarize_outcome_coverage(next(iter(evaluations.values())))
        if len(evaluations) == 1
        else summarize_ledger_coverages(evaluations)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(coverage, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
