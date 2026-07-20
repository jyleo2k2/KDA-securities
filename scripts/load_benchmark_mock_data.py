"""Load tracked synthetic benchmark CSVs into isolated Supabase tables."""

# ruff: noqa: E501 -- keep database column assignments visually aligned.

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
LOADS = (
    ("benchmark_mock_users", ROOT / "data/mock/users.csv"),
    ("benchmark_mock_accounts", ROOT / "data/mock/accounts.csv"),
    ("benchmark_mock_holdings", ROOT / "data/mock/holdings.csv"),
)
MANIFEST = ROOT / "data/mock/demo_scenario_users.json"


def _sync_demo_links(cursor: psycopg.Cursor) -> None:
    users = json.loads(MANIFEST.read_text(encoding="utf-8"))["users"]
    rows = [
        (item["benchmark_user_id"], item["auth_user_id"], item["scenario_code"])
        for item in users
    ]
    cursor.executemany(
        """
        update public.demo_user_financial_context as context
        set benchmark_user_id = benchmark.user_id,
            representative_age = benchmark.age::smallint,
            tax_year = benchmark.tax_year::smallint,
            gross_salary_krw = nullif(benchmark.gross_salary_krw, '')::numeric,
            comprehensive_income_krw = nullif(benchmark.comprehensive_income_krw, '')::numeric,
            pension_savings_contribution_krw = benchmark.pension_savings_contribution_krw::numeric,
            irp_contribution_krw = benchmark.irp_contribution_krw::numeric,
            updated_at = now()
        from public.benchmark_mock_users as benchmark
        where benchmark.user_id = %s
          and context.auth_user_id = %s::uuid
        """,
        [(benchmark_id, auth_id) for benchmark_id, auth_id, _ in rows],
    )
    cursor.executemany(
        """
        update public.mock_accounts as demo_account
        set benchmark_account_id = benchmark.account_id,
            balance_krw = benchmark.balance_krw::numeric
        from public.mock_scenarios as scenario,
             public.benchmark_mock_accounts as benchmark
        where scenario.code = %s
          and demo_account.scenario_id = scenario.id
          and benchmark.user_id = %s
          and demo_account.account_type = case benchmark.account_type
              when 'DC' then 'dc'
              when 'IRP' then 'irp'
              when 'PENSION_SAVINGS_FUND' then 'pension_savings'
          end
        """,
        [(scenario_code, benchmark_id) for benchmark_id, _, scenario_code in rows],
    )


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "update public.demo_user_financial_context set benchmark_user_id = null"
        )
        cursor.execute("update public.mock_accounts set benchmark_account_id = null")
        for table, _ in reversed(LOADS):
            cursor.execute(f"truncate table public.{table}")
        for table, path in LOADS:
            copy_sql = f"copy public.{table} from stdin with (format csv, header true)"
            with cursor.copy(copy_sql) as copy, path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    copy.write(chunk)
            cursor.execute(f"select count(*) from public.{table}")
            print(f"{table}={cursor.fetchone()[0]}")
        _sync_demo_links(cursor)


if __name__ == "__main__":
    main()
