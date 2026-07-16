import argparse
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import get_settings

from .fsc_fund_client import (
    FSC_FUND_PRODUCT_ENDPOINT,
    FscFundApiError,
    FscFundPage,
    fetch_fsc_fund_page,
    parse_fsc_fund_payload,
)

DEFAULT_NAME_QUERY = "상장지수투자신탁"
DEFAULT_ROWS_PER_PAGE = 1000
DEFAULT_RAW_ROOT = Path("data/raw/fsc/fund_product_basic")
DEFAULT_CACHE_ROOT = Path("data/cache/fsc")
DEFAULT_KRX_CACHE_ROOT = Path("data/cache/krx")

FUND_TYPE_ASSET_CLASS = {
    "주식형": "equity",
    "채권형": "fixed_income",
    "혼합주식형": "mixed_asset",
    "혼합채권형": "mixed_asset",
    "혼합자산": "mixed_asset",
    "단기금융": "cash_equivalent",
    "부동산": "real_estate",
    "특별자산": "real_asset",
    "재간접": "fund_of_funds",
    "파생상품": "derivatives",
}
ETF_BRANDS = (
    "TIMEFOLIO",
    "KIWOOM",
    "KOACT",
    "에셋플러스",
    "아이엠에셋",
    "HANARO",
    "KODEX",
    "TIGER",
    "KOSEF",
    "ARIRANG",
    "KBSTAR",
    "FOCUS",
    "마이티",
    "TREX",
    "TIME",
    "WON",
    "RISE",
    "PLUS",
    "ACE",
    "SOL",
    "1Q",
    "IBK",
    "HK",
    "BNK",
)
BRAND_ALIASES = {"ARIRANG": "PLUS", "KBSTAR": "RISE"}
LEGAL_SUFFIXES = (
    "증권상장지수투자신탁",
    "상장지수투자신탁",
)
TRAILING_LEGAL_TYPES = ("특별자산", "부동산", "증권")


@dataclass(frozen=True, slots=True)
class PageRecord:
    page_number: int
    row_count: int
    sha256: str
    relative_path: str
    status: str


def _latest_krx_report(cache_root: Path) -> Path:
    candidates = sorted(cache_root.glob("etf_market_evidence_*.json"))
    if not candidates:
        raise FileNotFoundError(f"no KRX ETF report found under {cache_root}")
    return candidates[-1]


def _raw_page_path(root: Path, snapshot_date: date, page_number: int) -> Path:
    return root / snapshot_date.isoformat() / f"page_{page_number:04d}.json"


def _write_raw(path: Path, page: FscFundPage) -> PageRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(page.raw_content)
    temporary.replace(path)
    return PageRecord(
        page_number=page.page_number,
        row_count=len(page.records),
        sha256=hashlib.sha256(page.raw_content).hexdigest(),
        relative_path=path.as_posix(),
        status="fetched",
    )


def _load_raw(path: Path) -> tuple[FscFundPage, PageRecord]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    page = parse_fsc_fund_payload(payload, raw_content=raw)
    return page, PageRecord(
        page_number=page.page_number,
        row_count=len(page.records),
        sha256=hashlib.sha256(raw).hexdigest(),
        relative_path=path.as_posix(),
        status="skipped_existing",
    )


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).upper()
    for source, target in BRAND_ALIASES.items():
        normalized = normalized.replace(source, target)
    return "".join(character for character in normalized if character.isalnum())


def krx_match_key(name: str) -> str:
    return _compact(name)


def fsc_match_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name)
    legal_match = re.search(
        r"(?:증권|특별자산|부동산)?\s*상장지수투자신탁",
        normalized,
    )
    if legal_match:
        normalized = normalized[: legal_match.start()]
    else:
        suffix_positions = [
            normalized.find(suffix)
            for suffix in LEGAL_SUFFIXES
            if normalized.find(suffix) >= 0
        ]
        if suffix_positions:
            normalized = normalized[: min(suffix_positions)]
    compact_end = normalized.rstrip()
    for legal_type in TRAILING_LEGAL_TYPES:
        if compact_end.endswith(legal_type):
            compact_end = compact_end[: -len(legal_type)]
            break
    normalized = compact_end
    upper = normalized.upper()
    brand_positions = [
        (upper.find(brand.upper()), brand)
        for brand in ETF_BRANDS
        if upper.find(brand.upper()) >= 0
    ]
    if brand_positions:
        start, brand = min(brand_positions, key=lambda item: item[0])
        normalized = normalized[start:]
        compact_brand = _compact(brand)
        compact_name = _compact(normalized)
        if compact_name.startswith(compact_brand * 2):
            normalized = compact_name[len(compact_brand) :]
    normalized = normalized.replace("ETF", "").replace("etf", "")
    return _compact(normalized)


