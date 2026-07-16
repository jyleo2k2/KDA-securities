"""Load tracked synthetic benchmark CSVs into isolated Supabase tables."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
LOADS = (
    ("benchmark_mock_users", ROOT / "data/mock/users.csv"),
    ("benchmark_mock_accounts", ROOT / "data/mock/accounts.csv"),
    ("benchmark_mock_holdings", ROOT / "data/mock/holdings.csv"),
)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table, path in LOADS:
            cursor.execute(f"truncate table public.{table} cascade")
            copy_sql = f"copy public.{table} from stdin with (format csv, header true)"
            with cursor.copy(copy_sql) as copy, path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    copy.write(chunk)
            cursor.execute(f"select count(*) from public.{table}")
            print(f"{table}={cursor.fetchone()[0]}")


if __name__ == "__main__":
    main()
