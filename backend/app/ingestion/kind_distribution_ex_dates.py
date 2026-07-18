import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from typing import Any

import httpx

from ._files import atomic_write_bytes, atomic_write_json
from .kind_common import json_value, request_with_retry, windows
from .kind_distribution_client import (
    KIND_BASE_URL,
    KIND_ETF_DISCLOSURE_ENDPOINT,
    KIND_EX_DATE_REPORT_NAME,
    KindDisclosureError,
    KindDisclosureRow,
    KindDistributionExDateEvent,
    decode_kind_html,
    fetch_disclosure_search,
    fetch_document,
    fetch_document_path,
    fetch_viewer,
    parse_disclosure_search,
    parse_distribution_ex_date_event,
    parse_document_url,
    parse_main_document_number,
)

DEFAULT_START_DATE = date(2026, 1, 1)
PAGE_SIZE = 3000


def _document_event(
    *,
    client: httpx.Client,
    row: KindDisclosureRow,
    raw_root: Path,
) -> KindDistributionExDateEvent:
    document_path = (
        raw_root / "documents" / row.receipt_number[:4] / f"{row.receipt_number}.html"
    )
    metadata_path = document_path.with_suffix(".json")
    if document_path.exists() and metadata_path.exists():
        raw_document = document_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_url = metadata["source_url"]
    else:
        raw_viewer = request_with_retry(
            partial(fetch_viewer, client, receipt_number=row.receipt_number),
        )
        doc_number = parse_main_document_number(decode_kind_html(raw_viewer))
        raw_path = request_with_retry(
            partial(fetch_document_path, client, doc_number=doc_number),
        )
        source_url = parse_document_url(decode_kind_html(raw_path))
        raw_document = request_with_retry(
            partial(fetch_document, client, source_url=source_url),
        )
        atomic_write_bytes(document_path, raw_document)
        metadata = {
            "receipt_number": row.receipt_number,
            "doc_number": doc_number,
            "source_url": source_url,
            "sha256": hashlib.sha256(raw_document).hexdigest(),
        }
        atomic_write_bytes(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            ),
        )
    return parse_distribution_ex_date_event(
        decode_kind_html(raw_document),
        isu_code=row.isu_code,
        isu_name=row.isu_name,
        receipt_number=row.receipt_number,
        submitted_at=row.submitted_at,
        source_url=source_url,
    )


def collect_kind_distribution_ex_dates(
    *,
    start_date: date,
    end_date: date,
    raw_root: Path,
    output_root: Path,
    workers: int = 4,
) -> dict[str, Any]:
    searches: list[KindDisclosureRow] = []
    search_files = []
    timeout = httpx.Timeout(30.0)
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "pension-copilot-kind/0.1",
        "Referer": (
            f"{KIND_BASE_URL}/disclosure/disclosurebystocktype.do"
            "?method=searchDisclosureByStockTypeEtf"
        ),
    }
    ex_date_root = raw_root / "distribution_ex_dates"
    with httpx.Client(
        base_url=KIND_BASE_URL,
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
    ) as client:
        for window_start, window_end in windows(start_date, end_date):
            page_index = 1
            while True:
                search_path = (
                    ex_date_root
                    / "search"
                    / f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
                    / f"page_{page_index:04d}.html"
                )
                if search_path.exists():
                    raw_search = search_path.read_bytes()
                else:
                    raw_search = request_with_retry(
                        partial(
                            fetch_disclosure_search,
                            client,
                            start_date=window_start,
                            end_date=window_end,
                            page_index=page_index,
                            page_size=PAGE_SIZE,
                            report_name=KIND_EX_DATE_REPORT_NAME,
                        ),
                    )
                    atomic_write_bytes(search_path, raw_search)
                page_rows = parse_disclosure_search(decode_kind_html(raw_search))
                searches.extend(page_rows)
                search_files.append(
                    {
                        "path": search_path.as_posix(),
                        "sha256": hashlib.sha256(raw_search).hexdigest(),
                        "row_count": len(page_rows),
                    }
                )
                if len(page_rows) < PAGE_SIZE:
                    break
                page_index += 1

        disclosures: dict[str, KindDisclosureRow] = {}
        for row in searches:
            disclosures[row.receipt_number] = row

        parsed_events: list[KindDistributionExDateEvent] = []
        failures = []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(
                    _document_event,
                    client=client,
                    row=row,
                    raw_root=ex_date_root,
                ): row
                for row in disclosures.values()
            }
            for position, future in enumerate(as_completed(futures), start=1):
                row = futures[future]
                try:
                    parsed_events.append(future.result())
                except (
                    KindDisclosureError,
                    KeyError,
                    json.JSONDecodeError,
                ) as exc:
                    failures.append(
                        {
                            "receipt_number": row.receipt_number,
                            "isu_code": row.isu_code,
                            "error": str(exc),
                        }
                    )
                if position % 100 == 0 or position == len(futures):
                    print(
                        json.dumps(
                            {
                                "completed_disclosures": position,
                                "disclosure_count": len(futures),
                                "parsed_event_count": len(parsed_events),
                                "failure_count": len(failures),
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )

    final_events: dict[tuple[str, date], KindDistributionExDateEvent] = {}
    for event in parsed_events:
        key = (event.isu_code, event.effective_date)
        current = final_events.get(key)
        if current is None or event.submitted_at > current.submitted_at:
            final_events[key] = event
    ordered_events = sorted(
        final_events.values(),
        key=lambda event: (event.effective_date, event.isu_code),
    )
    report = {
        "report_type": "kind_etf_distribution_ex_dates",
        "source": "KRX KIND ETF ex-distribution reference price disclosures",
        "source_url": (
            f"{KIND_BASE_URL}{KIND_ETF_DISCLOSURE_ENDPOINT}"
            "?method=searchDisclosureByStockTypeEtf"
        ),
        "coverage_start": start_date.isoformat(),
        "coverage_end": end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "search_row_count": len(searches),
        "unique_disclosure_count": len(disclosures),
        "event_count": len(ordered_events),
        "failure_count": len(failures),
        "search_files": search_files,
        "failures": failures,
        "events": [asdict(event) for event in ordered_events],
    }
    output_path = output_root / (
        f"etf_distribution_ex_dates_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    atomic_write_json(output_path, report, default=json_value)
    report["output_path"] = output_path.as_posix()
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect exact ETF ex-distribution dates from KIND."
    )
    parser.add_argument(
        "--from-date", type=date.fromisoformat, default=DEFAULT_START_DATE
    )
    parser.add_argument("--to-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/kind"))
    parser.add_argument("--output", type=Path, default=Path("data/cache/kind"))
    parser.add_argument("--workers", type=int, default=4)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = collect_kind_distribution_ex_dates(
        start_date=args.from_date,
        end_date=args.to_date,
        raw_root=args.raw_root,
        output_root=args.output,
        workers=args.workers,
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "events"},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
