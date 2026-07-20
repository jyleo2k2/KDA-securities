from backend.app.database import get_database_pool


def test_database_pool_uses_configured_connection_bounds() -> None:
    get_database_pool.cache_clear()
    pool = get_database_pool("postgresql://test:test@localhost:5432/test")
    try:
        assert pool.min_size == 2
        assert pool.max_size == 4
    finally:
        pool.close()
        get_database_pool.cache_clear()
