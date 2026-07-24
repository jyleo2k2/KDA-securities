"""Process-wide PostgreSQL connection pool for request-time read paths."""

from functools import lru_cache

from psycopg_pool import ConnectionPool


@lru_cache(maxsize=1)
def get_database_pool(database_url: str, *, max_size: int = 5) -> ConnectionPool:
    """Keep a small reusable pool per API process."""

    return ConnectionPool(
        conninfo=database_url,
        min_size=2,
        # This is per API process. Keep headroom under the configured
        # Supabase session-pool cap for ingestion and other API processes.
        max_size=max_size,
        timeout=5,
        check=ConnectionPool.check_connection,
        # DATABASE_URL은 Supabase transaction pooler(6543)를 기본 전제로 한다.
        # 트랜잭션 풀러는 연결을 트랜잭션 단위로 재사용하므로 세션 풀러(5432)의
        # 15개 상한(EMAXCONNSESSION)을 압박하지 않는다. 대신 서버측 prepared
        # statement가 연결 간에 유지되지 않으므로 psycopg가 이를 만들지 않도록
        # prepare_threshold=None 을 강제한다(psycopg 3.3 검증 완료). 이 값은
        # 세션 풀러(5432)에서도 무해하므로 두 포트 모두에서 안전하다.
        kwargs={"connect_timeout": 5, "prepare_threshold": None},
        open=False,
    )


def close_pool(pool: ConnectionPool | None) -> None:
    if pool is not None:
        pool.close()
