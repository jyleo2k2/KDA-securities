"""Load a verified news-event outcome engine report into the server-only ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.engine.news_event_outcomes import NewsEventOutcomeEvaluation
from backend.app.settings import get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load verified news-event outcomes.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.apply:
        print("dry run only; pass --apply to load verified news-event outcomes")
        return 0
    raw = args.report.read_bytes()
    evaluation = NewsEventOutcomeEvaluation.model_validate_json(raw)
    if (
        evaluation.is_forecast
        or evaluation.planning_return_input
        or evaluation.allocation_weight_input
        or evaluation.rebalancing_trigger_input
    ):
        raise ValueError("news-event outcome report violates descriptive-only policy")
    rows = [
        (outcome, horizon)
        for outcome in evaluation.outcomes
        for horizon in outcome.horizons
    ]
    if not rows:
        raise ValueError("news-event outcome report contains no verified outcomes")
    settings = get_settings()
    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    report_sha256 = hashlib.sha256(raw).hexdigest()
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.executemany(
            """
            insert into public.news_event_outcomes (
                event_key, occurred_on, theme_id, isu_code, isu_name,
                horizon_months, start_date, end_date, total_return_percent,
                maximum_drawdown_percent, peer_median_total_return_percent,
                peer_sample_count, event_source_url, event_source_label,
                event_source_as_of, history_source, history_source_url,
                history_source_as_of, engine_name, engine_version, policy_version,
                report_sha256
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            ) on conflict (event_key, isu_code, horizon_months) do update set
                occurred_on = excluded.occurred_on,
                theme_id = excluded.theme_id,
                isu_name = excluded.isu_name,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                total_return_percent = excluded.total_return_percent,
                maximum_drawdown_percent = excluded.maximum_drawdown_percent,
                peer_median_total_return_percent =
                    excluded.peer_median_total_return_percent,
                peer_sample_count = excluded.peer_sample_count,
                event_source_url = excluded.event_source_url,
                event_source_label = excluded.event_source_label,
                event_source_as_of = excluded.event_source_as_of,
                history_source = excluded.history_source,
                history_source_url = excluded.history_source_url,
                history_source_as_of = excluded.history_source_as_of,
                engine_name = excluded.engine_name,
                engine_version = excluded.engine_version,
                policy_version = excluded.policy_version,
                report_sha256 = excluded.report_sha256,
                loaded_at = now()
            """,
            [
                (
                    outcome.event_id,
                    outcome.occurred_on,
                    outcome.theme_id,
                    outcome.isu_code,
                    outcome.isu_name,
                    horizon.horizon_months,
                    horizon.start_date,
                    horizon.end_date,
                    horizon.total_return_percent,
                    horizon.maximum_drawdown_percent,
                    horizon.peer_median_total_return_percent,
                    horizon.peer_sample_count,
                    str(outcome.event_source.reference),
                    outcome.event_source.label,
                    outcome.event_source.as_of,
                    outcome.history_source or "verified_total_return",
                    str(outcome.history_source_chip.reference),
                    outcome.history_source_chip.as_of,
                    evaluation.engine_name,
                    evaluation.engine_version,
                    evaluation.policy_version,
                    report_sha256,
                )
                for outcome, horizon in rows
                if outcome.history_source_chip is not None
            ],
        )
    print(json.dumps({"loaded_outcome_rows": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
