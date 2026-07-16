import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from backend.app.settings import get_settings

from .law_open_client import (
    LAW_OPEN_ENDPOINT,
    LawOpenApiError,
    LawOpenDocument,
    fetch_law_open_document,
    parse_law_open_payload,
)

DEFAULT_RAW_ROOT = Path("data/raw/law_open")
DEFAULT_CACHE_ROOT = Path("data/cache/law_open")
LAW_OPEN_GUIDE_URL = (
    "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulInfoGuide"
)

DOCUMENT_SPECS = (
    {
        "slug": "retirement_benefit_act_enforcement_decree",
        "target": "law",
        "name": "근로자퇴직급여 보장법 시행령",
    },
    {
        "slug": "retirement_benefit_act_enforcement_rule",
        "target": "law",
        "name": "근로자퇴직급여 보장법 시행규칙",
    },
    {
        "slug": "retirement_pension_supervision_regulation",
        "target": "admrul",
        "name": "퇴직연금감독규정",
    },
    {
        "slug": "retirement_pension_supervision_detailed_rule",
        "target": "admrul",
        "name": "퇴직연금감독규정시행세칙",
    },
)


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    slug: str
    target: str
    name: str
    effective_date: str
    status: str
    sha256: str
    relative_path: str


def _raw_path(root: Path, snapshot_date: date, slug: str) -> Path:
    return root / snapshot_date.isoformat() / f"{slug}.json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _persist_raw(
    path: Path,
    *,
    slug: str,
    document: LawOpenDocument,
) -> DocumentRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(document.raw_content)
    temporary.replace(path)
    return DocumentRecord(
        slug=slug,
        target=document.target,
        name=document.returned_name,
        effective_date=document.effective_date,
        status="fetched",
        sha256=hashlib.sha256(document.raw_content).hexdigest(),
        relative_path=path.as_posix(),
    )


