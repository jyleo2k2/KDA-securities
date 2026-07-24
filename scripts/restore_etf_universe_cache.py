"""Restore the latest hash-verified compact ETF-universe operational cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_UNIVERSE_CACHE_BUCKET,
    OfficialRawStorage,
    OfficialRawStorageError,
)
from backend.app.settings import Settings
from scripts.archive_etf_universe_cache import DATASET


def _secret_value(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore a hash-verified ETF-universe operational cache."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--destination-root", type=Path, default=Path("data"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.apply:
        print("dry run only; pass --apply to restore the operational ETF cache")
        return 0

    try:
        settings = Settings()
        service_key = _secret_value(settings.supabase_secret_key)
        if not settings.supabase_url or not service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        storage = OfficialRawStorage(
            supabase_url=settings.supabase_url,
            service_key=service_key,
            bucket_name=OFFICIAL_ETF_UNIVERSE_CACHE_BUCKET,
        )
        manifest = storage.materialize_current_run(
            dataset=DATASET,
            destination=args.destination_root,
        )
    except (OfficialRawStorageError, OSError, ValueError) as error:
        print(f"ETF universe cache restore failed: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "artifact_count": len(manifest.artifacts),
                "bucket": OFFICIAL_ETF_UNIVERSE_CACHE_BUCKET,
                "dataset": DATASET,
                "run_id": manifest.run_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
