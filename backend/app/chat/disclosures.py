import calendar
import re
from datetime import date, datetime
from decimal import Decimal

import psycopg
from pydantic import BaseModel, ConfigDict

from ..engine import AccountType


class ProviderDisclosure(BaseModel):
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


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", value.lower()).replace("주식회사", "")


def _rank(question: str, row: ProviderDisclosure) -> tuple[int, Decimal]:
    query = _normalized(question)
    company = _normalized(row.company_name)
    exact = 1 if company and company in query else 0
    reserve = row.reserve_krw or Decimal("0")
    return (exact, reserve)


class DisclosureReadRepository:
    """Read only live-ingested FSS snapshots; fixtures are never queried here."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def search(
        self,
        question: str,
        *,
        account_type: AccountType,
        limit: int,
    ) -> list[ProviderDisclosure]:
        rows = (
            self._pension_savings_rows()
            if account_type == AccountType.PENSION_SAVINGS
            else self._retirement_rows(account_type)
        )
        ranked = sorted(rows, key=lambda row: _rank(question, row), reverse=True)
        explicit = [row for row in ranked if _rank(question, row)[0] == 1]
        selected = explicit if explicit else ranked
        return selected[: max(1, min(limit, 5))]

    def _pension_savings_rows(self) -> list[ProviderDisclosure]:
        with (
            psycopg.connect(self._database_url) as connection,
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

    def _retirement_rows(self, account_type: AccountType) -> list[ProviderDisclosure]:
        with (
            psycopg.connect(self._database_url) as connection,
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
