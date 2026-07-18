"""Read-only access to normalized FSS disclosure snapshots.

Writes happen only through the ingestion repositories; this module serves the
REST read path and never mutates disclosure tables. 챗봇의 최신분기 회사별
조회(SQL)도 여기에 통합돼 있다(랭킹은 chat 계층 책임).
"""

import calendar
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict

from ..engine import AccountType

MAX_LIMIT = 500


class ProviderDisclosure(BaseModel):
    """Latest-quarter provider snapshot shaped for chat answers."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    account_type: AccountType
    year: int
    quarter: int
    reserve_krw: Decimal | None
    earn_rate_current_pct: Decimal | None
    avg_earn_rate_3y_pct: Decimal | None
    avg_earn_rate_5y_pct: Decimal | None
    avg_earn_rate_7y_pct: Decimal | None
    avg_earn_rate_10y_pct: Decimal | None
    fee_rate_1y_pct: Decimal | None = None
    observed_at: datetime
    source_locator: str

    @property
    def period_end(self) -> date:
        month = self.quarter * 3
        return date(self.year, month, calendar.monthrange(self.year, month)[1])


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


class DisclosureReadRepository:
    def __init__(
        self, database_url: str, *, pool: ConnectionPool | None = None
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def latest_pension_savings_stats(
        self,
        *,
        year: int | None = None,
        quarter: int | None = None,
        limit: int = 100,
    ) -> list[PensionSavingsProviderStat]:
        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    year, quarter, area_name_raw, company_name_raw,
                    reserve_krw, earn_rate_1y, avg_earn_rate_3y, fee_rate_1y,
                    quality_flags, observed_at
                from public.pension_savings_provider_stats
                where (%s::smallint is null or year = %s)
                  and (%s::smallint is null or quarter = %s)
                order by year desc, quarter desc, company_name_raw
                limit %s
                """,
                (year, year, quarter, quarter, max(1, min(limit, MAX_LIMIT))),
            )
            return [PensionSavingsProviderStat(*row) for row in cursor]

    def latest_retirement_stats(
        self,
        *,
        scheme: str | None = None,
        year: int | None = None,
        quarter: int | None = None,
        limit: int = 100,
    ) -> list[RetirementProviderStat]:
        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                select
                    year, quarter, scheme, area_name_raw, company_name_raw,
                    reserve_krw, earn_rate_current, avg_earn_rate_3y,
                    avg_earn_rate_5y, quality_flags, observed_at
                from public.retirement_provider_stats
                where (%s::text is null or scheme = %s)
                  and (%s::smallint is null or year = %s)
                  and (%s::smallint is null or quarter = %s)
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
                    max(1, min(limit, MAX_LIMIT)),
                ),
            )
            return [RetirementProviderStat(*row) for row in cursor]

    def latest_quarter_disclosures(
        self, account_type: AccountType
    ) -> list[ProviderDisclosure]:
        """Return every provider row from the most recent live-ingested quarter."""
        if account_type == AccountType.PENSION_SAVINGS:
            return self._latest_quarter_pension_savings()
        return self._latest_quarter_retirement(account_type)

    def _latest_quarter_pension_savings(self) -> list[ProviderDisclosure]:
        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                with latest as (
                    select year, quarter
                    from public.pension_savings_provider_stats
                    order by year desc, quarter desc
                    limit 1
                )
                select
                    ps.company_name_raw, ps.year, ps.quarter, ps.reserve_krw,
                    ps.earn_rate_current, ps.avg_earn_rate_3y,
                    ps.avg_earn_rate_5y, ps.avg_earn_rate_7y,
                    ps.avg_earn_rate_10y, ps.fee_rate_1y, ps.observed_at,
                    ds.base_url
                from public.pension_savings_provider_stats as ps
                join latest using (year, quarter)
                join public.data_sources as ds on ds.id = ps.source_id
                where ds.is_active
                """
            )
            return [
                ProviderDisclosure(
                    company_name=row[0],
                    account_type=AccountType.PENSION_SAVINGS,
                    year=row[1],
                    quarter=row[2],
                    reserve_krw=row[3],
                    earn_rate_current_pct=row[4],
                    avg_earn_rate_3y_pct=row[5],
                    avg_earn_rate_5y_pct=row[6],
                    avg_earn_rate_7y_pct=row[7],
                    avg_earn_rate_10y_pct=row[8],
                    fee_rate_1y_pct=row[9],
                    observed_at=row[10],
                    source_locator=row[11],
                )
                for row in cursor
            ]

    def _latest_quarter_retirement(
        self, account_type: AccountType
    ) -> list[ProviderDisclosure]:
        with (
            self._connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                with latest as (
                    select year, quarter
                    from public.retirement_provider_stats
                    where scheme = %s
                    order by year desc, quarter desc
                    limit 1
                )
                select
                    rp.company_name_raw, rp.year, rp.quarter, rp.reserve_krw,
                    rp.earn_rate_current, rp.avg_earn_rate_3y,
                    rp.avg_earn_rate_5y, rp.avg_earn_rate_7y,
                    rp.avg_earn_rate_10y, rp.observed_at, ds.base_url
                from public.retirement_provider_stats as rp
                join latest using (year, quarter)
                join public.data_sources as ds on ds.id = rp.source_id
                where rp.scheme = %s and ds.is_active
                """,
                (account_type.value, account_type.value),
            )
            return [
                ProviderDisclosure(
                    company_name=row[0],
                    account_type=account_type,
                    year=row[1],
                    quarter=row[2],
                    reserve_krw=row[3],
                    earn_rate_current_pct=row[4],
                    avg_earn_rate_3y_pct=row[5],
                    avg_earn_rate_5y_pct=row[6],
                    avg_earn_rate_7y_pct=row[7],
                    avg_earn_rate_10y_pct=row[8],
                    observed_at=row[9],
                    source_locator=row[10],
                )
                for row in cursor
            ]
