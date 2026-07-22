from psycopg_pool import ConnectionPool

from backend.app.database import get_database_pool


def test_database_pool_uses_configured_connection_bounds() -> None:
    get_database_pool.cache_clear()
    pool = get_database_pool("postgresql://test:test@localhost:5432/test")
    try:
        assert pool.min_size == 2
        assert pool.max_size == 5
        assert pool._check is ConnectionPool.check_connection
    finally:
        pool.close()
        get_database_pool.cache_clear()
