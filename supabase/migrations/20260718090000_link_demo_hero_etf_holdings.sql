-- 발표용 히어로 6명의 기존 목계좌 중 시장형 보유내역 12건을
-- 원격 ETF 유니버스의 실제 종목코드에 연결한다.
-- 예금·현금은 시나리오 의도를 보존하기 위해 ETF로 바꾸지 않는다.

alter table public.mock_holdings
    add column if not exists etf_isu_code text;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'mock_holdings_etf_isu_code_not_blank_check'
          and conrelid = 'public.mock_holdings'::regclass
    ) then
        alter table public.mock_holdings
            add constraint mock_holdings_etf_isu_code_not_blank_check
            check (
                etf_isu_code is null
                or coalesce(length(btrim(etf_isu_code)), 0) > 0
            );
    end if;
end
$$;

create index if not exists mock_holdings_etf_isu_code_idx
    on public.mock_holdings (etf_isu_code)
    where etf_isu_code is not null;

with hero_etf_links (
    scenario_code,
    account_type,
    asset_class_code,
    market_value_krw,
    etf_isu_code
) as (
    values
        ('family_budget_pressure', 'dc', 'global_equity', 20000000::numeric, '379800'),
        ('family_budget_pressure', 'dc', 'bond', 10000000::numeric, '273130'),
        ('family_budget_pressure', 'pension_savings', 'global_equity', 5000000::numeric, '379800'),
        ('family_budget_pressure', 'pension_savings', 'bond', 4000000::numeric, '273130'),
        ('overlap_risk_concentration', 'dc', 'global_equity', 60000000::numeric, '379800'),
        ('overlap_risk_concentration', 'dc', 'eligible_tdf', 20000000::numeric, '434060'),
        ('overlap_risk_concentration', 'irp', 'global_equity', 34000000::numeric, '379800'),
        ('overlap_risk_concentration', 'irp', 'bond', 16000000::numeric, '273130'),
        ('overlap_risk_concentration', 'pension_savings', 'global_equity', 36000000::numeric, '379800'),
        ('pension_payout_transition', 'irp', 'bond', 30000000::numeric, '273130'),
        ('pension_payout_transition', 'pension_savings', 'bond', 25000000::numeric, '273130'),
        ('pension_payout_transition', 'pension_savings', 'global_equity', 5000000::numeric, '379800')
)
update public.mock_holdings as holding
set etf_isu_code = link.etf_isu_code
from hero_etf_links as link
join public.mock_scenarios as scenario
  on scenario.code = link.scenario_code
join public.mock_accounts as account
  on account.scenario_id = scenario.id
 and account.account_type = link.account_type
join public.asset_classes as asset_class
  on asset_class.code = link.asset_class_code
where holding.account_id = account.id
  and holding.asset_class_id = asset_class.id
  and holding.market_value_krw = link.market_value_krw;

do $$
declare
    linked_count integer;
begin
    select count(*)
    into linked_count
    from public.mock_holdings as holding
    join public.mock_accounts as account on account.id = holding.account_id
    join public.mock_scenarios as scenario on scenario.id = account.scenario_id
    where scenario.code in (
        'dc_dormant',
        'tax_contribution_uninvested',
        'overlap_risk_concentration',
        'young_retirement_distance',
        'family_budget_pressure',
        'pension_payout_transition'
    )
      and holding.etf_isu_code is not null;

    if linked_count <> 12 then
        raise exception 'expected 12 hero ETF links, found %', linked_count;
    end if;

    if exists (
        select 1
        from public.mock_holdings as holding
        join public.mock_accounts as account on account.id = holding.account_id
        join public.mock_scenarios as scenario on scenario.id = account.scenario_id
        where scenario.code in (
            'dc_dormant',
            'tax_contribution_uninvested',
            'overlap_risk_concentration',
            'young_retirement_distance',
            'family_budget_pressure',
            'pension_payout_transition'
        )
          and holding.etf_isu_code is not null
          and not exists (
              select 1
              from public.etf_dataset_versions as version
              join public.etf_universe_products as product
                on product.version_id = version.id
              where version.status = 'ready'
                and version.id = (
                    select max(id)
                    from public.etf_dataset_versions
                    where status = 'ready'
                )
                and product.account_type = account.account_type
                and product.isu_code = holding.etf_isu_code
                and (product.payload -> 'account_eligibility' ->> 'eligible')::boolean
          )
    ) then
        raise exception 'hero ETF link is missing from the latest eligible universe';
    end if;

    if exists (
        select 1
        from (
            select distinct holding.etf_isu_code
            from public.mock_holdings as holding
            join public.mock_accounts as account on account.id = holding.account_id
            join public.mock_scenarios as scenario on scenario.id = account.scenario_id
            where scenario.code in (
                'dc_dormant',
                'tax_contribution_uninvested',
                'overlap_risk_concentration',
                'young_retirement_distance',
                'family_budget_pressure',
                'pension_payout_transition'
            )
              and holding.etf_isu_code is not null
        ) as linked
        where not (
            select count(*) = 253
            from public.etf_return_histories as history
            where history.version_id = (
                select max(id)
                from public.etf_dataset_versions
                where status = 'ready'
            )
              and history.isu_code = linked.etf_isu_code
        )
    ) then
        raise exception 'hero ETF link requires exactly 253 return observations';
    end if;
end
$$;

comment on column public.mock_holdings.etf_isu_code is
    '발표용 목보유내역과 최신 ETF 유니버스를 연결하는 KRX 종목코드. 예금·현금은 null';
