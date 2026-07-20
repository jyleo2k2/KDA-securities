"""Read normalized full-universe KRX ETF volume snapshots from PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

import psycopg
from psycopg_pool import ConnectionPool

EtfMarketSort = Literal["trading_volume", "trading_value", "net_assets"]
SortOrder = Literal["asc", "desc"]

_SORT_COLUMNS: dict[EtfMarketSort, str] = {
    "trading_volume": "trading_volume",
    "trading_value": "trading_value_krw",
    "net_assets": "net_assets_krw",
}


class EtfMarketDataUnavailable(RuntimeError):
    """No normalized KRX ETF market snapshot is available."""


@dataclass(frozen=True, slots=True)
class EtfMarketObservation:
    base_date: date
    isu_code: str
    isu_name: str
    close_price_krw: Decimal
    fluctuation_rate_percent: Decimal | None
    nav_krw: Decimal | None
    trading_volume: int
    trading_value_krw: Decimal
    market_cap_krw: Decimal | None
    net_assets_krw: Decimal | None
    benchmark_name: str | None


@dataclass(frozen=True, slots=True)
class EtfMarketSnapshot:
    as_of: date
    total_count: int
    results: list[EtfMarketObservation]


class EtfMarketRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
        connection_factory: Callable[[str], Any] = psycopg.connect,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._pool is not None:
            with self._pool.connection() as connection:
                yield connection
            return
        with self._connection_factory(self._database_url) as connection:
            yield connection

    def list_snapshot(
        self,
        *,
        as_of: date | None,
        sort_by: EtfMarketSort,
        order: SortOrder,
        limit: int,
    ) -> EtfMarketSnapshot:
        sort_column = _SORT_COLUMNS[sort_by]
        direction = "asc" if order == "asc" else "desc"
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select max(base_date)
                from public.etf_daily_market_snapshots
                where (%s::date is null or base_date <= %s::date)
                """,
                (as_of, as_of),
            )
            target = cursor.fetchone()
            if target is None or target[0] is None:
                raise EtfMarketDataUnavailable("no KRX ETF market snapshot")
            target_date = target[0]
            cursor.execute(
                f"""
                select
                    base_date, isu_code, isu_name, close_price_krw,
                    fluctuation_rate_percent, nav_krw, trading_volume,
                    trading_value_krw, market_cap_krw, net_assets_krw,
                    benchmark_name, count(*) over ()
                from public.etf_daily_market_snapshots
                where base_date = %s
                order by {sort_column} {direction} nulls last, isu_code
                limit %s
                """,
                (target_date, limit),
            )
            rows = cursor.fetchall()
        if not rows:
            raise EtfMarketDataUnavailable("no KRX ETF rows for target date")
        results = [_observation(row[:11]) for row in rows]
        return EtfMarketSnapshot(
            as_of=target_date,
            total_count=int(rows[0][11]),
            results=results,
        )

    def volume_history(
        self,
        isu_code: str,
        *,
        from_date: date | None,
        to_date: date | None,
        limit: int,
    ) -> list[EtfMarketObservation]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    base_date, isu_code, isu_name, close_price_krw,
                    fluctuation_rate_percent, nav_krw, trading_volume,
                    trading_value_krw, market_cap_krw, net_assets_krw,
                    benchmark_name
                from public.etf_daily_market_snapshots
                where isu_code = %s
                  and (%s::date is null or base_date >= %s::date)
                  and (%s::date is null or base_date <= %s::date)
                order by base_date desc
                limit %s
                """,
                (isu_code, from_date, from_date, to_date, to_date, limit),
            )
            rows = cursor.fetchall()
        if not rows:
            raise KeyError(f"KRX ETF market history not found: {isu_code}")
        return list(reversed([_observation(row) for row in rows]))


def _observation(row: tuple[Any, ...]) -> EtfMarketObservation:
    return EtfMarketObservation(
        base_date=row[0],
        isu_code=str(row[1]),
        isu_name=str(row[2]),
        close_price_krw=Decimal(str(row[3])),
        fluctuation_rate_percent=(Decimal(str(row[4])) if row[4] is not None else None),
        nav_krw=Decimal(str(row[5])) if row[5] is not None else None,
        trading_volume=int(row[6]),
        trading_value_krw=Decimal(str(row[7])),
        market_cap_krw=Decimal(str(row[8])) if row[8] is not None else None,
        net_assets_krw=Decimal(str(row[9])) if row[9] is not None else None,
        benchmark_name=str(row[10]) if row[10] is not None else None,
    )
