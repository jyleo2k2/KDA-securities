-- Add three lifecycle personas alongside the existing behavior-based scenarios.
-- Auth credentials are provisioned separately through the server-only Admin API.

insert into public.mock_scenarios (
    code, name, description, age_band, risk_profile, investment_horizon_years
)
values
    (
        'young_retirement_distance',
        '연금이 멀게 느껴지는 청년층',
        '20~39세로 노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 설명용 시나리오',
        '20~39세',
        'balanced',
        35
    ),
    (
        'family_budget_pressure',
        '가계지출로 납입이 빠듯한 중년층',
        '40~54세로 자녀·주거비 때문에 추가 납입은 빠듯하지만 노후 준비를 걱정하기 시작한 설명용 시나리오',
        '40~54세',
        'balanced',
        13
    ),
    (
        'pension_payout_transition',
        '연금 수령을 시작하는 55세 이상',
        '55세 이상으로 연금 수령을 시작했거나 수령 직전이라 수령 기간·세금·자산 안정성을 실제로 검토하는 설명용 시나리오',
        '55세 이상',
        'conservative',
        1
    )
on conflict (code) do update set
    name = excluded.name,
    description = excluded.description,
    age_band = excluded.age_band,
    risk_profile = excluded.risk_profile,
    investment_horizon_years = excluded.investment_horizon_years,
    is_active = true,
    updated_at = now();

with account_seed (scenario_code, account_type, label, balance_krw) as (
    values
        ('young_retirement_distance', 'dc', '초기 직장 DC', 18000000::numeric),
        ('young_retirement_distance', 'pension_savings', '소액 연금저축펀드', 3600000::numeric),
        ('family_budget_pressure', 'dc', '회사 DC', 65000000::numeric),
        ('family_budget_pressure', 'irp', '개인 IRP', 12000000::numeric),
        ('family_budget_pressure', 'pension_savings', '연금저축펀드', 9000000::numeric),
        ('pension_payout_transition', 'irp', '수령기 IRP', 110000000::numeric),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 45000000::numeric)
)
insert into public.mock_accounts (scenario_id, account_type, label, balance_krw)
select ms.id, account_seed.account_type, account_seed.label, account_seed.balance_krw
from account_seed
join public.mock_scenarios as ms on ms.code = account_seed.scenario_code
on conflict (scenario_id, account_type, label) do update set
    balance_krw = excluded.balance_krw;

with holding_seed (
    scenario_code, account_type, account_label, asset_code, instrument_name,
    market_value_krw, risk_treatment, statutory_exception
) as (
    values
        ('young_retirement_distance', 'dc', '초기 직장 DC', 'deposit', '초기 DC 원리금보장 모형', 15000000::numeric, 'capital_preservation', null),
        ('young_retirement_distance', 'dc', '초기 직장 DC', 'cash', '초기 DC 현금성 모형', 3000000::numeric, 'capital_preservation', null),
        ('young_retirement_distance', 'pension_savings', '소액 연금저축펀드', 'cash', '연금저축 현금성 모형', 3600000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'dc', '회사 DC', 'deposit', '중년층 DC 원리금보장 모형', 35000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'dc', '회사 DC', 'global_equity', '중년층 글로벌주식형 모형', 20000000::numeric, 'general_risky', null),
        ('family_budget_pressure', 'dc', '회사 DC', 'bond', '중년층 채권형 모형', 10000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'irp', '개인 IRP', 'deposit', '중년층 IRP 원리금보장 모형', 8000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'irp', '개인 IRP', 'cash', '중년층 IRP 현금성 모형', 4000000::numeric, 'capital_preservation', null),
        ('family_budget_pressure', 'pension_savings', '연금저축펀드', 'global_equity', '중년층 연금저축 글로벌주식형 모형', 5000000::numeric, 'general_risky', null),
        ('family_budget_pressure', 'pension_savings', '연금저축펀드', 'bond', '중년층 연금저축 채권형 모형', 4000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'irp', '수령기 IRP', 'deposit', '수령기 IRP 원리금보장 모형', 60000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'irp', '수령기 IRP', 'bond', '수령기 IRP 채권형 모형', 30000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'irp', '수령기 IRP', 'cash', '수령기 IRP 현금성 모형', 20000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 'bond', '수령기 연금저축 채권형 모형', 25000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 'cash', '수령기 연금저축 현금성 모형', 15000000::numeric, 'capital_preservation', null),
        ('pension_payout_transition', 'pension_savings', '수령기 연금저축펀드', 'global_equity', '수령기 연금저축 글로벌주식형 모형', 5000000::numeric, 'general_risky', null)
)
insert into public.mock_holdings (
    account_id, asset_class_id, instrument_name, market_value_krw,
    risk_treatment, statutory_exception
)
select
    ma.id,
    ac.id,
    hs.instrument_name,
    hs.market_value_krw,
    hs.risk_treatment,
    hs.statutory_exception
from holding_seed as hs
join public.mock_scenarios as ms on ms.code = hs.scenario_code
join public.mock_accounts as ma
    on ma.scenario_id = ms.id
   and ma.account_type = hs.account_type
   and ma.label = hs.account_label
join public.asset_classes as ac on ac.code = hs.asset_code
on conflict (account_id, instrument_name) do update set
    asset_class_id = excluded.asset_class_id,
    market_value_krw = excluded.market_value_krw,
    risk_treatment = excluded.risk_treatment,
    statutory_exception = excluded.statutory_exception;
