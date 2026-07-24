from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from backend.app.database import get_database_pool
from backend.app.settings import Settings


def test_database_pool_uses_configured_connection_bounds() -> None:
    get_database_pool.cache_clear()
    pool = get_database_pool(
        "postgresql://test:test@localhost:5432/test",
        max_size=8,
    )
    try:
        assert pool.min_size == 2
        assert pool.max_size == 8
        assert pool._check is ConnectionPool.check_connection
        # 트랜잭션 풀러(6543)에서 prepared statement 충돌을 막기 위해
        # psycopg가 서버측 prepared statement를 만들지 않도록 강제한다.
        assert pool.kwargs.get("prepare_threshold", "MISSING") is None
    finally:
        pool.close()
        get_database_pool.cache_clear()


def test_database_pool_max_size_defaults_to_safe_process_budget() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_pool_max_size == 5


def test_database_pool_max_size_reads_server_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_POOL_MAX_SIZE", "8")

    assert Settings(_env_file=None).database_pool_max_size == 8


def test_database_pool_max_size_rejects_values_outside_session_pool_budget() -> None:
    for value in (1, 16):
        try:
            Settings(_env_file=None, database_pool_max_size=value)
        except ValidationError:
            continue
        raise AssertionError(f"database_pool_max_size={value} must be rejected")
