import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool

from .engine.etf_theme import EtfThemeDefinition

_TOPICS = {
    "overview",
    "representative_companies",
    "investment_considerations",
}


@dataclass(frozen=True, slots=True)
class ThemeContentEvidence:
    evidence_id: str
    label: str
    locator: str
    publisher: str
    as_of: date | None


class EtfThemeVerificationReader(Protocol):
    def verified_evidence(
        self,
        *,
        catalog_version: str,
        theme_id: str,
        topic: str,
        content_sha256: str,
    ) -> tuple[ThemeContentEvidence, ...]: ...


def etf_theme_content_sha256(theme: EtfThemeDefinition, topic: str) -> str:
    """Hash exactly the catalog fields rendered for one question topic."""

    if topic == "overview":
        payload: object = {
            "plain_summary": theme.plain_summary,
            "definition": theme.definition,
            "exposure_segments": list(theme.exposure_segments),
            "one_line_analogy": theme.one_line_analogy,
        }
    elif topic == "representative_companies":
        payload = [
            {
                "name": company.name,
                "theme_role": company.theme_role,
                "plain_description": company.plain_description,
                "representative_reason": company.representative_reason,
            }
            for company in theme.representative_companies
        ]
    elif topic == "investment_considerations":
        payload = {
            "benefits": list(theme.benefits),
            "risks": list(theme.risks),
        }
    else:
        raise ValueError(f"unsupported ETF theme content topic: {topic}")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


class PostgresEtfThemeVerificationRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool
        self._today = today

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def verified_evidence(
        self,
        *,
        catalog_version: str,
        theme_id: str,
        topic: str,
        content_sha256: str,
    ) -> tuple[ThemeContentEvidence, ...]:
        if topic not in _TOPICS:
            raise ValueError(f"unsupported ETF theme content topic: {topic}")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    review.content_sha256,
                    review.review_due_date,
                    evidence.id,
                    evidence.source_label,
                    evidence.official_source_url,
                    document.publisher,
                    document.as_of_date,
                    document.license_status,
                    document.metadata,
                    evidence.knowledge_chunk_id,
                    chunk.metadata
                from public.etf_theme_content_reviews as review
                join public.etf_theme_content_evidence as evidence
                  on evidence.review_id = review.id
                join public.knowledge_documents as document
                  on document.id = evidence.knowledge_document_id
                left join public.knowledge_chunks as chunk
                  on chunk.document_id = evidence.knowledge_document_id
                 and chunk.id = evidence.knowledge_chunk_id
                where review.catalog_version = %s
                  and review.theme_id = %s
                  and review.topic = %s
                  and review.status = 'verified'
                order by evidence.display_order, evidence.id
                """,
                (catalog_version, theme_id, topic),
            )
            rows = cursor.fetchall()

        if not rows:
            return ()
        current_date = self._today()
        evidence_items: list[ThemeContentEvidence] = []
        for row in rows:
            if row[0] != content_sha256 or row[1] < current_date:
                return ()
            document_metadata = row[8]
            if (
                row[7] != "permitted"
                or not isinstance(document_metadata, dict)
                or document_metadata.get("data_boundary") != "verified_knowledge"
                or document_metadata.get("contains_personal_data") is not False
                or document_metadata.get("is_mock") is not False
                or not self._review_is_current(document_metadata, current_date)
            ):
                return ()
            chunk_id = row[9]
            chunk_metadata = row[10]
            if not isinstance(chunk_id, int) or (
                not isinstance(chunk_metadata, dict)
                or chunk_metadata.get("is_active") is False
                or chunk_metadata.get("data_boundary") != "verified_knowledge"
            ):
                return ()
            locator = str(row[4])
            official_source_urls = document_metadata.get("official_source_urls")
            if (
                not locator.startswith("https://")
                or not isinstance(official_source_urls, list)
                or locator not in official_source_urls
            ):
                return ()
            evidence_items.append(
                ThemeContentEvidence(
                    evidence_id=f"knowledge:{chunk_id}",
                    label=str(row[3]),
                    locator=locator,
                    publisher=str(row[5]),
                    as_of=row[6],
                )
            )
        return tuple(evidence_items)

    @staticmethod
    def _review_is_current(metadata: dict[str, object], today: date) -> bool:
        raw_due_date = metadata.get("review_due_date")
        if not isinstance(raw_due_date, str):
            return False
        try:
            return date.fromisoformat(raw_due_date) >= today
        except ValueError:
            return False
