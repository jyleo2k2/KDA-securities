-- Statistical benchmark data only. These rows are not Auth users or real accounts.
create table public.benchmark_mock_users (
  user_id text primary key, age text not null, age_group text not null, employment_type text not null,
  gross_salary_krw text, comprehensive_income_krw text, tax_credit_income_basis text not null,
  tax_credit_income_amount_krw text not null, tax_year text not null, pension_tax_credit_rate_pct text not null,
  total_tax_credit_eligible_contribution_krw text not null, estimated_pension_tax_credit_krw text not null,
  planned_pension_start_age text not null, planned_receipt_years text not null,
  planned_annual_total_pension_receipt_krw text not null, planned_annual_personal_pension_receipt_krw text not null,
  planned_low_rate_pension_tax_pct text not null, planned_receipt_tax_treatment text not null,
  risk_profile text not null, preferred_management_type text not null, retirement_fund_attitude text not null,
  investment_readiness text not null, payout_preference text not null, primary_outside_asset text not null,
  mock_scenario text not null, data_kind text not null check (data_kind = 'MOCK'), source_ids text not null
);

create table public.benchmark_mock_accounts (
  account_id text primary key, user_id text not null references public.benchmark_mock_users(user_id) on delete cascade,
  account_type text not null, balance_krw text not null, monthly_contribution_krw text not null,
  annual_contribution_krw text not null, contribution_status text not null, contribution_frequency text not null,
  account_open_year text not null, contribution_years text not null, planned_contribution_years_at_receipt text not null,
  pension_receipt_eligibility text not null, tax_credit_eligible_contribution_krw text not null,
  estimated_tax_credit_krw text not null, planned_annual_pension_receipt_krw text not null,
  planned_receipt_tax_treatment text not null, risky_asset_ratio text not null, safe_asset_ratio text not null,
  cash_ratio text not null, trailing_12m_return_pct text not null, return_period_end text not null,
  data_kind text not null check (data_kind = 'MOCK'), source_ids text not null
);

create table public.benchmark_mock_holdings (
  account_id text not null references public.benchmark_mock_accounts(account_id) on delete cascade,
  asset_class text not null, weight text not null, amount_krw text not null,
  data_kind text not null check (data_kind = 'MOCK'), source_ids text not null,
  primary key (account_id, asset_class)
);

create index benchmark_mock_accounts_user_id_idx on public.benchmark_mock_accounts(user_id);
create index benchmark_mock_users_scenario_idx on public.benchmark_mock_users(mock_scenario);

alter table public.benchmark_mock_users enable row level security;
alter table public.benchmark_mock_accounts enable row level security;
alter table public.benchmark_mock_holdings enable row level security;
revoke all on public.benchmark_mock_users, public.benchmark_mock_accounts, public.benchmark_mock_holdings from anon, authenticated;
grant select, insert, update, delete on public.benchmark_mock_users, public.benchmark_mock_accounts, public.benchmark_mock_holdings to service_role;
