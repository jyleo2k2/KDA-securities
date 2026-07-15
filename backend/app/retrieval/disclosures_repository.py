"""Read-only access to normalized FSS disclosure snapshots.

Writes happen only through the ingestion repositories; this module serves the
REST read path and never mutates disclosure tables.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import psycopg

MAX_LIMIT = 500


@dataclass(frozen=True, slots=True)
class PensionSavingsProviderStat:
    year: int
    quarter: int
    area_name_raw: str
    company_name_raw: str
    reserve_krw: Decimal | None
    earn_rate_1y: Decimal | None
    avg_earn_rate_3y: Decimal | None
    fee_rate_1y: Decimal | None
    quality_flags: list[str]
    observed_at: datetime
    source_name: str
    source_url: str


@dataclass(frozen=True, slots=True)
class RetirementProviderStat:
    year: int
    quarter: int
    scheme: str
    area_name_raw: str
    company_name_raw: str
    reserve_krw: Decimal | None
    earn_rate_current: Decimal | None
    avg_earn_rate_3y: Decimal | None
    avg_earn_rate_5y: Decimal | None
    quality_flags: list[str]
    observed_at: datetime
    source_name: str
    source_url: str


class DisclosureReadRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def latest_pension_savings_stats(
        self,
        *,
        year: int | None = None,
        quarter: int | None = None,
        provider_name: str | None = None,
        limit: int = 100,
    ) -> list[PensionSavingsProviderStat]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    year, quarter, area_name_raw, company_name_raw,
                    reserve_krw, earn_rate_1y, avg_earn_rate_3y, fee_rate_1y,
                    stats.quality_flags, stats.observed_at,
                    source.name, source.base_url
                from public.pension_savings_provider_stats as stats
                join public.data_sources as source on source.id = stats.source_id
                where (%s::smallint is null or year = %s)
                  and (%s::smallint is null or quarter = %s)
                  and (%s::text is null or company_name_raw = %s)
                order by year desc, quarter desc, company_name_raw
                limit %s
                """,
                (
                    year,
                    year,
                    quarter,
                    quarter,
                    provider_name,
                    provider_name,
                    max(1, min(limit, MAX_LIMIT)),
                ),
            )
            return [PensionSavingsProviderStat(*row) for row in cursor]

    def latest_retirement_stats(
        self,
        *,
        scheme: str | None = None,
        year: int | None = None,
        quarter: int | None = None,
        provider_name: str | None = None,
        limit: int = 100,
    ) -> list[RetirementProviderStat]:
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    year, quarter, scheme, area_name_raw, company_name_raw,
                    reserve_krw, earn_rate_current, avg_earn_rate_3y,
                    stats.avg_earn_rate_5y, stats.quality_flags,
                    stats.observed_at, source.name, source.base_url
                from public.retirement_provider_stats as stats
                join public.data_sources as source on source.id = stats.source_id
                where (%s::text is null or scheme = %s)
                  and (%s::smallint is null or year = %s)
                  and (%s::smallint is null or quarter = %s)
                  and (%s::text is null or company_name_raw = %s)
                order by year desc, quarter desc, company_name_raw, scheme
                limit %s
                """,
                (
                    scheme,
                    scheme,
                    year,
                    year,
                    quarter,
                    quarter,
                    provider_name,
                    provider_name,
                    max(1, min(limit, MAX_LIMIT)),
                ),
            )
            return [RetirementProviderStat(*row) for row in cursor]
