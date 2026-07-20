import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import Settings

from ._files import atomic_write_bytes, atomic_write_json, sha256_hex
from ._secrets import require_secret
from .fsc_stock_dividend_client import (
    FSC_STOCK_DIVIDEND_ENDPOINT,
    FscStockDividendApiError,
    fetch_fsc_stock_dividend_page,
    parse_fsc_stock_dividend_payload,
)


def collect_fsc_stock_dividends(
    *,
    api_key: str,
    base_date: date | None,
    raw_root: Path,
    output_root: Path,
    rows_per_page: int = 1000,
    force: bool = False,
) -> dict[str, Any]:
    if rows_per_page < 1:
        raise ValueError("rows-per-page must be positive")
    records = []
    pages = []
    page_number = 1
    with httpx.Client(
        timeout=httpx.Timeout(30.0),
        headers={
            "Accept": "application/json",
            "User-Agent": "pension-copilot-fsc-stock-dividend/0.1",
        },
    ) as client:
        while True:
            partition = base_date.isoformat() if base_date is not None else "all"
            path = raw_root / partition / f"page_{page_number:04d}.json"
            if path.exists() and not force:
                raw_content = path.read_bytes()
                page = parse_fsc_stock_dividend_payload(
                    json.loads(raw_content), raw_content=raw_content
                )
                status = "skipped_existing"
            else:
                page = fetch_fsc_stock_dividend_page(
                    client,
                    api_key=api_key,
                    page_number=page_number,
                    rows_per_page=rows_per_page,
                    base_date=(base_date.strftime("%Y%m%d") if base_date else ""),
                )
                atomic_write_bytes(path, page.raw_content)
                status = "fetched"
            records.extend(page.records)
            pages.append(
                {
                    "page_number": page_number,
                    "row_count": len(page.records),
                    "status": status,
                    "raw_path": path.as_posix(),
                    "sha256": sha256_hex(page.raw_content),
                }
            )
            if len(records) >= page.total_count or not page.records:
                break
            page_number += 1

    data_as_of = max((record["basDt"] for record in records), default=None)
    report = {
        "report_type": "fsc_stock_dividend_information",
        "source": "Financial Services Commission Public Data Portal",
        "endpoint": FSC_STOCK_DIVIDEND_ENDPOINT,
        "requested_base_date": base_date.isoformat() if base_date else None,
        "data_as_of": (
            f"{data_as_of[:4]}-{data_as_of[4:6]}-{data_as_of[6:]}"
            if data_as_of
            else None
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "page_count": len(pages),
        "record_count": len(records),
        "pages": pages,
        "records": records,
        "license": "KOGL Type 2: attribution, non-commercial use only",
    }
    output_suffix = data_as_of or (
        base_date.strftime("%Y%m%d") if base_date else "empty"
    )
    output_path = output_root / f"stock_dividends_{output_suffix}.json"
    atomic_write_json(output_path, report)
    report["output_path"] = output_path.as_posix()
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect FSC stock dividends.")
    parser.add_argument("--base-date", type=date.fromisoformat)
    parser.add_argument(
        "--raw-output", type=Path, default=Path("data/raw/fsc/stock_dividends")
    )
    parser.add_argument("--output", type=Path, default=Path("data/cache/fsc"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--rows-per-page", type=int, default=1000)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings(_env_file=args.env_file)
    secret = settings.fsc_stock_dividend_api_key or settings.fsc_fund_product_api_key
    result = collect_fsc_stock_dividends(
        api_key=require_secret(secret, "FSC_STOCK_DIVIDEND_API_KEY"),
        base_date=args.base_date,
        raw_root=args.raw_output,
        output_root=args.output,
        rows_per_page=args.rows_per_page,
        force=args.force,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "records"},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FscStockDividendApiError as exc:
        raise SystemExit(str(exc)) from exc
