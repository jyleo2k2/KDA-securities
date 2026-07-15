"""BGE-M3 차원 고정 마이그레이션을 원격에 적용 (이재용 직접 실행용).

supabase CLI 링크(access token) 없이 DATABASE_URL로 적용하고, CLI와 같은
형식으로 마이그레이션 히스토리를 기록한다. 이미 적용됐으면 건너뛴다(멱등).

    uv run python scripts/apply_embedding_migration.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from backend.app.settings import get_settings

VERSION = "20260715165614"
NAME = "fix_embedding_dimension_bge_m3"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / f"{VERSION}_{NAME}.sql"
)


def main() -> int:
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL이 설정되지 않았습니다 (.env 확인)", file=sys.stderr)
        return 1
    database_url = settings.database_url.get_secret_value().strip()
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    statements = [
        statement.strip()
        for statement in sql.split(";")
        if statement.strip() and not statement.strip().startswith("--")
    ]

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select 1 from supabase_migrations.schema_migrations"
                " where version = %s",
                (VERSION,),
            )
            if cursor.fetchone() is not None:
                print(f"이미 적용됨: {VERSION}_{NAME} — 건너뜀")
                return 0
            cursor.execute(sql)
            cursor.execute(
                "insert into supabase_migrations.schema_migrations"
                " (version, statements, name) values (%s, %s, %s)",
                (VERSION, statements, NAME),
            )
        connection.commit()
    print(f"적용 완료: {VERSION}_{NAME}")

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select atttypmod from pg_attribute"
            " where attrelid = 'public.knowledge_chunks'::regclass"
            " and attname = 'embedding'"
        )
        typmod = cursor.fetchone()[0]
        print(f"embedding 차원 확인: typmod={typmod} (1024차원 고정이면 1028)")
        cursor.execute(
            "select indexname from pg_indexes"
            " where tablename = 'knowledge_chunks' and indexname like '%hnsw%'"
        )
        for row in cursor.fetchall():
            print(f"HNSW 인덱스 확인: {row[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
