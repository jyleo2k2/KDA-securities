-- Unify the 10k benchmark contract and the six detailed demo customers.

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

with user_link (auth_user_id, scenario_code, benchmark_user_id, representative_age) as (
    values
        ('0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01'::uuid, 'dc_dormant', 'USR09660', 34::smallint),
        ('1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02'::uuid, 'tax_contribution_uninvested', 'USR00540', 48::smallint),
        ('2f5cae61-5f80-4040-b3c2-9f33c4d93e03'::uuid, 'overlap_risk_concentration', 'USR03419', 42::smallint),
        ('306dbf72-6091-4141-84d3-a044d5ea4f04'::uuid, 'young_retirement_distance', 'USR08633', 29::smallint),
        ('417ec083-71a2-4242-95e4-b155e6fb5005'::uuid, 'family_budget_pressure', 'USR00109', 47::smallint),
        ('528fd194-82b3-4343-a6f5-c266f70c6106'::uuid, 'pension_payout_transition', 'USR08609', 55::smallint)
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
        ('dc_dormant', '30대', 'conservative', 26::smallint),
        ('tax_contribution_uninvested', '40대', 'balanced', 17::smallint),
        ('overlap_risk_concentration', '40대', 'growth', 18::smallint),
        ('young_retirement_distance', '20~39세', 'balanced', 26::smallint),
        ('family_budget_pressure', '40~54세', 'balanced', 13::smallint),
        ('pension_payout_transition', '55세 이상', 'balanced', 5::smallint)
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
        ('family_budget_pressure', 'dc', 'ACC000187', 73980000::numeric),
        ('family_budget_pressure', 'irp', 'ACC000188', 8070000::numeric),
        ('family_budget_pressure', 'pension_savings', 'ACC000189', 6610000::numeric),
        ('tax_contribution_uninvested', 'irp', 'ACC000907', 37700000::numeric),
        ('tax_contribution_uninvested', 'pension_savings', 'ACC000908', 2980000::numeric),
        ('overlap_risk_concentration', 'dc', 'ACC005722', 123940000::numeric),
        ('overlap_risk_concentration', 'irp', 'ACC005723', 21990000::numeric),
        ('overlap_risk_concentration', 'pension_savings', 'ACC005724', 3400000::numeric),
        ('pension_payout_transition', 'irp', 'ACC014528', 153720000::numeric),
        ('pension_payout_transition', 'pension_savings', 'ACC014529', 3710000::numeric),
        ('young_retirement_distance', 'dc', 'ACC014566', 22690000::numeric),
        ('young_retirement_distance', 'pension_savings', 'ACC014567', 520000::numeric),
        ('dc_dormant', 'dc', 'ACC016306', 60980000::numeric)
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
  and scenario.code in ('dc_dormant', 'tax_contribution_uninvested', 'overlap_risk_concentration', 'young_retirement_distance', 'family_budget_pressure', 'pension_payout_transition');

with holding_seed (
    scenario_code, account_type, asset_class_code, instrument_name,
    market_value_krw, risk_treatment, statutory_exception, etf_isu_code
) as (
    values
        ('dc_dormant', 'dc', 'domestic_equity', 'HANARO 200TR', 733217::numeric, 'general_risky', null, '332930'),
        ('dc_dormant', 'dc', 'domestic_equity', 'SOL AI반도체소부장', 314236::numeric, 'general_risky', null, '455850'),
        ('dc_dormant', 'dc', 'global_equity', 'ACE 미국S&P500', 896150::numeric, 'general_risky', null, '360200'),
        ('dc_dormant', 'dc', 'global_equity', 'KODEX 미국S&P500', 384064::numeric, 'general_risky', null, '379800'),
        ('dc_dormant', 'dc', 'bond', 'SOL 종합채권(AA-이상)액티브', 14142969::numeric, 'capital_preservation', null, '436140'),
        ('dc_dormant', 'dc', 'deposit', '원리금보장 상품', 33000242::numeric, 'capital_preservation', null, null),
        ('dc_dormant', 'dc', 'cash', '현금성 자산', 11509122::numeric, 'capital_preservation', null, null),
        ('tax_contribution_uninvested', 'irp', 'domestic_equity', 'SOL 200 Top10', 700628::numeric, 'general_risky', null, '411540'),
        ('tax_contribution_uninvested', 'irp', 'domestic_equity', 'RISE 2차전지TOP10', 300269::numeric, 'general_risky', null, '465330'),
        ('tax_contribution_uninvested', 'irp', 'global_equity', 'RISE 미국S&P500(H)', 467076::numeric, 'general_risky', null, '453330'),
        ('tax_contribution_uninvested', 'irp', 'global_equity', 'SOL 글로벌AI반도체탑픽액티브', 200176::numeric, 'general_risky', null, '423170'),
        ('tax_contribution_uninvested', 'irp', 'bond', 'RISE 종합채권(A-이상)액티브', 4682906::numeric, 'capital_preservation', null, '385540'),
        ('tax_contribution_uninvested', 'irp', 'deposit', '원리금보장 상품', 10926817::numeric, 'capital_preservation', null, null),
        ('tax_contribution_uninvested', 'irp', 'cash', '현금성 자산', 20422128::numeric, 'capital_preservation', null, null),
        ('tax_contribution_uninvested', 'pension_savings', 'domestic_equity', 'HANARO K고배당', 136220::numeric, 'general_risky', null, '322410'),
        ('tax_contribution_uninvested', 'pension_savings', 'domestic_equity', 'TIGER 헬스케어', 58380::numeric, 'general_risky', null, '143860'),
        ('tax_contribution_uninvested', 'pension_savings', 'global_equity', 'HANARO 미국S&P500', 90812::numeric, 'general_risky', null, '432840'),
        ('tax_contribution_uninvested', 'pension_savings', 'global_equity', 'TIGER S&P글로벌헬스케어(합성)', 38919::numeric, 'general_risky', null, '248270'),
        ('tax_contribution_uninvested', 'pension_savings', 'bond', 'ACE 종합채권(AA-이상)액티브', 897439::numeric, 'capital_preservation', null, '356540'),
        ('tax_contribution_uninvested', 'pension_savings', 'cash', '현금성 자산', 1758230::numeric, 'capital_preservation', null, null),
        ('overlap_risk_concentration', 'dc', 'domestic_equity', 'HANARO K고배당', 32851437::numeric, 'general_risky', null, '322410'),
        ('overlap_risk_concentration', 'dc', 'domestic_equity', 'TIGER 헬스케어', 14079188::numeric, 'general_risky', null, '143860'),
        ('overlap_risk_concentration', 'dc', 'global_equity', 'HANARO 미국S&P500', 21901016::numeric, 'general_risky', null, '432840'),
        ('overlap_risk_concentration', 'dc', 'global_equity', 'TIGER S&P글로벌헬스케어(합성)', 9386150::numeric, 'general_risky', null, '248270'),
        ('overlap_risk_concentration', 'dc', 'bond', 'ACE 종합채권(AA-이상)액티브', 12648325::numeric, 'capital_preservation', null, '356540'),
        ('overlap_risk_concentration', 'dc', 'deposit', '원리금보장 상품', 29512841::numeric, 'capital_preservation', null, null),
        ('overlap_risk_concentration', 'dc', 'cash', '현금성 자산', 3561043::numeric, 'capital_preservation', null, null),
        ('overlap_risk_concentration', 'irp', 'domestic_equity', 'ACE AI반도체TOP3+', 6465060::numeric, 'general_risky', null, '469150'),
        ('overlap_risk_concentration', 'irp', 'domestic_equity', 'HANARO 농업융복합산업', 2770740::numeric, 'general_risky', null, '314700'),
        ('overlap_risk_concentration', 'irp', 'global_equity', 'ACE 미국S&P500', 4310040::numeric, 'general_risky', null, '360200'),
        ('overlap_risk_concentration', 'irp', 'global_equity', 'RISE 미국반도체NYSE', 1847160::numeric, 'general_risky', null, '469060'),
        ('overlap_risk_concentration', 'irp', 'bond', 'HANARO 종합채권(AA-이상)액티브', 1904400::numeric, 'capital_preservation', null, '461500'),
        ('overlap_risk_concentration', 'irp', 'deposit', '원리금보장 상품', 4443585::numeric, 'capital_preservation', null, null),
        ('overlap_risk_concentration', 'irp', 'cash', '현금성 자산', 249015::numeric, 'capital_preservation', null, null),
        ('overlap_risk_concentration', 'pension_savings', 'domestic_equity', 'HANARO 200TR', 904938::numeric, 'general_risky', null, '332930'),
        ('overlap_risk_concentration', 'pension_savings', 'domestic_equity', 'SOL 금융지주플러스고배당', 387830::numeric, 'general_risky', null, '484880'),
        ('overlap_risk_concentration', 'pension_savings', 'global_equity', 'TIGER 미국배당다우존스', 603292::numeric, 'general_risky', null, '458730'),
        ('overlap_risk_concentration', 'pension_savings', 'global_equity', 'ACE 글로벌반도체TOP4 Plus', 258554::numeric, 'general_risky', null, '446770'),
        ('overlap_risk_concentration', 'pension_savings', 'bond', 'SOL 종합채권(AA-이상)액티브', 1097935::numeric, 'capital_preservation', null, '436140'),
        ('overlap_risk_concentration', 'pension_savings', 'cash', '현금성 자산', 147451::numeric, 'capital_preservation', null, null),
        ('young_retirement_distance', 'dc', 'domestic_equity', 'ACE AI반도체TOP3+', 2198525::numeric, 'general_risky', null, '469150'),
        ('young_retirement_distance', 'dc', 'domestic_equity', 'HANARO 농업융복합산업', 942225::numeric, 'general_risky', null, '314700'),
        ('young_retirement_distance', 'dc', 'global_equity', 'ACE 미국S&P500', 4082963::numeric, 'general_risky', null, '360200'),
        ('young_retirement_distance', 'dc', 'global_equity', 'RISE 미국반도체NYSE', 1749842::numeric, 'general_risky', null, '469060'),
        ('young_retirement_distance', 'dc', 'bond', 'HANARO 종합채권(AA-이상)액티브', 3839216::numeric, 'capital_preservation', null, '461500'),
        ('young_retirement_distance', 'dc', 'deposit', '원리금보장 상품', 8958171::numeric, 'capital_preservation', null, null),
        ('young_retirement_distance', 'dc', 'cash', '현금성 자산', 919058::numeric, 'capital_preservation', null, null),
        ('young_retirement_distance', 'pension_savings', 'domestic_equity', 'HANARO 200TR', 79661::numeric, 'general_risky', null, '332930'),
        ('young_retirement_distance', 'pension_savings', 'domestic_equity', 'SOL 금융지주플러스고배당', 34140::numeric, 'general_risky', null, '484880'),
        ('young_retirement_distance', 'pension_savings', 'global_equity', 'TIGER 미국배당다우존스', 147942::numeric, 'general_risky', null, '458730'),
        ('young_retirement_distance', 'pension_savings', 'global_equity', 'ACE 글로벌반도체TOP4 Plus', 63404::numeric, 'general_risky', null, '446770'),
        ('young_retirement_distance', 'pension_savings', 'bond', 'SOL 종합채권(AA-이상)액티브', 188851::numeric, 'capital_preservation', null, '436140'),
        ('young_retirement_distance', 'pension_savings', 'cash', '현금성 자산', 6002::numeric, 'capital_preservation', null, null),
        ('family_budget_pressure', 'dc', 'domestic_equity', 'HANARO 200TR', 11152530::numeric, 'general_risky', null, '332930'),
        ('family_budget_pressure', 'dc', 'domestic_equity', 'SOL 금융지주플러스고배당', 4779655::numeric, 'general_risky', null, '484880'),
        ('family_budget_pressure', 'dc', 'global_equity', 'TIGER 미국배당다우존스', 7435020::numeric, 'general_risky', null, '458730'),
        ('family_budget_pressure', 'dc', 'global_equity', 'ACE 글로벌반도체TOP4 Plus', 3186437::numeric, 'general_risky', null, '446770'),
        ('family_budget_pressure', 'dc', 'bond', 'SOL 종합채권(AA-이상)액티브', 13305673::numeric, 'capital_preservation', null, '436140'),
        ('family_budget_pressure', 'dc', 'deposit', '원리금보장 상품', 31046595::numeric, 'capital_preservation', null, null),
        ('family_budget_pressure', 'dc', 'cash', '현금성 자산', 3074090::numeric, 'capital_preservation', null, null),
        ('family_budget_pressure', 'irp', 'domestic_equity', 'HANARO 200TR', 1195498::numeric, 'general_risky', null, '332930'),
        ('family_budget_pressure', 'irp', 'domestic_equity', 'SOL AI반도체소부장', 512356::numeric, 'general_risky', null, '455850'),
        ('family_budget_pressure', 'irp', 'global_equity', 'HANARO 미국S&P500', 796995::numeric, 'general_risky', null, '432840'),
        ('family_budget_pressure', 'irp', 'global_equity', 'SOL 미국AI반도체칩메이커', 341569::numeric, 'general_risky', null, '479620'),
        ('family_budget_pressure', 'irp', 'bond', 'RISE 종합채권(A-이상)액티브', 1477706::numeric, 'capital_preservation', null, '385540'),
        ('family_budget_pressure', 'irp', 'deposit', '원리금보장 상품', 3447972::numeric, 'capital_preservation', null, null),
        ('family_budget_pressure', 'irp', 'cash', '현금성 자산', 297904::numeric, 'capital_preservation', null, null),
        ('family_budget_pressure', 'pension_savings', 'domestic_equity', 'SOL 200 Top10', 1993372::numeric, 'general_risky', null, '411540'),
        ('family_budget_pressure', 'pension_savings', 'domestic_equity', 'RISE 2차전지TOP10', 854302::numeric, 'general_risky', null, '465330'),
        ('family_budget_pressure', 'pension_savings', 'global_equity', 'ACE 미국S&P500', 1328916::numeric, 'general_risky', null, '360200'),
        ('family_budget_pressure', 'pension_savings', 'global_equity', 'KODEX 미국S&P500', 569535::numeric, 'general_risky', null, '379800'),
        ('family_budget_pressure', 'pension_savings', 'bond', 'ACE 종합채권(AA-이상)액티브', 1555009::numeric, 'capital_preservation', null, '356540'),
        ('family_budget_pressure', 'pension_savings', 'cash', '현금성 자산', 308866::numeric, 'capital_preservation', null, null),
        ('pension_payout_transition', 'irp', 'domestic_equity', 'HANARO 200TR', 3710832::numeric, 'general_risky', null, '332930'),
        ('pension_payout_transition', 'irp', 'domestic_equity', 'SOL AI반도체소부장', 1590356::numeric, 'general_risky', null, '455850'),
        ('pension_payout_transition', 'irp', 'global_equity', 'HANARO 미국S&P500', 1590387::numeric, 'general_risky', null, '432840'),
        ('pension_payout_transition', 'irp', 'global_equity', 'SOL 미국AI반도체칩메이커', 681595::numeric, 'general_risky', null, '479620'),
        ('pension_payout_transition', 'irp', 'bond', 'RISE 종합채권(A-이상)액티브', 16235599::numeric, 'capital_preservation', null, '385540'),
        ('pension_payout_transition', 'irp', 'deposit', '원리금보장 상품', 37883218::numeric, 'capital_preservation', null, null),
        ('pension_payout_transition', 'irp', 'cash', '현금성 자산', 92028013::numeric, 'capital_preservation', null, null),
        ('pension_payout_transition', 'pension_savings', 'domestic_equity', 'SOL 200 Top10', 185099::numeric, 'general_risky', null, '411540'),
        ('pension_payout_transition', 'pension_savings', 'domestic_equity', 'RISE 2차전지TOP10', 79328::numeric, 'general_risky', null, '465330'),
        ('pension_payout_transition', 'pension_savings', 'global_equity', 'ACE 미국S&P500', 79328::numeric, 'general_risky', null, '360200'),
        ('pension_payout_transition', 'pension_savings', 'global_equity', 'KODEX 미국S&P500', 33998::numeric, 'general_risky', null, '379800'),
        ('pension_payout_transition', 'pension_savings', 'bond', 'ACE 종합채권(AA-이상)액티브', 1403408::numeric, 'capital_preservation', null, '356540'),
        ('pension_payout_transition', 'pension_savings', 'cash', '현금성 자산', 1928839::numeric, 'capital_preservation', null, null)
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
