import argparse
import hashlib
import json
import time
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
    KindDisclosureError,
    KindDisclosureRow,
    KindDistributionEvent,
    decode_kind_html,
    fetch_disclosure_search,
    fetch_document,
    fetch_document_path,
    fetch_viewer,
    parse_disclosure_search,
    parse_distribution_events,
    parse_document_url,
    parse_main_document_number,
)

DEFAULT_START_DATE = date(2020, 1, 1)
PAGE_SIZE = 3000


def _event_key(event: KindDistributionEvent) -> tuple[str, date]:
    return event.isu_code, event.record_date


def collect_kind_distributions(
    *,
    start_date: date,
    end_date: date,
    raw_root: Path,
    output_root: Path,
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
                    raw_root
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
                        ),
                    )
                    atomic_write_bytes(search_path, raw_search)
                page_rows = parse_disclosure_search(
                    decode_kind_html(raw_search)
                )
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
            current = disclosures.get(row.receipt_number)
            if current is None or row.submitted_at > current.submitted_at:
                disclosures[row.receipt_number] = row

        parsed_events: list[KindDistributionEvent] = []
        failures = []
        for position, row in enumerate(
            sorted(disclosures.values(), key=lambda item: item.receipt_number),
            start=1,
        ):
            document_path = (
                raw_root
                / "documents"
                / row.receipt_number[:4]
                / f"{row.receipt_number}.html"
            )
            metadata_path = document_path.with_suffix(".json")
            try:
                if document_path.exists() and metadata_path.exists():
                    raw_document = document_path.read_bytes()
                    metadata = json.loads(metadata_path.read_text("utf-8"))
                    source_url = metadata["source_url"]
                else:
                    raw_viewer = request_with_retry(
                        partial(
                            fetch_viewer,
                            client, receipt_number=row.receipt_number
                        ),
                    )
                    doc_number = parse_main_document_number(
                        decode_kind_html(raw_viewer)
                    )
                    raw_path = request_with_retry(
                        partial(
                            fetch_document_path,
                            client, doc_number=doc_number
                        ),
                    )
                    source_url = parse_document_url(decode_kind_html(raw_path))
                    raw_document = request_with_retry(
                        partial(
                            fetch_document,
                            client, source_url=source_url
                        ),
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
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        ).encode("utf-8"),
                    )
                parsed_events.extend(
                    parse_distribution_events(
                        decode_kind_html(raw_document),
                        receipt_number=row.receipt_number,
                        submitted_at=row.submitted_at,
                        source_url=source_url,
                        isu_code=row.isu_code,
                        isu_name=row.isu_name,
                    )
                )
            except (KindDisclosureError, KeyError, json.JSONDecodeError) as exc:
                failures.append(
                    {
                        "receipt_number": row.receipt_number,
                        "error": str(exc),
                    }
                )
            if position % 25 == 0 or position == len(disclosures):
                print(
                    json.dumps(
                        {
                            "completed_disclosures": position,
                            "disclosure_count": len(disclosures),
                            "parsed_event_count": len(parsed_events),
                            "failure_count": len(failures),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            time.sleep(0.05)

    final_events: dict[tuple[str, date], KindDistributionEvent] = {}
    for event in parsed_events:
        current = final_events.get(_event_key(event))
        if current is None or event.submitted_at > current.submitted_at:
            final_events[_event_key(event)] = event

    ordered_events = sorted(
        final_events.values(), key=lambda item: (item.record_date, item.isu_code)
    )
    report = {
        "report_type": "kind_etf_distribution_events",
        "source": "KRX KIND ETF profit distribution disclosures",
        "source_url": (
            f"{KIND_BASE_URL}{KIND_ETF_DISCLOSURE_ENDPOINT}"
            "?method=searchDisclosureByStockTypeEtf"
        ),
        "coverage_start": start_date.isoformat(),
        "coverage_end": end_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "search_row_count": len(searches),
        "unique_disclosure_count": len(disclosures),
        "parsed_event_count_before_correction_dedup": len(parsed_events),
        "event_count": len(ordered_events),
        "failure_count": len(failures),
        "search_files": search_files,
        "failures": failures,
        "correction_policy": (
            "For the same ETF and record date, keep the event from the latest "
            "submitted disclosure."
        ),
        "events": [asdict(event) for event in ordered_events],
    }
    output_path = output_root / (
        f"etf_distributions_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    atomic_write_json(output_path, report, default=json_value)
    report["output_path"] = output_path.as_posix()
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect ETF distribution events from official KIND filings."
    )
    parser.add_argument(
        "--from-date", type=date.fromisoformat, default=DEFAULT_START_DATE
    )
    parser.add_argument(
        "--to-date", type=date.fromisoformat, default=date.today()
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/kind"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/cache/kind")
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = collect_kind_distributions(
        start_date=args.from_date,
        end_date=args.to_date,
        raw_root=args.raw_root,
        output_root=args.output,
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
