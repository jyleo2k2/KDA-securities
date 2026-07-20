"""Render the additive demo-customer migration and the matching seed tail."""

# ruff: noqa: E501 -- long lines are intentional inside generated SQL literals.

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"
MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260720022220_unify_demo_customer_contract.sql"
)
SEED = ROOT / "supabase" / "seed.sql"
SEED_START = "-- BEGIN GENERATED DEMO CUSTOMER CONTRACT V2"
SEED_END = "-- END GENERATED DEMO CUSTOMER CONTRACT V2"


def _quote(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def _read_accounts() -> dict[tuple[str, str], dict[str, str]]:
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    scenario_by_user = {
        item["benchmark_user_id"]: item["scenario_code"] for item in manifest
    }
    result: dict[tuple[str, str], dict[str, str]] = {}
    with (MOCK_DIR / "accounts.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            scenario = scenario_by_user.get(row["user_id"])
            if scenario is not None:
                result[(scenario, row["account_type"])] = row
    return result


def _sync_sql() -> str:
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    scenarios = json.loads(
        (MOCK_DIR / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )
    source_accounts = _read_accounts()

    user_values = ",\n        ".join(
        f"({_quote(item['auth_user_id'])}::uuid, {_quote(item['scenario_code'])}, "
        f"{_quote(item['benchmark_user_id'])}, {item['representative_age']}::smallint)"
        for item in manifest
    )
    scenario_values = ",\n        ".join(
        f"({_quote(item['scenario_code'])}, {_quote(item['age_band'])}, "
        f"{_quote(item['risk_profile'])}, {item['investment_horizon_years']}::smallint)"
        for item in scenarios
    )
    account_values = ",\n        ".join(
        f"({_quote(scenario)}, {_quote({'DC': 'dc', 'IRP': 'irp', 'PENSION_SAVINGS_FUND': 'pension_savings'}[account_type])}, "
        f"{_quote(row['account_id'])}, {row['balance_krw']}::numeric)"
        for (scenario, account_type), row in source_accounts.items()
    )

    holding_rows: list[str] = []
    for scenario in scenarios:
        for account in scenario["accounts"]:
            for holding in account["holdings"]:
                holding_rows.append(
                    "("
                    + ", ".join(
                        (
                            _quote(scenario["scenario_code"]),
                            _quote(account["account_type"]),
                            _quote(holding["asset_class_code"]),
                            _quote(holding["instrument_name"]),
                            f"{holding['amount_krw']}::numeric",
                            _quote(holding["risk_treatment"]),
                            _quote(holding.get("statutory_exception")),
                            _quote(holding.get("etf_isu_code")),
                        )
                    )
                    + ")"
                )
    holding_values = ",\n        ".join(holding_rows)

    return f"""
with user_link (auth_user_id, scenario_code, benchmark_user_id, representative_age) as (
    values
        {user_values}
)
update public.demo_user_financial_context as context
set benchmark_user_id = link.benchmark_user_id,
    representative_age = link.representative_age,
    tax_year = benchmark.tax_year::smallint,
    gross_salary_krw = nullif(benchmark.gross_salary_krw, '')::numeric,
    comprehensive_income_krw = nullif(benchmark.comprehensive_income_krw, '')::numeric,
    pension_savings_contribution_krw = benchmark.pension_savings_contribution_krw::numeric,
    irp_contribution_krw = benchmark.irp_contribution_krw::numeric,
    updated_at = now()
from user_link as link
join public.benchmark_mock_users as benchmark
  on benchmark.user_id = link.benchmark_user_id
where context.auth_user_id = link.auth_user_id;

with scenario_seed (scenario_code, age_band, risk_profile, investment_horizon_years) as (
    values
        {scenario_values}
)
update public.mock_scenarios as scenario
set age_band = seed.age_band,
    risk_profile = seed.risk_profile,
    investment_horizon_years = seed.investment_horizon_years,
    updated_at = now()
from scenario_seed as seed
where scenario.code = seed.scenario_code;

with account_link (scenario_code, account_type, benchmark_account_id, balance_krw) as (
    values
        {account_values}
)
update public.mock_accounts as account
set benchmark_account_id = benchmark.account_id,
    balance_krw = link.balance_krw
from account_link as link
join public.mock_scenarios as scenario on scenario.code = link.scenario_code
left join public.benchmark_mock_accounts as benchmark
  on benchmark.account_id = link.benchmark_account_id
where account.scenario_id = scenario.id
  and account.account_type = link.account_type
  and (benchmark.account_id is not null or not exists (
      select 1 from public.benchmark_mock_accounts
  ));

delete from public.mock_holdings as holding
using public.mock_accounts as account, public.mock_scenarios as scenario
where holding.account_id = account.id
  and account.scenario_id = scenario.id
  and scenario.code in ({", ".join(_quote(item["scenario_code"]) for item in scenarios)});

with holding_seed (
    scenario_code, account_type, asset_class_code, instrument_name,
    market_value_krw, risk_treatment, statutory_exception, etf_isu_code
) as (
    values
        {holding_values}
)
insert into public.mock_holdings (
    account_id, asset_class_id, instrument_name, market_value_krw,
    risk_treatment, statutory_exception, etf_isu_code
)
select
    account.id, asset.id, seed.instrument_name, seed.market_value_krw,
    seed.risk_treatment, seed.statutory_exception, seed.etf_isu_code
from holding_seed as seed
join public.mock_scenarios as scenario on scenario.code = seed.scenario_code
join public.mock_accounts as account
  on account.scenario_id = scenario.id
 and account.account_type = seed.account_type
join public.asset_classes as asset on asset.code = seed.asset_class_code;
""".strip()


def main() -> None:
    sync_sql = _sync_sql()
    migration_sql = f"""-- Unify the 10k benchmark contract and the six detailed demo customers.

alter table public.benchmark_mock_users
    add column if not exists pension_savings_contribution_krw text not null default '0',
    add column if not exists irp_contribution_krw text not null default '0';

with contribution as (
    select
        user_id,
        coalesce(sum(annual_contribution_krw::numeric) filter (
            where account_type = 'PENSION_SAVINGS_FUND'
        ), 0) as pension_savings_contribution_krw,
        coalesce(sum(annual_contribution_krw::numeric) filter (
            where account_type = 'IRP'
        ), 0) as irp_contribution_krw
    from public.benchmark_mock_accounts
    group by user_id
)
update public.benchmark_mock_users as benchmark
set pension_savings_contribution_krw = contribution.pension_savings_contribution_krw::text,
    irp_contribution_krw = contribution.irp_contribution_krw::text
from contribution
where benchmark.user_id = contribution.user_id;

alter table public.demo_user_financial_context
    add column if not exists benchmark_user_id text
        references public.benchmark_mock_users(user_id) on delete restrict;

create unique index if not exists demo_user_financial_context_benchmark_user_id_uidx
    on public.demo_user_financial_context (benchmark_user_id)
    where benchmark_user_id is not null;

alter table public.mock_accounts
    add column if not exists benchmark_account_id text
        references public.benchmark_mock_accounts(account_id) on delete restrict;

create unique index if not exists mock_accounts_benchmark_account_id_uidx
    on public.mock_accounts (benchmark_account_id)
    where benchmark_account_id is not null;

{sync_sql}

do $$
declare
    benchmark_count integer;
begin
    select count(*) into benchmark_count from public.benchmark_mock_users;
    if benchmark_count > 0 then
        if (select count(*) from public.demo_user_financial_context where benchmark_user_id is not null) <> 6 then
            raise exception 'expected six linked demo customers';
        end if;
        if (select count(*) from public.mock_accounts where benchmark_account_id is not null) <> 13 then
            raise exception 'expected thirteen linked demo accounts';
        end if;
        if exists (
            select 1 from public.benchmark_mock_users
            where pension_savings_contribution_krw::numeric + irp_contribution_krw::numeric > 18000000
        ) then
            raise exception 'personal-pension annual contribution limit exceeded';
        end if;
    end if;
    if exists (
        select 1
        from public.mock_accounts as account
        join public.mock_scenarios as scenario on scenario.id = account.scenario_id
        left join public.mock_holdings as holding on holding.account_id = account.id
        where scenario.code in ('dc_dormant','tax_contribution_uninvested','overlap_risk_concentration','young_retirement_distance','family_budget_pressure','pension_payout_transition')
        group by account.id
        having sum(holding.market_value_krw) <> account.balance_krw
    ) then
        raise exception 'detailed demo holdings do not equal account balances';
    end if;
    if not exists (
        select 1 from public.mock_holdings as holding
        join public.mock_accounts as account on account.id = holding.account_id
        join public.mock_scenarios as scenario on scenario.id = account.scenario_id
        where scenario.code in ('dc_dormant','tax_contribution_uninvested','overlap_risk_concentration','young_retirement_distance','family_budget_pressure','pension_payout_transition')
          and holding.instrument_name like 'KODEX %'
    ) then
        raise exception 'KODEX must remain represented in demo portfolios';
    end if;
    if exists (select 1 from public.etf_dataset_versions where status = 'ready') then
        if exists (
            select 1
            from public.mock_holdings as holding
            join public.mock_accounts as account on account.id = holding.account_id
            join public.mock_scenarios as scenario on scenario.id = account.scenario_id
            where scenario.code in ('dc_dormant','tax_contribution_uninvested','overlap_risk_concentration','young_retirement_distance','family_budget_pressure','pension_payout_transition')
              and holding.etf_isu_code is not null
              and not exists (
                  select 1
                  from public.etf_universe_products as product
                  where product.version_id = (
                      select max(id) from public.etf_dataset_versions where status = 'ready'
                  )
                    and product.account_type = account.account_type
                    and product.isu_code = holding.etf_isu_code
                    and (product.payload -> 'account_eligibility' ->> 'eligible')::boolean
              )
        ) then
            raise exception 'demo ETF is not eligible for its pension account';
        end if;
        if exists (
            select holding.etf_isu_code
            from public.mock_holdings as holding
            join public.mock_accounts as account on account.id = holding.account_id
            join public.mock_scenarios as scenario on scenario.id = account.scenario_id
            where holding.etf_isu_code is not null
              and scenario.code in ('dc_dormant','tax_contribution_uninvested','overlap_risk_concentration','young_retirement_distance','family_budget_pressure','pension_payout_transition')
              and not exists (
                  select 1
                  from public.etf_return_histories as history
                  where history.version_id = (
                      select max(id) from public.etf_dataset_versions where status = 'ready'
                  )
                    and history.isu_code = holding.etf_isu_code
                  group by history.isu_code
                  having count(*) = 253
              )
        ) then
            raise exception 'demo ETF requires exactly 253 return observations';
        end if;
    end if;
    if not exists (
        select 1
        from public.mock_holdings as holding
        where holding.instrument_name like 'KODEX %'
    ) or not exists (
        select 1
        from public.mock_holdings as holding
        where holding.instrument_name like 'TIGER %'
    ) or not exists (
        select 1 from public.mock_holdings where instrument_name like 'ACE %'
    ) or not exists (
        select 1 from public.mock_holdings where instrument_name like 'RISE %'
    ) or not exists (
        select 1 from public.mock_holdings where instrument_name like 'SOL %'
    ) or not exists (
        select 1 from public.mock_holdings where instrument_name like 'HANARO %'
    ) then
        raise exception 'six required ETF issuers are not represented';
    end if;
end
$$;

comment on column public.benchmark_mock_users.pension_savings_contribution_krw is
    '당해연도 연금저축펀드 납입액. 개인 IRP와 합산하여 연 1,800만원 이하';
comment on column public.benchmark_mock_users.irp_contribution_krw is
    '당해연도 개인 IRP 납입액. 연금저축펀드와 합산하여 연 1,800만원 이하';
comment on column public.demo_user_financial_context.benchmark_user_id is
    '대표 고객이 상세화한 1만명 기준 고객 행';
comment on column public.mock_accounts.benchmark_account_id is
    '대표 고객 상세 계좌의 1만명 기준 계좌 행';
"""
    MIGRATION.write_text(migration_sql, encoding="utf-8")

    seed_text = SEED.read_text(encoding="utf-8")
    if SEED_START in seed_text:
        seed_text = seed_text.split(SEED_START, 1)[0].rstrip() + "\n"
    seed_tail = f"\n{SEED_START}\n{sync_sql}\n{SEED_END}\n"
    SEED.write_text(seed_text + seed_tail, encoding="utf-8")
    print(f"rendered {MIGRATION.name} and seed sync")


if __name__ == "__main__":
    main()
