"""Stage official KOFIA/KIS ETF reference workbooks in private Storage.

The operator supplies the two official files and their individual source dates.
This command preserves the raw files, hashes, and an immutable run manifest; it
does not infer a fee or account eligibility from price data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET,
    OfficialRawStorage,
)
from backend.app.settings import Settings

DATASET = "etf-universe-reference-inputs"


def _secret_value(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def _require_workbook(path: Path, *, suffixes: set[str], label: str) -> Path:
    if not path.is_file():
        raise ValueError(f"{label} workbook does not exist: {path}")
    if path.suffix.lower() not in suffixes:
        allowed = ", ".join(sorted(suffixes))
        raise ValueError(f"{label} workbook must use one of: {allowed}")
    if not path.stat().st_size:
        raise ValueError(f"{label} workbook is empty: {path}")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Store verified KOFIA cost and KIS retirement ETF workbooks privately."
        )
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--kofia-fund-costs", type=Path, required=True)
    parser.add_argument("--kofia-as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--kofia-source-url", required=True)
    parser.add_argument("--kis-retirement-list", type=Path, required=True)
    parser.add_argument(
        "--kis-eligibility-as-of", type=date.fromisoformat, required=True
    )
    parser.add_argument("--kis-source-url", required=True)
    parser.add_argument("--work-root", type=Path, default=Path("data/refresh"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.apply:
        print("dry run only; pass --apply to store official reference inputs")
        return 0

    try:
        kofia_path = _require_workbook(
            args.kofia_fund_costs,
            suffixes={".xls", ".xlsx"},
            label="KOFIA fund-cost",
        )
        kis_path = _require_workbook(
            args.kis_retirement_list,
            suffixes={".xlsx"},
            label="KIS retirement ETF",
        )
        if not args.kofia_source_url.startswith("https://"):
            raise ValueError("KOFIA source URL must use https")
        if not args.kis_source_url.startswith("https://"):
            raise ValueError("KIS source URL must use https")

        settings = Settings()
        service_key = _secret_value(settings.supabase_secret_key)
        if not settings.supabase_url or not service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

        collected_at = datetime.now(UTC)
        run_id = collected_at.strftime("%Y%m%dT%H%M%SZ")
        work_root = args.work_root / run_id
        metadata_path = work_root / "reference_input_metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "dataset": DATASET,
                    "kofia": {
                        "as_of": args.kofia_as_of.isoformat(),
                        "source_url": args.kofia_source_url,
                    },
                    "kis_retirement_eligibility": {
                        "as_of": args.kis_eligibility_as_of.isoformat(),
                        "source_url": args.kis_source_url,
                    },
                    "staged_at": collected_at.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        storage = OfficialRawStorage(
            supabase_url=settings.supabase_url,
            service_key=service_key,
            bucket_name=OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET,
        )
        manifest = storage.upload_run(
            run_id=run_id,
            files={
                "kofia-fund-costs": kofia_path,
                "kis-retirement-list": kis_path,
                "reference-metadata": metadata_path,
            },
            collected_at=collected_at,
        )
        storage.promote_current_run(dataset=DATASET, manifest=manifest)
    except (OSError, ValueError) as error:
        print(f"official ETF reference staging failed: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "artifact_count": len(manifest.artifacts),
                "bucket": OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET,
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
