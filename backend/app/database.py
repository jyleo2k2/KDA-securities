"""Process-wide PostgreSQL connection pool for request-time read paths."""

from functools import lru_cache

from psycopg_pool import ConnectionPool


@lru_cache(maxsize=1)
def get_database_pool(database_url: str) -> ConnectionPool:
    """Keep a small reusable pool per API process."""

    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=4,
        timeout=5,
        kwargs={"connect_timeout": 5},
        open=False,
    )


def close_pool(pool: ConnectionPool | None) -> None:
    if pool is not None:
        pool.close()