def _normalize_funds(records: list[dict[str, str]]) -> list[dict[str, Any]]:
    latest_by_standard_code: dict[str, dict[str, str]] = {}
    for record in records:
        code = record["asoStdCd"]
        previous = latest_by_standard_code.get(code)
        if previous is None or record["basDt"] > previous["basDt"]:
            latest_by_standard_code[code] = record
    funds = []
    for record in latest_by_standard_code.values():
        fund_type = record["fndTp"].strip()
        funds.append(
            {
                "base_date": record["basDt"],
                "short_code": record["srtnCd"],
                "fund_name": record["fndNm"],
                "category": record["ctg"],
                "establishment_date": record["setpDt"],
                "fund_type": fund_type,
                "coarse_asset_class": FUND_TYPE_ASSET_CLASS.get(
                    fund_type, "other"
                ),
                "product_classification_code": record["prdClsfCd"],
                "fund_standard_code": record["asoStdCd"],
                "match_key": fsc_match_key(record["fndNm"]),
            }
        )
    return sorted(funds, key=lambda item: item["fund_standard_code"])


def _join_krx(
    krx_report_path: Path,
    funds: list[dict[str, Any]],
) -> dict[str, Any]:
    report = json.loads(krx_report_path.read_text(encoding="utf-8"))
    products = report.get("products")
    if not isinstance(products, list):
        raise ValueError("KRX ETF report must contain products")
    lookup: dict[str, list[dict[str, Any]]] = {}
    for fund in funds:
        lookup.setdefault(fund["match_key"], []).append(fund)

    joined = []
    for product in products:
        code = product.get("isu_code")
        name = product.get("isu_name")
        if not isinstance(code, str) or not isinstance(name, str):
            raise ValueError("KRX ETF product code and name must be strings")
        key = krx_match_key(name)
        candidates = lookup.get(key, [])
        if len(candidates) == 1:
            status = "matched_exact_normalized_name"
            matched_fund = candidates[0]
        elif len(candidates) > 1:
            status = "ambiguous"
            matched_fund = None
        else:
            status = "unmatched"
            matched_fund = None
        joined.append(
            {
                "isu_code": code,
                "isu_name": name,
                "match_status": status,
                "match_key": key,
                "candidate_count": len(candidates),
                "fund": matched_fund,
            }
        )
    return {
        "krx_as_of": report.get("as_of"),
        "krx_product_count": len(joined),
        "matched_count": sum(
            row["match_status"] == "matched_exact_normalized_name" for row in joined
        ),
        "ambiguous_count": sum(row["match_status"] == "ambiguous" for row in joined),
        "unmatched_count": sum(row["match_status"] == "unmatched" for row in joined),
        "products": joined,
    }


