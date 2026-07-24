"""Refresh official ETF distribution evidence without exposing raw data publicly.

This is intentionally an operator command.  It performs no collection or DB write
unless ``--apply`` is supplied, so a checkout cannot accidentally replace the
ready event master during local development.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.etf_corporate_events import build_etf_corporate_event_master
from backend.app.etf_distribution_event_repository import (
    EtfDistributionEventLoadError,
    PostgresEtfDistributionEventRepository,
    load_etf_distribution_event_master,
)
from backend.app.ingestion._files import atomic_write_json
from backend.app.ingestion.etf_distribution_refresh import (
    DistributionRefreshQuarantined,
    build_refresh_window,
    build_refreshed_event_master,
)
from backend.app.ingestion.kind_distribution_ex_dates import (
    collect_kind_distribution_ex_dates,
)
from backend.app.ingestion.kind_distributions import collect_kind_distributions
from backend.app.ingestion.kis_dividend_schedules import collect_kis_dividend_schedules
from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET,
    OfficialRawStorage,
)
from backend.app.settings import Settings


def _secret_value(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def _latest_pension_etf_universe(database_url: str) -> list[dict[str, str]]:
    """Read the same latest ready pension-eligible universe used by the engine."""

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select product.isu_code, product.payload->>'isu_name'
            from public.etf_universe_products product
            where product.version_id = (
                select id from public.etf_dataset_versions
                where status = 'ready'
                order by as_of desc, id desc limit 1
            )
              and product.account_type = 'pension_savings'
            order by product.isu_code
            """
        )
        rows = cursor.fetchall()
    products = [
        {"isu_code": str(row[0]), "isu_name": str(row[1] or "").strip()}
        for row in rows
    ]
    if not products or any(not product["isu_name"] for product in products):
        raise RuntimeError("latest ready pension ETF universe is unavailable")
    return products


def _require_complete_reports(reports: dict[str, dict[str, Any]]) -> None:
    failures = {
        source: int(report.get("failure_count", 0))
        for source, report in reports.items()
        if int(report.get("failure_count", 0))
    }
    if failures:
        raise RuntimeError(f"official collection failures: {failures}")


def _storage_object_path(*, run_id: str, source: str, path: Path) -> str:
    return (
        f"storage://{OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET}/"
        f"runs/{run_id}/{source}/{path.name}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh official KIND/KIS ETF distribution evidence incrementally."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--work-root", type=Path, default=Path("data/refresh"))
    parser.add_argument("--kis-delay-seconds", type=float, default=0.12)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.apply:
        print("dry run only; pass --apply to collect and load official evidence")
        return 0

    settings = Settings()
    database_url = _secret_value(settings.database_url)
    kis_app_key = _secret_value(settings.kis_app_key)
    kis_app_secret = _secret_value(settings.kis_app_secret)
    if not database_url or not kis_app_key or not kis_app_secret:
        print("DATABASE_URL, KIS_APP_KEY, KIS_APP_SECRET이 필요합니다", file=sys.stderr)
        return 1
    if not settings.supabase_url or not _secret_value(settings.supabase_secret_key):
        print("SUPABASE_URL, SUPABASE_SECRET_KEY가 필요합니다", file=sys.stderr)
        return 1

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    work_root = args.work_root / run_id
    reports_root = work_root / "reports"
    raw_root = work_root / "raw"
    try:
        previous = PostgresEtfDistributionEventRepository(
            database_url
        ).latest_ready_master()
        window = build_refresh_window(
            latest_ready_as_of=previous.as_of, today=args.as_of
        )
        products = _latest_pension_etf_universe(database_url)
        universe_path = work_root / "pension_eligible_etfs.json"
        atomic_write_json(universe_path, {"products": products})

        kind_report = collect_kind_distributions(
            start_date=window.kind_from,
            end_date=window.kind_to,
            raw_root=raw_root / "kind",
            output_root=reports_root,
        )
        ex_date_report = collect_kind_distribution_ex_dates(
            start_date=window.kind_from,
            end_date=window.kind_to,
            raw_root=raw_root / "kind",
            output_root=reports_root,
        )
        kis_report = collect_kis_dividend_schedules(
            app_key=kis_app_key,
            app_secret=kis_app_secret,
            universe_path=universe_path,
            start_date=window.kis_from,
            end_date=window.kis_to,
            raw_root=raw_root / "kis",
            output_root=reports_root,
            delay_seconds=args.kis_delay_seconds,
        )
        reports = {
            "kind": kind_report,
            "kind-ex-date": ex_date_report,
            "kis": kis_report,
        }
        _require_complete_reports(reports)
        report_paths = {
            source: Path(str(report["output_path"]))
            for source, report in reports.items()
        }
        source_files = {
            "kind_distributions": _storage_object_path(
                run_id=run_id, source="kind-report", path=report_paths["kind"]
            ),
            "kind_distribution_ex_dates": _storage_object_path(
                run_id=run_id,
                source="kind-ex-date-report",
                path=report_paths["kind-ex-date"],
            ),
            "kis_ksd_dividend_schedule": _storage_object_path(
                run_id=run_id, source="kis-report", path=report_paths["kis"]
            ),
        }
        empty_adjusted_root = work_root / "no-adjusted-price-refresh"
        empty_adjusted_root.mkdir(parents=True, exist_ok=True)
        refreshed = build_etf_corporate_event_master(
            distribution_report=kind_report,
            ex_date_report=ex_date_report,
            adjusted_price_root=empty_adjusted_root,
            source_files=source_files,
            as_of=args.as_of,
            kis_dividend_report=kis_report,
            eligible_isu_codes={product["isu_code"] for product in products},
        )
        merged = build_refreshed_event_master(
            previous_master={"events": previous.events},
            refreshed_master=refreshed,
            kind_from=window.kind_from,
        )
        event_path = reports_root / f"etf_corporate_events_{args.as_of}.json"
        atomic_write_json(event_path, merged)

        storage = OfficialRawStorage(
            supabase_url=settings.supabase_url,
            service_key=_secret_value(settings.supabase_secret_key),
        )
        storage.upload_run(
            run_id=run_id,
            files={
                "kind-report": report_paths["kind"],
                "kind-ex-date-report": report_paths["kind-ex-date"],
                "kis-report": report_paths["kis"],
                "event-master": event_path,
            },
            directories={"kind-raw": raw_root / "kind", "kis-raw": raw_root / "kis"},
        )
        summary = load_etf_distribution_event_master(
            database_url, event_path=event_path
        )
    except (
        DistributionRefreshQuarantined,
        EtfDistributionEventLoadError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"ETF 분배금 갱신 실패 또는 격리: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "as_of": summary.as_of.isoformat(),
                "event_rows": summary.event_rows,
                "run_id": run_id,
                "version_id": summary.version_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
