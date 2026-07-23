"""Load a normalized official ETF distribution-event master into Supabase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.etf_distribution_event_repository import (
    EtfDistributionEventLoadError,
    load_etf_distribution_event_master,
)
from backend.app.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    args = parser.parse_args()
    settings = get_settings()
    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    if not database_url:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    try:
        summary = load_etf_distribution_event_master(
            database_url, event_path=args.events
        )
    except (FileNotFoundError, EtfDistributionEventLoadError) as error:
        print(f"적재 실패: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "as_of": summary.as_of.isoformat(),
                "event_rows": summary.event_rows,
                "source_sha256": summary.source_sha256,
                "version_id": summary.version_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
