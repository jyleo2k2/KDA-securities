"""Render the common-account seed for the six synthetic customer scenarios."""

# ruff: noqa: E501 -- long lines are intentional inside generated SQL literals.

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"
SEED = ROOT / "supabase" / "seed.sql"
SEED_START = "-- BEGIN GENERATED DEMO CUSTOMER CONTRACT V2"
SEED_END = "-- END GENERATED DEMO CUSTOMER CONTRACT V2"


def _quote(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"

def _common_account_sync_sql() -> str:
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    scenarios = json.loads(
        (MOCK_DIR / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )
    user_values = ",\n        ".join(
        f"({_quote(item['auth_user_id'])}::uuid, {_quote(item['benchmark_user_id'])}, {item['representative_age']}::smallint)"
        for item in manifest
    )
    scenario_values = ",\n        ".join(
        f"({_quote(item['scenario_code'])}, {_quote(item['age_band'])}, {_quote(item['risk_profile'])}, {item['investment_horizon_years']}::smallint)"
        for item in scenarios
    )
    account_rows = [
        (
            scenario["scenario_code"],
            account["account_type"],
            account["label"],
            sum(int(holding["amount_krw"]) for holding in account["holdings"]),
        )
        for scenario in scenarios
        for account in scenario["accounts"]
    ]
    holding_rows = [
        (
            scenario["scenario_code"],
            account["account_type"],
            account["label"],
            holding["asset_class_code"],
            holding["instrument_name"],
            holding["amount_krw"],
            holding["risk_treatment"],
            holding.get("statutory_exception"),
            holding.get("etf_isu_code"),
        )
        for scenario in scenarios
        for account in scenario["accounts"]
        for holding in account["holdings"]
    ]
    account_values = ",\n        ".join(
        "(" + ", ".join(
            (
                _quote(scenario_code),
                _quote(account_type),
                _quote(account_name),
                f"{balance_krw}::numeric",
            )
        ) + ")"
        for scenario_code, account_type, account_name, balance_krw in account_rows
    )
    holding_values = ",\n        ".join(
        "(" + ", ".join(
            (
                _quote(scenario_code),
                _quote(account_type),
                _quote(account_name),
                _quote(asset_class_code),
                _quote(instrument_name),
                f"{market_value_krw}::numeric",
                _quote(risk_treatment),
                _quote(statutory_exception),
                _quote(etf_isu_code),
            )
        ) + ")"
        for (
            scenario_code,
            account_type,
            account_name,
            asset_class_code,
            instrument_name,
            market_value_krw,
            risk_treatment,
            statutory_exception,
            etf_isu_code,
        ) in holding_rows
    )
    return f"""
with user_link (auth_user_id, benchmark_user_id, representative_age) as (
    values
        {user_values}
)
update public.demo_user_financial_context as context
set benchmark_user_id = link.benchmark_user_id,
    representative_age = link.representative_age,
    tax_year = 2026,
    gross_salary_krw = nullif(benchmark.gross_salary_krw, '')::numeric,
    comprehensive_income_krw = nullif(benchmark.comprehensive_income_krw, '')::numeric,
    pension_savings_contribution_krw = benchmark.pension_savings_contribution_krw::numeric,
    irp_contribution_krw = benchmark.irp_contribution_krw::numeric,
    updated_at = now()
from user_link as link
join benchmark.benchmark_mock_users as benchmark on benchmark.user_id = link.benchmark_user_id
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

with account_seed (scenario_code, account_type, account_name, market_value_krw) as (
    values
        {account_values}
)
insert into public.pension_accounts (
    id, owner_id, scenario_id, institution_id, account_type, account_name, data_kind, origin
)
select
    md5('mock-account:' || scenario.code || ':' || seed.account_type || ':' || seed.account_name)::uuid,
    null, scenario.id, null, seed.account_type, seed.account_name, 'mock', 'synthetic'
from account_seed as seed
join public.mock_scenarios as scenario on scenario.code = seed.scenario_code
on conflict (id) do update set
    owner_id = null,
    scenario_id = excluded.scenario_id,
    institution_id = null,
    account_type = excluded.account_type,
    account_name = excluded.account_name,
    data_kind = 'mock',
    origin = 'synthetic',
    updated_at = now();

with account_seed (scenario_code, account_type, account_name, market_value_krw) as (
    values
        {account_values}
)
insert into public.account_snapshots (
    id, account_id, as_of_date, contributed_principal_krw, market_value_krw, source_id, origin
)
select
    md5('mock-snapshot:' || scenario.code || ':' || seed.account_type || ':' || seed.account_name || ':2026-07-16')::uuid,
    md5('mock-account:' || scenario.code || ':' || seed.account_type || ':' || seed.account_name)::uuid,
    date '2026-07-16', null::numeric, seed.market_value_krw, null, 'synthetic'
from account_seed as seed
join public.mock_scenarios as scenario on scenario.code = seed.scenario_code
on conflict (id) do update set
    account_id = excluded.account_id,
    as_of_date = excluded.as_of_date,
    contributed_principal_krw = null,
    market_value_krw = excluded.market_value_krw,
    source_id = null,
    origin = 'synthetic';

with holding_seed (
    scenario_code, account_type, account_name, asset_class_code, raw_instrument_name,
    market_value_krw, risk_treatment, statutory_exception, etf_isu_code
) as (
    values
        {holding_values}
)
insert into public.account_holding_snapshots (
    id, snapshot_id, product_id, raw_instrument_name, etf_isu_code, asset_class_id,
    market_value_krw, risk_treatment, statutory_exception, source_id, origin
)
select
    md5('mock-holding:' || scenario.code || ':' || seed.account_type || ':' || seed.account_name || ':' || seed.raw_instrument_name || ':2026-07-16')::uuid,
    md5('mock-snapshot:' || scenario.code || ':' || seed.account_type || ':' || seed.account_name || ':2026-07-16')::uuid,
    null, seed.raw_instrument_name, seed.etf_isu_code, asset.id, seed.market_value_krw,
    seed.risk_treatment, seed.statutory_exception, null, 'synthetic'
from holding_seed as seed
join public.mock_scenarios as scenario on scenario.code = seed.scenario_code
join public.asset_classes as asset on asset.code = seed.asset_class_code
on conflict (id) do update set
    snapshot_id = excluded.snapshot_id,
    product_id = null,
    raw_instrument_name = excluded.raw_instrument_name,
    etf_isu_code = excluded.etf_isu_code,
    asset_class_id = excluded.asset_class_id,
    market_value_krw = excluded.market_value_krw,
    risk_treatment = excluded.risk_treatment,
    statutory_exception = excluded.statutory_exception,
    source_id = null,
    origin = 'synthetic';

do $$
begin
    if (select count(*) from public.pension_accounts where data_kind = 'mock' and origin = 'synthetic') <> 13 then
        raise exception 'expected 13 seeded mock accounts';
    end if;
    if (select count(*) from public.account_holding_snapshots as holding
        join public.account_snapshots as snapshot on snapshot.id = holding.snapshot_id
        join public.pension_accounts as account on account.id = snapshot.account_id
        where account.data_kind = 'mock' and account.origin = 'synthetic'
          and snapshot.as_of_date = date '2026-07-16') <> 86 then
        raise exception 'expected 86 seeded mock holdings';
    end if;
    if exists (
        select 1
        from public.account_snapshots as snapshot
        join public.pension_accounts as account on account.id = snapshot.account_id
        left join public.account_holding_snapshots as holding on holding.snapshot_id = snapshot.id
        where account.data_kind = 'mock' and account.origin = 'synthetic'
          and snapshot.as_of_date = date '2026-07-16'
        group by snapshot.id, snapshot.market_value_krw
        having snapshot.market_value_krw is distinct from coalesce(sum(holding.market_value_krw), 0)
    ) then
        raise exception 'seeded common holding total does not match snapshot';
    end if;
end
$$;
""".strip()


def main() -> None:
    seed_text = SEED.read_text(encoding="utf-8")
    prefix, existing_tail = seed_text.split(SEED_START, 1)
    _, suffix = existing_tail.split(SEED_END, 1)
    seed_tail = f"\n{SEED_START}\n{_common_account_sync_sql()}\n{SEED_END}\n"
    SEED.write_text(prefix.rstrip() + seed_tail + suffix.lstrip("\n"), encoding="utf-8")
    print(f"rendered common account seed sync from {MOCK_DIR.name}")


if __name__ == "__main__":
    main()
