"""Process-wide PostgreSQL connection pool for request-time read paths."""

from functools import lru_cache

from psycopg_pool import ConnectionPool


@lru_cache(maxsize=1)
def get_database_pool(database_url: str) -> ConnectionPool:
    """Keep a small reusable pool per API process."""

    return ConnectionPool(
        conninfo=database_url,
        min_size=2,
        max_size=15,
        timeout=5,
        check=ConnectionPool.check_connection,
        # 현재 DATABASE_URL은 Supavisor session pooler(5432)라 prepared statement가
        # 정상 동작한다. transaction pooler(6543)로 전환하면 반드시
        # kwargs에 "prepare_threshold": None 을 추가해야 한다(psycopg 3.3 검증 완료).
        kwargs={"connect_timeout": 5},
        open=False,
    )


def close_pool(pool: ConnectionPool | None) -> None:
    if pool is not None:
        pool.close()
