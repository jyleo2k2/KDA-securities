"""Remove expired official ETF distribution raw objects via the Storage API."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET,
    RAW_RETENTION_DAYS,
    OfficialRawStorage,
    OfficialRawStorageError,
)
from backend.app.settings import Settings


def _secret_value(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def _expired_object_paths(*, database_url: str, cutoff: datetime) -> list[str]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select name
            from storage.objects
            where bucket_id = %s
              and name like 'runs/%%'
              and created_at < %s
            order by name
            """,
            (OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET, cutoff),
        )
        return [str(row[0]) for row in cursor.fetchall()]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete official ETF distribution raw objects after one year."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings(_env_file=args.env_file)
    database_url = _secret_value(settings.database_url)
    service_key = _secret_value(settings.supabase_secret_key)
    if not database_url or not settings.supabase_url or not service_key:
        print(
            "DATABASE_URL, SUPABASE_URL, SUPABASE_SECRET_KEY가 필요합니다",
            file=sys.stderr,
        )
        return 1
    cutoff = datetime.combine(
        args.as_of - timedelta(days=RAW_RETENTION_DAYS), time.min, tzinfo=UTC
    )
    paths = _expired_object_paths(database_url=database_url, cutoff=cutoff)
    result = {
        "candidate_count": len(paths),
        "cutoff": cutoff.isoformat(),
        "deleted_count": 0,
    }
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    try:
        result["deleted_count"] = OfficialRawStorage(
            supabase_url=settings.supabase_url,
            service_key=service_key,
        ).delete_paths(paths)
    except (OfficialRawStorageError, OSError, ValueError) as error:
        print(f"원본 만료 삭제 실패: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