def collect_fsc_fund_products(
    *,
    api_key: str,
    snapshot_date: date,
    name_query: str,
    rows_per_page: int,
    raw_root: Path,
    cache_root: Path,
    krx_report_path: Path,
    force: bool = False,
) -> dict[str, Any]:
    if rows_per_page < 1 or rows_per_page > 10000:
        raise ValueError("rows-per-page must be between 1 and 10000")
    pages: list[FscFundPage] = []
    page_records: list[PageRecord] = []
    total_pages: int | None = None
    page_number = 1
    with httpx.Client(
        timeout=httpx.Timeout(60.0),
        headers={"User-Agent": "pension-copilot-fsc-fund/0.1"},
    ) as client:
        while total_pages is None or page_number <= total_pages:
            path = _raw_page_path(raw_root, snapshot_date, page_number)
            if path.exists() and not force:
                try:
                    page, record = _load_raw(path)
                except (FscFundApiError, json.JSONDecodeError, OSError):
                    page = fetch_fsc_fund_page(
                        client,
                        api_key=api_key,
                        page_number=page_number,
                        rows_per_page=rows_per_page,
                        name_query=name_query,
                    )
                    record = _write_raw(path, page)
            else:
                page = fetch_fsc_fund_page(
                    client,
                    api_key=api_key,
                    page_number=page_number,
                    rows_per_page=rows_per_page,
                    name_query=name_query,
                )
                record = _write_raw(path, page)
            if page.page_number != page_number:
                raise FscFundApiError("FSC returned an unexpected page number")
            pages.append(page)
            page_records.append(record)
            total_pages = max(1, math.ceil(page.total_count / rows_per_page))
            page_number += 1

    records = [record for page in pages for record in page.records]
    declared_total = pages[0].total_count if pages else 0
    if len(records) != declared_total:
        raise FscFundApiError(
            f"FSC total mismatch: declared={declared_total}, received={len(records)}"
        )
    funds = _normalize_funds(records)
    join_report = _join_krx(krx_report_path, funds)
    generated_at = datetime.now(UTC).isoformat()
    cache_root.mkdir(parents=True, exist_ok=True)

    fund_path = cache_root / f"fund_product_basic_{snapshot_date.isoformat()}.json"
    fund_output = {
        "source": "Financial Services Commission Fund Product Basic Information",
        "endpoint": FSC_FUND_PRODUCT_ENDPOINT,
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "name_query": name_query,
        "source_record_count": len(records),
        "fund_count": len(funds),
        "limitations": [
            "fund standard codes are not KRX listed issue codes",
            "fund type is a coarse asset class and does not identify region or hedge",
            "only exact normalized-name joins are accepted automatically",
        ],
        "funds": funds,
    }
    temporary = fund_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(fund_output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(fund_path)

    join_path = cache_root / f"krx_etf_fund_join_{snapshot_date.isoformat()}.json"
    join_output = {
        "source": fund_output["source"],
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "krx_report_path": krx_report_path.as_posix(),
        **join_report,
    }
    temporary_join = join_path.with_suffix(".json.tmp")
    temporary_join.write_text(
        json.dumps(join_output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_join.replace(join_path)

    manifest_root = raw_root / "manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_root / f"fund_product_basic_{snapshot_date}.json"
    manifest = {
        "source": fund_output["source"],
        "endpoint": FSC_FUND_PRODUCT_ENDPOINT,
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": generated_at,
        "name_query": name_query,
        "source_record_count": len(records),
        "page_count": len(page_records),
        "pages": [asdict(record) for record in page_records],
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return {
        "source_record_count": len(records),
        "fund_count": len(funds),
        "page_count": len(page_records),
        "matched_count": join_report["matched_count"],
        "ambiguous_count": join_report["ambiguous_count"],
        "unmatched_count": join_report["unmatched_count"],
        "fund_cache_path": fund_path.as_posix(),
        "join_cache_path": join_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect FSC fund-product data and join it to the KRX ETF universe."
    )
    parser.add_argument(
        "--snapshot-date", type=date.fromisoformat, default=date.today()
    )
    parser.add_argument("--name-query", default=DEFAULT_NAME_QUERY)
    parser.add_argument("--rows-per-page", type=int, default=DEFAULT_ROWS_PER_PAGE)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cache-output", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--krx-report", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.fsc_fund_product_api_key is None:
        raise SystemExit("FSC_FUND_PRODUCT_API_KEY is required")
    api_key = settings.fsc_fund_product_api_key.get_secret_value().strip()
    if not api_key:
        raise SystemExit("FSC_FUND_PRODUCT_API_KEY is required")
    result = collect_fsc_fund_products(
        api_key=api_key,
        snapshot_date=args.snapshot_date,
        name_query=args.name_query,
        rows_per_page=args.rows_per_page,
        raw_root=args.raw_output,
        cache_root=args.cache_output,
        krx_report_path=args.krx_report or _latest_krx_report(DEFAULT_KRX_CACHE_ROOT),
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
