"""Validate and load the approved 20-theme verification ledger."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import psycopg

from ..etf_theme_repository import EtfThemeRepository
from ..etf_theme_verification_repository import etf_theme_content_sha256
from ..retrieval.knowledge_policy import is_allowed_official_source_url

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_MANIFEST = ROOT / "data" / "knowledge" / "etf_theme_evidence.json"
ETF_THEME_CONTENT_TOPICS = (
    "overview",
    "representative_companies",
    "investment_considerations",
    "performance_drivers",
    "risks",
)
_EVIDENCE_ROLES = {
    "overview": "definition",
    "representative_companies": "company_profile",
    "investment_considerations": "service_interpretation",
    "performance_drivers": "performance_driver",
    "risks": "risk",
}


class ThemeEvidenceManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ThemeEvidenceBinding:
    theme_id: str
    source_label: str
    publisher: str
    official_source_url: str


@dataclass(frozen=True, slots=True)
class ThemeEvidenceManifest:
    catalog_version: str
    knowledge_document_id: str
    reviewer: str
    verified_at: datetime
    review_due_date: date
    themes: tuple[ThemeEvidenceBinding, ...]


@dataclass(frozen=True, slots=True)
class ThemeVerificationLoadResult:
    review_count: int
    evidence_count: int
    knowledge_document_id: str


def load_theme_evidence_manifest(
    repository: EtfThemeRepository,
    path: Path = DEFAULT_EVIDENCE_MANIFEST,
) -> ThemeEvidenceManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ThemeEvidenceManifestError("failed to read ETF theme evidence") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ThemeEvidenceManifestError("schema_version must be 1")

    def required_text(key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ThemeEvidenceManifestError(f"{key} is required")
        return value.strip()

    catalog_version = required_text("catalog_version")
    if catalog_version != repository.catalog.catalog_version:
        raise ThemeEvidenceManifestError("catalog_version does not match catalog")
    try:
        verified_at = datetime.fromisoformat(required_text("verified_at"))
        review_due_date = date.fromisoformat(required_text("review_due_date"))
    except ValueError as error:
        raise ThemeEvidenceManifestError(
            "approval dates must use ISO format"
        ) from error
    if verified_at.tzinfo is None:
        raise ThemeEvidenceManifestError("verified_at must include a timezone")
    if review_due_date < verified_at.date():
        raise ThemeEvidenceManifestError("review_due_date precedes verification")

    raw_themes = payload.get("themes")
    if not isinstance(raw_themes, list):
        raise ThemeEvidenceManifestError("themes must be a list")
    bindings: list[ThemeEvidenceBinding] = []
    for entry in raw_themes:
        if not isinstance(entry, dict):
            raise ThemeEvidenceManifestError("theme evidence entries must be objects")
        values: dict[str, str] = {}
        for key in ("theme_id", "source_label", "publisher", "official_source_url"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ThemeEvidenceManifestError(f"theme evidence {key} is required")
            values[key] = value.strip()
        if not is_allowed_official_source_url(values["official_source_url"]):
            raise ThemeEvidenceManifestError("theme evidence URL is not official")
        bindings.append(ThemeEvidenceBinding(**values))

    expected_ids = {theme.theme_id for theme in repository.list()}
    actual_ids = [binding.theme_id for binding in bindings]
    if len(actual_ids) != len(set(actual_ids)):
        raise ThemeEvidenceManifestError("theme evidence contains duplicate theme IDs")
    if set(actual_ids) != expected_ids:
        raise ThemeEvidenceManifestError("theme evidence must cover all catalog themes")
    return ThemeEvidenceManifest(
        catalog_version=catalog_version,
        knowledge_document_id=required_text("knowledge_document_id"),
        reviewer=required_text("reviewer"),
        verified_at=verified_at,
        review_due_date=review_due_date,
        themes=tuple(bindings),
    )


def load_theme_verification_ledger(
    database_url: str,
    *,
    repository: EtfThemeRepository,
    manifest: ThemeEvidenceManifest,
) -> ThemeVerificationLoadResult:
    """Upsert all 100 approvals and their exact RAG chunk evidence atomically."""

    if not database_url:
        raise ValueError("database_url is required")
    themes_by_id = {theme.theme_id: theme for theme in repository.list()}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select id, metadata
            from public.knowledge_documents
            where metadata ->> 'document_id' = %s
            order by updated_at desc
            """,
            (manifest.knowledge_document_id,),
        )
        document_rows = cursor.fetchall()
        if len(document_rows) != 1:
            raise RuntimeError(
                "approved ETF theme knowledge document is missing or duplicated"
            )
        knowledge_document_id, document_metadata = document_rows[0]
        official_urls = document_metadata.get("official_source_urls", [])
        if not isinstance(official_urls, list):
            raise RuntimeError(
                "approved ETF theme document has invalid source metadata"
            )

        cursor.execute(
            """
            select id, content
            from public.knowledge_chunks
            where document_id = %s
              and metadata ->> 'is_active' is distinct from 'false'
            order by chunk_index
            """,
            (knowledge_document_id,),
        )
        chunks = cursor.fetchall()
        chunks_by_theme: dict[str, int] = {}
        for binding in manifest.themes:
            if binding.official_source_url not in official_urls:
                raise RuntimeError(
                    "official source is absent from RAG metadata: "
                    f"{binding.theme_id}"
                )
            marker = f"[theme:{binding.theme_id}]"
            matching = [
                int(chunk_id)
                for chunk_id, content in chunks
                if marker in content
            ]
            if len(matching) != 1:
                raise RuntimeError(
                    "theme RAG marker is missing or duplicated: "
                    f"{binding.theme_id}"
                )
            chunks_by_theme[binding.theme_id] = matching[0]

        review_count = 0
        evidence_count = 0
        for binding in manifest.themes:
            theme = themes_by_id[binding.theme_id]
            for topic in ETF_THEME_CONTENT_TOPICS:
                cursor.execute(
                    """
                    insert into public.etf_theme_content_reviews (
                        catalog_version, theme_id, topic, content_sha256,
                        status, verified_at, review_due_date, reviewer, review_notes
                    )
                    values (%s, %s, %s, %s, 'verified', %s, %s, %s, %s)
                    on conflict (catalog_version, theme_id, topic) do update set
                        content_sha256 = excluded.content_sha256,
                        status = excluded.status,
                        verified_at = excluded.verified_at,
                        review_due_date = excluded.review_due_date,
                        reviewer = excluded.reviewer,
                        review_notes = excluded.review_notes,
                        updated_at = now()
                    returning id
                    """,
                    (
                        manifest.catalog_version,
                        binding.theme_id,
                        topic,
                        etf_theme_content_sha256(theme, topic),
                        manifest.verified_at,
                        manifest.review_due_date,
                        manifest.reviewer,
                        "승인 대화 5개와 공식 링크 교차 검토 완료; "
                        "카탈로그 payload 해시 고정",
                    ),
                )
                review_row = cursor.fetchone()
                if review_row is None:
                    raise RuntimeError("failed to upsert ETF theme review")
                review_id = int(review_row[0])
                cursor.execute(
                    """
                    delete from public.etf_theme_content_evidence
                    where review_id = %s
                      and (
                          official_source_url <> %s
                          or evidence_role <> %s
                      )
                    """,
                    (
                        review_id,
                        binding.official_source_url,
                        _EVIDENCE_ROLES[topic],
                    ),
                )
                cursor.execute(
                    """
                    insert into public.etf_theme_content_evidence (
                        review_id, knowledge_document_id, knowledge_chunk_id,
                        official_source_url, source_label, evidence_role, display_order
                    )
                    values (%s, %s, %s, %s, %s, %s, 1)
                    on conflict (review_id, official_source_url, evidence_role)
                    do update set
                        knowledge_document_id = excluded.knowledge_document_id,
                        knowledge_chunk_id = excluded.knowledge_chunk_id,
                        source_label = excluded.source_label,
                        display_order = excluded.display_order
                    """,
                    (
                        review_id,
                        knowledge_document_id,
                        chunks_by_theme[binding.theme_id],
                        binding.official_source_url,
                        binding.source_label,
                        _EVIDENCE_ROLES[topic],
                    ),
                )
                review_count += 1
                evidence_count += 1
        cursor.execute(
            """
            select count(*)
            from public.etf_theme_content_reviews
            where catalog_version = %s and status = 'verified'
            """,
            (manifest.catalog_version,),
        )
        count_row = cursor.fetchone()
        if count_row is None or int(count_row[0]) != review_count:
            raise RuntimeError("remote ETF theme review count does not match the load")
        cursor.execute(
            """
            select count(*)
            from public.etf_theme_content_evidence as evidence
            join public.etf_theme_content_reviews as review
              on review.id = evidence.review_id
            where review.catalog_version = %s and review.status = 'verified'
            """,
            (manifest.catalog_version,),
        )
        evidence_row = cursor.fetchone()
        if evidence_row is None or int(evidence_row[0]) != evidence_count:
            raise RuntimeError(
                "remote ETF theme evidence count does not match the load"
            )
    return ThemeVerificationLoadResult(
        review_count=review_count,
        evidence_count=evidence_count,
        knowledge_document_id=str(knowledge_document_id),
    )
