"""Read-only aggregate queries for the anonymous benchmark dataset."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

import psycopg
from psycopg_pool import ConnectionPool


@dataclass(frozen=True, slots=True)
class BenchmarkDistribution:
    code: str
    count: int


@dataclass(frozen=True, slots=True)
class BenchmarkAccountTypeStat:
    account_type: str
    account_count: int
    mean_balance_krw: Decimal
    mean_monthly_contribution_krw: Decimal
    mean_risky_asset_ratio_percent: Decimal


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    user_count: int
    account_count: int
    holding_count: int
    age_groups: list[BenchmarkDistribution]
    risk_profiles: list[BenchmarkDistribution]
    account_type_stats: list[BenchmarkAccountTypeStat]


class BenchmarkRepository:
    """Expose only population-level mock-data statistics to the API."""

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

    def get_summary(self) -> BenchmarkSummary:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    (select count(*) from benchmark.benchmark_mock_users),
                    (select count(*) from benchmark.benchmark_mock_accounts),
                    (select count(*) from benchmark.benchmark_mock_holdings)
                """
            )
            user_count, account_count, holding_count = cursor.fetchone()

            cursor.execute(
                """
                select age_group, count(*)
                from benchmark.benchmark_mock_users
                group by age_group
                order by case age_group
                    when '20s' then 1
                    when '30s' then 2
                    when '40s' then 3
                    when '50_plus' then 4
                    else 99
                end
                """
            )
            age_groups = [
                BenchmarkDistribution(code=row[0], count=row[1]) for row in cursor
            ]

            cursor.execute(
                """
                select risk_profile, count(*)
                from benchmark.benchmark_mock_users
                group by risk_profile
                order by case risk_profile
                    when 'STABLE_SEEKING' then 1
                    when 'STABLE' then 2
                    when 'RISK_NEUTRAL' then 3
                    when 'ACTIVE' then 4
                    else 99
                end
                """
            )
            risk_profiles = [
                BenchmarkDistribution(code=row[0], count=row[1]) for row in cursor
            ]

            cursor.execute(
                """
                select
                    account_type,
                    count(*),
                    avg(nullif(balance_krw, '')::numeric),
                    avg(nullif(monthly_contribution_krw, '')::numeric),
                    avg(nullif(risky_asset_ratio, '')::numeric) * 100
                from benchmark.benchmark_mock_accounts
                group by account_type
                order by case account_type
                    when 'DC' then 1
                    when 'IRP' then 2
                    when 'PENSION_SAVINGS_FUND' then 3
                    else 99
                end
                """
            )
            account_type_stats = [
                BenchmarkAccountTypeStat(
                    account_type=row[0],
                    account_count=row[1],
                    mean_balance_krw=row[2],
                    mean_monthly_contribution_krw=row[3],
                    mean_risky_asset_ratio_percent=row[4],
                )
                for row in cursor
            ]

        return BenchmarkSummary(
            user_count=user_count,
            account_count=account_count,
            holding_count=holding_count,
            age_groups=age_groups,
            risk_profiles=risk_profiles,
            account_type_stats=account_type_stats,
        )
