"""Owner-scoped persistence and aggregate counts for User Pick follows."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict


class BenchmarkFollowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    follow_count: int
    is_following: bool


class UnknownBenchmarkPortfolioError(LookupError):
    """Raised when a follow target is not part of the published catalog."""


class BenchmarkFollowRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool: ConnectionPool | None = None,
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

    def list_states(self, owner_id: UUID) -> list[BenchmarkFollowState]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select
                    target.portfolio_id,
                    target.initial_follow_count
                        + count(follow.owner_id)::integer as follow_count,
                    coalesce(
                        bool_or(follow.owner_id = %s),
                        false
                    ) as is_following
                from public.benchmark_follow_targets as target
                left join public.user_benchmark_portfolio_follows as follow
                  on follow.portfolio_id = target.portfolio_id
                group by
                    target.portfolio_id,
                    target.initial_follow_count,
                    target.display_order
                order by target.display_order
                """,
                (owner_id,),
            )
            return [
                BenchmarkFollowState(
                    portfolio_id=row[0],
                    follow_count=row[1],
                    is_following=bool(row[2]),
                )
                for row in cursor
            ]

    def set_following(
        self,
        owner_id: UUID,
        *,
        portfolio_id: str,
        following: bool,
    ) -> BenchmarkFollowState:
        with self._connection() as connection, connection.cursor() as cursor:
            if following:
                cursor.execute(
                    """
                    insert into public.user_benchmark_portfolio_follows (
                        owner_id,
                        portfolio_id
                    )
                    select %s, target.portfolio_id
                    from public.benchmark_follow_targets as target
                    where target.portfolio_id = %s
                    on conflict (owner_id, portfolio_id) do nothing
                    """,
                    (owner_id, portfolio_id),
                )
            else:
                cursor.execute(
                    """
                    delete from public.user_benchmark_portfolio_follows
                    where owner_id = %s
                      and portfolio_id = %s
                    """,
                    (owner_id, portfolio_id),
                )

            cursor.execute(
                """
                select
                    target.portfolio_id,
                    target.initial_follow_count
                        + count(follow.owner_id)::integer as follow_count,
                    exists (
                        select 1
                        from public.user_benchmark_portfolio_follows as mine
                        where mine.owner_id = %s
                          and mine.portfolio_id = target.portfolio_id
                    ) as is_following
                from public.benchmark_follow_targets as target
                left join public.user_benchmark_portfolio_follows as follow
                  on follow.portfolio_id = target.portfolio_id
                where target.portfolio_id = %s
                group by
                    target.portfolio_id,
                    target.initial_follow_count
                """,
                (owner_id, portfolio_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise UnknownBenchmarkPortfolioError(portfolio_id)
        return BenchmarkFollowState(
            portfolio_id=row[0],
            follow_count=row[1],
            is_following=bool(row[2]),
        )
