-- Preserve the mock-data edits that were made directly in the linked project.
-- The statements are safe to replay and do not touch account balances or holdings.

insert into public.mock_scenarios (
    code, name, description, age_band, risk_profile, investment_horizon_years
)
values
    (
        'dc_dormant',
        'DC형 방치',
        E'회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객\n비고: 납입액에 대한 세액공제혜택 대상인 연금저축펀드와 개인 IRP계좌가 없음',
        '40대',
        'balanced',
        20
    ),
    (
        'tax_contribution_uninvested',
        '세액공제 후 미운용',
        E'세액공제를 위해 납입했지만 IRP·연금저축을 실제 운용하지 않은 고객\n비고: 각 계좌별 납입액 세액공제한도를 고려하지 않고 납입했음',
        '30대',
        'balanced',
        25
    ),
    (
        'overlap_risk_concentration',
        '계좌별 중복·위험 편중',
        'DC·IRP·연금저축에 글로벌주식형 자산이 중복되어 위험자산 편중이 있는 고객',
        '30대',
        'growth',
        28
    ),
    (
        'young_retirement_distance',
        '연금이 멀게 느껴지는 청년층',
        '노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 청년층 고객',
        '20~39세',
        'balanced',
        35
    ),
    (
        'family_budget_pressure',
        '가계지출로 납입이 빠듯한 중년층',
        '자녀·주거비로 추가 납입은 빠듯하지만 노후 준비를 걱정하기 시작한 중년층 고객',
        '40~54세',
        'balanced',
        13
    )
on conflict (code) do update set
    description = excluded.description,
    updated_at = now();

with context_seed (auth_user_id, customer_context) as (
    values
        (
            '0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01'::uuid,
            E'회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객\n비고: 납입액에 대한 세액공제혜택 대상인 연금저축펀드와 개인 IRP계좌가 없음'
        ),
        (
            '1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02'::uuid,
            E'세액공제를 위해 납입했지만 IRP·연금저축을 실제 운용하지 않은 고객\n비고: 각 계좌별 납입액 세액공제한도를 고려하지 않고 납입했음'
        ),
        (
            '2f5cae61-5f80-4040-b3c2-9f33c4d93e03'::uuid,
            'DC·IRP·연금저축에 글로벌주식형 자산이 중복되어 위험자산 편중이 있는 고객'
        ),
        (
            '306dbf72-6091-4141-84d3-a044d5ea4f04'::uuid,
            '노후가 멀게 느껴져 연금 운용과 추가 납입의 우선순위가 낮은 청년층 고객'
        ),
        (
            '417ec083-71a2-4242-95e4-b155e6fb5005'::uuid,
            '자녀·주거비로 추가 납입은 빠듯하지만 노후 준비를 걱정하기 시작한 중년층 고객'
        )
)
update public.demo_user_financial_context as context
set customer_context = seed.customer_context,
    updated_at = now()
from context_seed as seed
where context.auth_user_id = seed.auth_user_id
  and context.customer_context is distinct from seed.customer_context;

with contribution_seed (
    auth_user_id, pension_savings_contribution_krw, irp_contribution_krw
) as (
    values
        ('0d3a8c4f-3d6e-4e2e-91a0-7d11a2b71c01'::uuid, 0::numeric, 0::numeric),
        ('1e4b9d50-4e7f-4f3f-a2b1-8e22b3c82d02'::uuid, 3000000::numeric, 6000000::numeric),
        ('2f5cae61-5f80-4040-b3c2-9f33c4d93e03'::uuid, 1500000::numeric, 2000000::numeric),
        ('306dbf72-6091-4141-84d3-a044d5ea4f04'::uuid, 2000000::numeric, 0::numeric),
        ('417ec083-71a2-4242-95e4-b155e6fb5005'::uuid, 2400000::numeric, 2400000::numeric)
)
update public.demo_user_financial_context as context
set pension_savings_contribution_krw = seed.pension_savings_contribution_krw,
    irp_contribution_krw = seed.irp_contribution_krw,
    updated_at = now()
from contribution_seed as seed
where context.auth_user_id = seed.auth_user_id
  and (
      context.pension_savings_contribution_krw
          is distinct from seed.pension_savings_contribution_krw
      or context.irp_contribution_krw is distinct from seed.irp_contribution_krw
  );
