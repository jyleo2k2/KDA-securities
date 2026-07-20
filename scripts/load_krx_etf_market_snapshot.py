"""Load one full-universe KRX ETF trading-day snapshot into Supabase.

By default the latest raw file with usable closing prices is loaded. A historical
snapshot can be selected with ``--date YYYY-MM-DD``.

    uv run python scripts/load_krx_etf_market_snapshot.py
    uv run python scripts/load_krx_etf_market_snapshot.py --date 2026-07-16
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.krx_market_repository import (
    DEFAULT_KRX_RAW_ROOT,
    KrxEtfMarketLoadError,
    latest_usable_krx_etf_raw_path,
    load_krx_etf_market_snapshot,
)
from backend.app.settings import get_settings


def _raw_path(raw_root: Path, base_date: date) -> Path:
    return (
        raw_root
        / "etf_bydd_trd"
        / f"{base_date.year:04d}"
        / f"{base_date.month:02d}"
        / f"{base_date:%Y%m%d}.json"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load a normalized all-listed KRX ETF daily market snapshot."
    )
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_KRX_RAW_ROOT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    if not database_url:
        print("DATABASE_URL이 비어 있습니다 (.env 확인)", file=sys.stderr)
        return 1

    try:
        raw_path = (
            _raw_path(args.raw_root, args.date)
            if args.date is not None
            else latest_usable_krx_etf_raw_path(args.raw_root)
        )
        if not raw_path.exists():
            raise FileNotFoundError(raw_path)
        summary = load_krx_etf_market_snapshot(
            database_url,
            raw_path=raw_path,
        )
    except (FileNotFoundError, KrxEtfMarketLoadError) as exc:
        print(f"적재 실패: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "base_date": summary.base_date.isoformat(),
                "source_rows": summary.source_rows,
                "normalized_rows": summary.normalized_rows,
                "skipped_rows": summary.skipped_rows,
                "run_id": str(summary.run_id),
                "raw_sha256": summary.raw_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
