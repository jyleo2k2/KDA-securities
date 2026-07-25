"""Archive the compact ETF-universe operational cache in private Storage.

The full KIS adjusted-price history remains in the server-side database.  This
command preserves the latest compact inputs needed to audit an ETF-universe
refresh: account-specific cost/return reports, corporate events, and the KIS
ETF snapshot metadata.  It never writes unless ``--apply`` is supplied.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_UNIVERSE_CACHE_BUCKET,
    OfficialRawStorage,
    OfficialRawStorageError,
)
from backend.app.settings import Settings

DATASET = "etf-universe-operational-cache"
_REQUIRED_CACHE_FILES = {
    "returns": (
        "dc_etf_cost_return_*.json",
        "irp_etf_cost_return_*.json",
        "pension_savings_etf_cost_return_*.json",
        "pension_etf_cost_return_master_*.json",
    ),
    "events": ("etf_corporate_events_*.json",),
    "kis": ("etf_snapshot_*.json", "adjusted_price_master_*.json"),
}


def _secret_value(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def _latest_matching_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise ValueError(
            f"required ETF cache file is unavailable: {directory / pattern}"
        )
    return matches[-1]


def prepare_operational_cache_snapshot(
    *, cache_root: Path, snapshot_root: Path
) -> list[Path]:
    """Copy only the latest audit inputs into a portable cache snapshot."""

    selected: list[Path] = []
    for section, patterns in _REQUIRED_CACHE_FILES.items():
        source_directory = cache_root / section
        for pattern in patterns:
            source = _latest_matching_file(source_directory, pattern)
            target = snapshot_root / section / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            selected.append(target)
    return selected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive compact ETF-universe operational inputs privately."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=Path("data/cache"))
    parser.add_argument("--work-root", type=Path, default=Path("data/refresh"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.apply:
        print("dry run only; pass --apply to archive the operational ETF cache")
        return 0

    collected_at = datetime.now(UTC)
    run_id = collected_at.strftime("%Y%m%dT%H%M%SZ")
    snapshot_root = args.work_root / run_id / "cache"
    try:
        selected = prepare_operational_cache_snapshot(
            cache_root=args.cache_root,
            snapshot_root=snapshot_root,
        )
        metadata_path = snapshot_root / "snapshot_metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "dataset": DATASET,
                    "included_files": [
                        path.relative_to(snapshot_root).as_posix()
                        for path in selected
                    ],
                    "price_history_boundary": "server_database",
                    "staged_at": collected_at.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        settings = Settings()
        service_key = _secret_value(settings.supabase_secret_key)
        if not settings.supabase_url or not service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        storage = OfficialRawStorage(
            supabase_url=settings.supabase_url,
            service_key=service_key,
            bucket_name=OFFICIAL_ETF_UNIVERSE_CACHE_BUCKET,
        )
        manifest = storage.upload_run(
            run_id=run_id,
            files={},
            directories={"cache": snapshot_root},
            collected_at=collected_at,
        )
        storage.promote_current_run(dataset=DATASET, manifest=manifest)
    except (OfficialRawStorageError, OSError, ValueError) as error:
        print(f"ETF universe cache archive failed: {error}", file=sys.stderr)
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
