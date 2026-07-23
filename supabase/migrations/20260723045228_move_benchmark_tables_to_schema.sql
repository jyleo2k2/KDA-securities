create schema if not exists benchmark;

revoke all on schema benchmark from public, anon, authenticated;
grant usage on schema benchmark to service_role;

alter table public.benchmark_mock_users set schema benchmark;
alter table public.benchmark_mock_accounts set schema benchmark;
alter table public.benchmark_mock_holdings set schema benchmark;

create view public.benchmark_mock_users
with (security_invoker = true) as
select * from benchmark.benchmark_mock_users;

create view public.benchmark_mock_accounts
with (security_invoker = true) as
select * from benchmark.benchmark_mock_accounts;

create view public.benchmark_mock_holdings
with (security_invoker = true) as
select * from benchmark.benchmark_mock_holdings;

revoke all on public.benchmark_mock_users,
    public.benchmark_mock_accounts,
    public.benchmark_mock_holdings from public, anon, authenticated;

grant select on public.benchmark_mock_users,
    public.benchmark_mock_accounts,
    public.benchmark_mock_holdings to service_role;
