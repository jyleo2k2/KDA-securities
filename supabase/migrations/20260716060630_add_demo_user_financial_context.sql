-- Link the six synthetic Auth users to their database-backed demo context.
-- Balances stay authoritative in mock_accounts. Missing income and current-year
-- contribution values remain NULL in storage and are normalized to KRW 0 by
-- the FastAPI read model, per the approved demo rule.

create table public.demo_user_financial_context (
    auth_user_id uuid primary key references auth.users(id) on delete cascade,
    scenario_id bigint not null
        references public.mock_scenarios(id) on delete restrict,
    nickname text not null check (length(btrim(nickname)) > 0),
    representative_age smallint not null
        check (representative_age between 18 and 120),
    customer_context text not null check (length(btrim(customer_context)) > 0),
    tax_year smallint not null default 2026 check (tax_year = 2026),
    gross_salary_krw numeric(20, 0) check (gross_salary_krw >= 0),
    comprehensive_income_krw numeric(20, 0)
        check (comprehensive_income_krw >= 0),
    pension_savings_contribution_krw numeric(20, 0)
        check (pension_savings_contribution_krw >= 0),
    irp_contribution_krw numeric(20, 0)
        check (irp_contribution_krw >= 0),
    as_of_date date not null default current_date,
    data_kind text not null default 'mock' check (data_kind = 'mock'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (
        gross_salary_krw is null
        or comprehensive_income_krw is null
    )
);

create index demo_user_financial_context_scenario_idx
    on public.demo_user_financial_context (scenario_id);

alter table public.demo_user_financial_context enable row level security;

create policy demo_user_financial_context_select_own
on public.demo_user_financial_context
for select
to authenticated
using ((select auth.uid()) = auth_user_id);

revoke all privileges on table public.demo_user_financial_context
from public, anon, authenticated;

grant all privileges on table public.demo_user_financial_context
to service_role;

with demo_seed (
    auth_user_id, scenario_code, nickname, representative_age, customer_context
) as (
    values
        (
            '0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01'::uuid,
            'dc_dormant',
            '박준호(가상)',
            46::smallint,
            '회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객'
        ),
        (
            '1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02'::uuid,
            'tax_contribution_uninvested',
            '이서연(가상)',
            34::smallint,
            '세액공제를 위해 납입했지만 IRP·연금저축 자금을 운용하지 않은 고객'
        ),
        (
            '2f5cae61-5f80-4040-b3c2-9f33c4d93e03'::uuid,
            'overlap_risk_concentration',
            '정민재(가상)',
            32::smallint,
            '여러 연금계좌에 같은 위험자산이 중복된 편중형 고객'
        ),
        (
            '306dbf72-6091-4141-84d3-a044d5ea4f04'::uuid,
            'young_retirement_distance',
            '김하린(가상)',
            29::smallint,
            '노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 고객'
        ),
        (
            '417ec083-71a2-4242-95e4-b155e6fb5005'::uuid,
            'family_budget_pressure',
            '최지훈(가상)',
            47::smallint,
            '자녀·주거비로 납입은 빠듯하지만 노후 준비를 걱정하기 시작한 고객'
        ),
        (
            '528fd194-82b3-4343-a6f5-c266f70c6106'::uuid,
            'pension_payout_transition',
            '윤정희(가상)',
            60::smallint,
            '연금 수령을 시작했거나 수령 직전이라 인출·세금·안정성을 검토하는 고객'
        )
)
insert into public.demo_user_financial_context (
    auth_user_id,
    scenario_id,
    nickname,
    representative_age,
    customer_context,
    tax_year,
    as_of_date
)
select
    seed.auth_user_id,
    scenario.id,
    seed.nickname,
    seed.representative_age,
    seed.customer_context,
    2026,
    date '2026-07-16'
from demo_seed as seed
join auth.users as auth_user on auth_user.id = seed.auth_user_id
join public.mock_scenarios as scenario on scenario.code = seed.scenario_code
on conflict (auth_user_id) do update set
    scenario_id = excluded.scenario_id,
    nickname = excluded.nickname,
    representative_age = excluded.representative_age,
    customer_context = excluded.customer_context,
    tax_year = excluded.tax_year,
    as_of_date = excluded.as_of_date,
    data_kind = 'mock',
    updated_at = now();
