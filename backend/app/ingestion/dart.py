import argparse
import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import httpx

from backend.app.settings import get_settings

from .dart_client import (
    DART_DOCUMENT_ENDPOINT,
    DART_LIST_ENDPOINT,
    DartApiError,
    DartDisclosure,
    DartDisclosurePage,
    fetch_fund_disclosure_page,
    fetch_original_document,
    parse_disclosure_payload,
)
from .fsc_fund import fsc_match_key, krx_match_key

DEFAULT_RAW_ROOT = Path("data/raw/dart")
DEFAULT_CACHE_ROOT = Path("data/cache/dart")
DEFAULT_LOOKBACK_DAYS = 365
MAX_DART_WINDOW_DAYS = 90
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
KEYWORDS = (
    "총보수",
    "기타비용",
    "매매·중개수수료",
    "매매중개수수료",
    "합성",
    "파생상품",
    "환헤지",
    "위험등급",
    "기초지수",
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


def _latest(path: Path, pattern: str) -> Path:
    candidates = sorted(path.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"no matching file found under {path}")
    return candidates[-1]


def dart_fund_match_key(name: str) -> str:
    normalized = fsc_match_key(name)
    if not normalized:
        normalized = krx_match_key(name)
    return normalized[:-1] if normalized.endswith("H") else normalized


def _target_products(report: dict[str, Any]) -> list[dict[str, Any]]:
    products = report.get("products")
    if not isinstance(products, list):
        raise ValueError("cost-return report must contain products")
    targets = []
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("cost-return products must be JSON objects")
        cost = product.get("cost")
        classification = product.get("classification")
        if not isinstance(cost, dict) or not isinstance(classification, dict):
            raise ValueError("product cost/classification must be JSON objects")
        missing_kis_cost = cost.get("kis_total_expense_ratio_percent") is None
        low_confidence = classification.get("classification_confidence") == "low"
        if not missing_kis_cost and not low_confidence:
            continue
        code = product.get("isu_code")
        name = product.get("isu_name")
        if not isinstance(code, str) or not isinstance(name, str):
            raise ValueError("target product code/name must be strings")
        targets.append(
            {
                "isu_code": code,
                "isu_name": name,
                "match_key": dart_fund_match_key(name),
                "reasons": [
                    reason
                    for condition, reason in (
                        (missing_kis_cost, "missing_kis_total_expense_ratio"),
                        (low_confidence, "low_classification_confidence"),
                    )
                    if condition
                ],
            }
        )
    return targets


def _raw_page_path(
    raw_root: Path, begin_date: date, end_date: date, page_number: int
) -> Path:
    period = f"{begin_date:%Y%m%d}_{end_date:%Y%m%d}"
    return raw_root / "fund_disclosures" / period / f"page_{page_number:04d}.json"


def _date_windows(begin_date: date, end_date: date) -> list[tuple[date, date]]:
    if begin_date > end_date:
        raise ValueError("begin_date must be on or before end_date")
    windows = []
    window_end = end_date
    while window_end >= begin_date:
        window_begin = max(
            begin_date, window_end - timedelta(days=MAX_DART_WINDOW_DAYS)
        )
        windows.append((window_begin, window_end))
        window_end = window_begin - timedelta(days=1)
    return windows


def _load_page(path: Path) -> DartDisclosurePage:
    raw = path.read_bytes()
    return parse_disclosure_payload(json.loads(raw), raw_content=raw)


def _collect_disclosures(
    *,
    client: httpx.Client,
    api_key: str,
    begin_date: date,
    end_date: date,
    raw_root: Path,
    force: bool,
) -> tuple[list[DartDisclosure], list[dict[str, Any]]]:
    page_number = 1
    total_pages: int | None = None
    disclosures: list[DartDisclosure] = []
    pages = []
    while total_pages is None or page_number <= total_pages:
        path = _raw_page_path(raw_root, begin_date, end_date, page_number)
        if path.exists() and not force:
            page = _load_page(path)
            status = "skipped_existing"
        else:
            page = fetch_fund_disclosure_page(
                client,
                api_key=api_key,
                begin_date=begin_date,
                end_date=end_date,
                page_number=page_number,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_bytes(page.raw_content)
            temporary.replace(path)
            status = "fetched"
        if page.page_number != page_number and page.total_count:
            raise ValueError("OpenDART returned an unexpected page number")
        disclosures.extend(page.disclosures)
        pages.append(
            {
                "page_number": page_number,
                "row_count": len(page.disclosures),
                "sha256": hashlib.sha256(page.raw_content).hexdigest(),
                "path": path.as_posix(),
                "status": status,
            }
        )
        total_pages = page.total_pages
        if total_pages == 0:
            break
        page_number += 1
    return disclosures, pages


def _disclosure_key(disclosure: DartDisclosure) -> str:
    if "상장지수투자신탁" not in disclosure.report_name:
        return ""
    return dart_fund_match_key(disclosure.report_name)


def _report_priority(report_name: str) -> int:
    if "투자설명서" in report_name:
        return 3
    if "일괄신고서" in report_name:
        return 2
    if "증권신고서" in report_name:
        return 1
    return 0


def _match_targets(
    targets: list[dict[str, Any]], disclosures: list[DartDisclosure]
) -> list[dict[str, Any]]:
    lookup: dict[str, list[DartDisclosure]] = {}
    for disclosure in disclosures:
        key = _disclosure_key(disclosure)
        if key:
            lookup.setdefault(key, []).append(disclosure)
    matched = []
    for target in targets:
        candidates = lookup.get(target["match_key"], [])
        candidates.sort(
            key=lambda item: (
                item.receipt_date,
                _report_priority(item.report_name),
                item.receipt_number,
            ),
            reverse=True,
        )
        selected = candidates[0] if candidates else None
        matched.append(
            {
                **target,
                "match_status": (
                    "matched_exact_normalized_name" if selected else "unmatched"
                ),
                "candidate_count": len(candidates),
                "selected_disclosure": (
                    {
                        **asdict(selected),
                        "receipt_date": selected.receipt_date.isoformat(),
                        "source_url": DART_VIEWER_URL + selected.receipt_number,
                    }
                    if selected
                    else None
                ),
            }
        )
    return matched


def _decode_document_member(content: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _document_text(content: bytes) -> tuple[str, list[str]]:
    texts = []
    member_names = []
    with ZipFile(BytesIO(content)) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            member_names.append(name)
            decoded = _decode_document_member(archive.read(name))
            parser = _TextExtractor()
            parser.feed(decoded)
            texts.append(" ".join(parser.parts))
    return " ".join(texts), member_names


def _keyword_evidence(text: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    counts = {}
    snippets = {}
    for keyword in KEYWORDS:
        positions = [
            match.start() for match in re.finditer(re.escape(keyword), compact)
        ]
        counts[keyword] = len(positions)
        if positions:
            start = max(0, positions[0] - 120)
            end = min(len(compact), positions[0] + len(keyword) + 180)
            snippets[keyword] = compact[start:end]
    return {"keyword_counts": counts, "first_keyword_snippets": snippets}


def _collect_selected_documents(
    *,
    client: httpx.Client,
    api_key: str,
    matches: list[dict[str, Any]],
    raw_root: Path,
    force: bool,
) -> None:
    for match in matches:
        selected = match["selected_disclosure"]
        if selected is None:
            match["document"] = None
            continue
        receipt_number = selected["receipt_number"]
        path = raw_root / "documents" / f"{receipt_number}.zip"
        if path.exists() and not force:
            content = path.read_bytes()
            status = "skipped_existing"
        else:
            try:
                document = fetch_original_document(
                    client,
                    api_key=api_key,
                    receipt_number=receipt_number,
                )
            except DartApiError as exc:
                match["document"] = {
                    "status": "document_unavailable",
                    "dart_status": exc.dart_status,
                    "error": str(exc),
                }
                continue
            content = document.content
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".zip.tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
            status = "fetched"
        text, member_names = _document_text(content)
        match["document"] = {
            "path": path.as_posix(),
            "status": status,
            "sha256": hashlib.sha256(content).hexdigest(),
            "member_names": member_names,
            "text_character_count": len(text),
            **_keyword_evidence(text),
        }


def collect_dart_etf_evidence(
    *,
    api_key: str,
    source_report_path: Path,
    as_of: date,
    begin_date: date,
    raw_root: Path,
    cache_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    if begin_date > as_of:
        raise ValueError("begin_date must be on or before as_of")
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    targets = _target_products(source_report)
    with httpx.Client(
        timeout=httpx.Timeout(60.0),
        headers={"User-Agent": "pension-copilot-opendart/0.1"},
    ) as client:
        disclosures_by_receipt: dict[str, DartDisclosure] = {}
        pages = []
        for window_begin, window_end in _date_windows(begin_date, as_of):
            window_disclosures, window_pages = _collect_disclosures(
                client=client,
                api_key=api_key,
                begin_date=window_begin,
                end_date=window_end,
                raw_root=raw_root,
                force=force,
            )
            for disclosure in window_disclosures:
                disclosures_by_receipt[disclosure.receipt_number] = disclosure
            for page in window_pages:
                page["begin_date"] = window_begin.isoformat()
                page["end_date"] = window_end.isoformat()
            pages.extend(window_pages)
        disclosures = list(disclosures_by_receipt.values())
        matches = _match_targets(targets, disclosures)
        _collect_selected_documents(
            client=client,
            api_key=api_key,
            matches=matches,
            raw_root=raw_root,
            force=force,
        )

    output = {
        "report_type": "dart_etf_disclosure_evidence",
        "as_of": as_of.isoformat(),
        "begin_date": begin_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "source_report": source_report_path.as_posix(),
        "source_endpoints": [DART_LIST_ENDPOINT, DART_DOCUMENT_ENDPOINT],
        "target_rule": (
            "missing KIS total expense ratio or low classification confidence"
        ),
        "target_count": len(targets),
        "disclosure_count": len(disclosures),
        "matched_count": sum(
            row["match_status"].startswith("matched") for row in matches
        ),
        "unmatched_count": sum(row["match_status"] == "unmatched" for row in matches),
        "limitations": [
            (
                "Name matching does not prove that every numeric table was parsed "
                "correctly."
            ),
            (
                "Keyword snippets are discovery evidence and must not populate "
                "engine costs."
            ),
            (
                "Only explicitly parsed and validated document fields may become "
                "overrides."
            ),
            (
                "The search period is bounded; unmatched products may need an "
                "older window."
            ),
        ],
        "pages": pages,
        "products": matches,
    }
    cache_root.mkdir(parents=True, exist_ok=True)
    output_path = cache_root / f"etf_disclosure_evidence_{as_of}.json"
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return {
        "target_count": output["target_count"],
        "disclosure_count": output["disclosure_count"],
        "matched_count": output["matched_count"],
        "unmatched_count": output["unmatched_count"],
        "output_path": output_path.as_posix(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect OpenDART evidence for unresolved pension ETFs."
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--begin-date", type=date.fromisoformat)
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cache-output", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.dart_api_key is None:
        raise SystemExit("DART_API_KEY is required")
    api_key = settings.dart_api_key.get_secret_value().strip()
    if not api_key:
        raise SystemExit("DART_API_KEY is required")
    source_report = args.source_report or _latest(
        Path("data/cache/returns"), "pension_etf_cost_return_master_*.json"
    )
    begin_date = args.begin_date or (
        args.as_of - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    )
    result = collect_dart_etf_evidence(
        api_key=api_key,
        source_report_path=source_report,
        as_of=args.as_of,
        begin_date=begin_date,
        raw_root=args.raw_output,
        cache_root=args.cache_output,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