def _load_raw(
    path: Path,
    *,
    slug: str,
    target: str,
    name: str,
) -> tuple[LawOpenDocument, DocumentRecord]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LawOpenApiError(f"invalid saved law-open-data JSON: {path}") from exc
    document = parse_law_open_payload(
        payload,
        target=target,
        requested_name=name,
        raw_content=raw,
    )
    return document, DocumentRecord(
        slug=slug,
        target=target,
        name=document.returned_name,
        effective_date=document.effective_date,
        status="skipped_existing",
        sha256=hashlib.sha256(raw).hexdigest(),
        relative_path=path.as_posix(),
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _law_article(document: LawOpenDocument, number: str) -> dict[str, Any]:
    root = document.payload.get("법령")
    articles = root.get("조문", {}).get("조문단위") if isinstance(root, dict) else None
    for article in _as_list(articles):
        if isinstance(article, dict) and str(article.get("조문번호")) == number:
            return article
    raise LawOpenApiError(f"{document.returned_name} article {number} is missing")


def _admrul_article(document: LawOpenDocument, heading: str) -> str:
    root = document.payload.get("AdmRulService")
    articles = root.get("조문내용") if isinstance(root, dict) else None
    for article in _as_list(articles):
        if isinstance(article, str) and article.startswith(heading):
            return article
    raise LawOpenApiError(f"{document.returned_name} {heading} is missing")


def _numbered_item(
    rows: Any,
    *,
    number_key: str,
    number: str,
) -> dict[str, Any]:
    for row in _as_list(rows):
        if isinstance(row, dict) and row.get(number_key) == number:
            return row
    raise LawOpenApiError(f"legal item {number} is missing")


def _text_segment(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise LawOpenApiError(f"legal text marker is missing: {start_marker}")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        end = len(text)
    return text[start:end].strip()


def _tdf_criteria(article: str) -> list[str]:
    criteria = []
    position = 0
    for number in range(1, 6):
        marker = f"{number}. "
        start = article.find(marker, position)
        if start < 0:
            raise LawOpenApiError(f"qualified-TDF criterion {number} is missing")
        next_marker = f"{number + 1}. "
        end = article.find(next_marker, start + len(marker)) if number < 5 else -1
        if end < 0:
            end = len(article)
        criteria.append(article[start:end].strip())
        position = end
    return criteria


def _source(
    document: LawOpenDocument,
    *,
    article: str,
    evidence_text: str,
) -> dict[str, str]:
    return {
        "document_name": document.returned_name,
        "effective_date": document.effective_date,
        "article": article,
        "evidence_text": evidence_text,
        "api_endpoint": LAW_OPEN_ENDPOINT,
    }


def build_pension_regulatory_master(
    documents: dict[str, LawOpenDocument],
    *,
    snapshot_date: date,
    records: list[DocumentRecord] | None = None,
) -> dict[str, Any]:
    decree = documents["retirement_benefit_act_enforcement_decree"]
    rule = documents["retirement_benefit_act_enforcement_rule"]
    regulation = documents["retirement_pension_supervision_regulation"]
    detailed = documents["retirement_pension_supervision_detailed_rule"]

    decree_26 = _law_article(decree, "26")
    decree_first = _numbered_item(decree_26.get("항"), number_key="항번호", number="①")
    decree_second = _numbered_item(
        decree_first.get("호"), number_key="호번호", number="2."
    )
    decree_second_a = _numbered_item(
        decree_second.get("목"), number_key="목번호", number="가."
    )

    rule_10 = _law_article(rule, "10")
    rule_first = _numbered_item(rule_10.get("항"), number_key="항번호", number="①")
    dc_irp_limit = _numbered_item(
        rule_first.get("호"), number_key="호번호", number="2."
    )
    if "100분의 70" not in str(dc_irp_limit.get("호내용", "")):
        raise LawOpenApiError("DC/IRP 70 percent rule text has changed")

    regulation_11 = _admrul_article(regulation, "제11조(")
    tdf_basis = _text_segment(regulation_11, "9. 투자목표시점", "10. 법")
    default_option_basis = _text_segment(regulation_11, "10. 법", "② 확정")
    detailed_5_2 = _admrul_article(detailed, "제5조의2(")
    criteria = _tdf_criteria(detailed_5_2)

    rules = [
        {
            "rule_id": "DC_IRP_GENERAL_RISK_ASSET_CAP",
            "account_types": ["dc", "irp"],
            "cap_treatment": "GENERAL_70",
            "aggregate_limit_percent": 70,
            "source": _source(
                rule,
                article="제10조 제1항 제2호",
                evidence_text=str(dc_irp_limit["호내용"]),
            ),
        },
        {
            "rule_id": "DC_IRP_LOWER_RISK_METHOD_CAP_EXCLUSION",
            "account_types": ["dc", "irp"],
            "cap_treatment": "EXCLUDED_FROM_GENERAL_70",
            "product_level_verification_required": True,
            "source": _source(
                decree,
                article="제26조 제1항 제2호 가목",
                evidence_text=str(decree_second_a["목내용"]),
            ),
        },
        {
            "rule_id": "DC_IRP_QUALIFIED_TDF_CRITERIA",
            "account_types": ["dc", "irp"],
            "cap_treatment": "EXCLUDED_FROM_GENERAL_70_IF_QUALIFIED",
            "product_level_verification_required": True,
            "criteria": criteria,
            "sources": [
                _source(
                    regulation,
                    article="제11조 제1항 제9호",
                    evidence_text=tdf_basis,
                ),
                _source(
                    detailed,
                    article="제5조의2",
                    evidence_text=detailed_5_2,
                ),
            ],
        },
        {
            "rule_id": "DC_IRP_DEFAULT_OPTION_APPROVAL",
            "account_types": ["dc", "irp"],
            "cap_treatment": "EXCLUDED_FROM_GENERAL_70_IF_APPROVED",
            "product_level_verification_required": True,
            "source": _source(
                regulation,
                article="제11조 제1항 제10호",
                evidence_text=default_option_basis,
            ),
        },
    ]
    return {
        "report_type": "pension_account_regulatory_rules",
        "snapshot_date": snapshot_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "국가법령정보 공동활용 Open API",
        "source_guide_url": LAW_OPEN_GUIDE_URL,
        "api_endpoint": LAW_OPEN_ENDPOINT,
        "account_scope": ["dc", "irp"],
        "limitations": [
            "연금저축계좌 상품 적격성은 이 퇴직연금 법령 마스터의 적용 대상이 아니다",
            "법령상 적격 TDF 요건만으로 개별 상품 적격성을 자동 확정하지 않는다",
            "개별 상품의 70% 또는 100% 매매 한도는 "
            "퇴직연금사업자 공식 목록으로 확인한다",
            "디폴트옵션은 고용노동부 승인상품 목록과 별도로 대조해야 한다",
        ],
        "documents": [asdict(record) for record in (records or [])],
        "rules": rules,
    }


def collect_pension_regulatory_rules(
    *,
    api_key: str,
    snapshot_date: date,
    raw_root: Path,
    cache_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    documents: dict[str, LawOpenDocument] = {}
    records: list[DocumentRecord] = []
    with httpx.Client(
        timeout=httpx.Timeout(60.0),
        headers={"User-Agent": "pension-copilot-law-open/0.1"},
    ) as client:
        for spec in DOCUMENT_SPECS:
            path = _raw_path(raw_root, snapshot_date, spec["slug"])
            if path.exists() and not force:
                try:
                    document, record = _load_raw(path, **spec)
                except (LawOpenApiError, OSError):
                    document = fetch_law_open_document(
                        client,
                        api_key=api_key,
                        target=spec["target"],
                        name=spec["name"],
                    )
                    record = _persist_raw(path, slug=spec["slug"], document=document)
            else:
                document = fetch_law_open_document(
                    client,
                    api_key=api_key,
                    target=spec["target"],
                    name=spec["name"],
                )
                record = _persist_raw(path, slug=spec["slug"], document=document)
            documents[spec["slug"]] = document
            records.append(record)

    master = build_pension_regulatory_master(
        documents,
        snapshot_date=snapshot_date,
        records=records,
    )
    cache_path = cache_root / f"pension_regulatory_rules_{snapshot_date}.json"
    _atomic_json(cache_path, master)
    manifest_path = raw_root / "manifests" / f"law_open_{snapshot_date}.json"
    _atomic_json(
        manifest_path,
        {
            "source": master["source"],
            "snapshot_date": snapshot_date.isoformat(),
            "generated_at": master["generated_at"],
            "documents": [asdict(record) for record in records],
        },
    )
    return {
        "snapshot_date": snapshot_date.isoformat(),
        "document_count": len(records),
        "rule_count": len(master["rules"]),
        "fetched": sum(record.status == "fetched" for record in records),
        "skipped_existing": sum(
            record.status == "skipped_existing" for record in records
        ),
        "cache_path": cache_path.as_posix(),
        "manifest_path": manifest_path.as_posix(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect current pension laws and build a regulatory rule master."
    )
    parser.add_argument(
        "--snapshot-date", type=date.fromisoformat, default=date.today()
    )
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cache-output", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if settings.law_open_api_key is None:
        raise SystemExit("LAW_OPEN_API_KEY is required")
    api_key = settings.law_open_api_key.get_secret_value().strip()
    if not api_key:
        raise SystemExit("LAW_OPEN_API_KEY is required")
    result = collect_pension_regulatory_rules(
        api_key=api_key,
        snapshot_date=args.snapshot_date,
        raw_root=args.raw_output,
        cache_root=args.cache_output,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
