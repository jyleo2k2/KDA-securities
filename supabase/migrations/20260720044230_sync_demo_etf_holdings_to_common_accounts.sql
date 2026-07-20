-- Synchronize the upgraded six-customer ETF detail into the common account model.
-- The earlier common-account backfill is already applied remotely and remains
-- immutable. These rows are derived MOCK snapshots and are reproducible from
-- the legacy mock account/holding source updated by the preceding migration.

do $$
declare
    source_account_count integer;
    source_holding_count integer;
    target_account_count integer;
begin
    select count(*)
    into source_account_count
    from public.mock_accounts as account
    join public.mock_scenarios as scenario on scenario.id = account.scenario_id
    where scenario.code in (
        'dc_dormant',
        'tax_contribution_uninvested',
        'overlap_risk_concentration',
        'young_retirement_distance',
        'family_budget_pressure',
        'pension_payout_transition'
    );

    if source_account_count <> 13 then
        raise exception 'expected 13 detailed mock accounts, found %',
            source_account_count;
    end if;

    select count(*)
    into source_holding_count
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
    );

    if source_holding_count <> 86 then
        raise exception 'expected 86 detailed mock holdings, found %',
            source_holding_count;
    end if;

    if exists (
        select 1
        from public.mock_accounts as account
        join public.mock_scenarios as scenario on scenario.id = account.scenario_id
        left join public.mock_holdings as holding on holding.account_id = account.id
        where scenario.code in (
            'dc_dormant',
            'tax_contribution_uninvested',
            'overlap_risk_concentration',
            'young_retirement_distance',
            'family_budget_pressure',
            'pension_payout_transition'
        )
        group by account.id, account.balance_krw
        having account.balance_krw
            is distinct from coalesce(sum(holding.market_value_krw), 0)
    ) then
        raise exception 'detailed mock account balance does not equal holding total';
    end if;

    select count(*)
    into target_account_count
    from public.pension_accounts as account
    join public.mock_scenarios as scenario on scenario.id = account.scenario_id
    where account.data_kind = 'mock'
      and account.origin = 'synthetic'
      and scenario.code in (
          'dc_dormant',
          'tax_contribution_uninvested',
          'overlap_risk_concentration',
          'young_retirement_distance',
          'family_budget_pressure',
          'pension_payout_transition'
      );

    if target_account_count <> 13 then
        raise exception 'expected 13 existing common mock accounts, found %',
            target_account_count;
    end if;
end
$$;

with source_accounts as (
    select
        md5(
            'mock-account:' || scenario.code || ':' || account.account_type
            || ':' || account.label
        )::uuid as target_id,
        account.scenario_id,
        account.account_type,
        account.label
    from public.mock_accounts as account
    join public.mock_scenarios as scenario on scenario.id = account.scenario_id
    where scenario.code in (
        'dc_dormant',
        'tax_contribution_uninvested',
        'overlap_risk_concentration',
        'young_retirement_distance',
        'family_budget_pressure',
        'pension_payout_transition'
    )
)
insert into public.pension_accounts (
    id,
    owner_id,
    scenario_id,
    institution_id,
    account_type,
    account_name,
    data_kind,
    origin
)
select
    source.target_id,
    null,
    source.scenario_id,
    null,
    source.account_type,
    source.label,
    'mock',
    'synthetic'
from source_accounts as source
on conflict (id) do update set
    owner_id = null,
    scenario_id = excluded.scenario_id,
    institution_id = null,
    account_type = excluded.account_type,
    account_name = excluded.account_name,
    data_kind = 'mock',
    origin = 'synthetic',
    updated_at = now();

with source_snapshots as (
    select
        md5(
            'mock-snapshot:' || scenario.code || ':' || account.account_type
            || ':' || account.label || ':2026-07-16'
        )::uuid as target_id,
        md5(
            'mock-account:' || scenario.code || ':' || account.account_type
            || ':' || account.label
        )::uuid as target_account_id,
        account.balance_krw
    from public.mock_accounts as account
    join public.mock_scenarios as scenario on scenario.id = account.scenario_id
    where scenario.code in (
        'dc_dormant',
        'tax_contribution_uninvested',
        'overlap_risk_concentration',
        'young_retirement_distance',
        'family_budget_pressure',
        'pension_payout_transition'
    )
)
insert into public.account_snapshots (
    id,
    account_id,
    as_of_date,
    contributed_principal_krw,
    market_value_krw,
    source_id,
    origin
)
select
    source.target_id,
    source.target_account_id,
    date '2026-07-16',
    null::numeric,
    source.balance_krw,
    null,
    'synthetic'
from source_snapshots as source
on conflict (id) do update set
    account_id = excluded.account_id,
    as_of_date = excluded.as_of_date,
    contributed_principal_krw = null,
    market_value_krw = excluded.market_value_krw,
    source_id = null,
    origin = 'synthetic';

delete from public.account_holding_snapshots as holding
using public.account_snapshots as snapshot,
      public.pension_accounts as account,
      public.mock_scenarios as scenario
where holding.snapshot_id = snapshot.id
  and snapshot.account_id = account.id
  and account.scenario_id = scenario.id
  and account.data_kind = 'mock'
  and account.origin = 'synthetic'
  and snapshot.as_of_date = date '2026-07-16'
  and scenario.code in (
      'dc_dormant',
      'tax_contribution_uninvested',
      'overlap_risk_concentration',
      'young_retirement_distance',
      'family_budget_pressure',
      'pension_payout_transition'
  );

with source_holdings as (
    select
        md5(
            'mock-holding:' || scenario.code || ':' || account.account_type
            || ':' || account.label || ':' || holding.instrument_name
            || ':2026-07-16'
        )::uuid as target_id,
        md5(
            'mock-snapshot:' || scenario.code || ':' || account.account_type
            || ':' || account.label || ':2026-07-16'
        )::uuid as target_snapshot_id,
        holding.instrument_name,
        holding.etf_isu_code,
        holding.asset_class_id,
        holding.market_value_krw,
        holding.risk_treatment,
        holding.statutory_exception
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
)
insert into public.account_holding_snapshots (
    id,
    snapshot_id,
    product_id,
    raw_instrument_name,
    etf_isu_code,
    asset_class_id,
    market_value_krw,
    risk_treatment,
    statutory_exception,
    source_id,
    origin
)
select
    source.target_id,
    source.target_snapshot_id,
    null,
    source.instrument_name,
    source.etf_isu_code,
    source.asset_class_id,
    source.market_value_krw,
    source.risk_treatment,
    source.statutory_exception,
    null,
    'synthetic'
from source_holdings as source;

do $$
declare
    target_account_count integer;
    target_snapshot_count integer;
    target_holding_count integer;
begin
    select
        count(distinct account.id),
        count(distinct snapshot.id),
        count(holding.id)
    into
        target_account_count,
        target_snapshot_count,
        target_holding_count
    from public.pension_accounts as account
    join public.mock_scenarios as scenario on scenario.id = account.scenario_id
    join public.account_snapshots as snapshot on snapshot.account_id = account.id
    left join public.account_holding_snapshots as holding
        on holding.snapshot_id = snapshot.id
    where account.data_kind = 'mock'
      and account.origin = 'synthetic'
      and snapshot.as_of_date = date '2026-07-16'
      and scenario.code in (
          'dc_dormant',
          'tax_contribution_uninvested',
          'overlap_risk_concentration',
          'young_retirement_distance',
          'family_budget_pressure',
          'pension_payout_transition'
      );

    if target_account_count <> 13 or target_snapshot_count <> 13 then
        raise exception 'expected 13 synced common accounts and snapshots, found %/%',
            target_account_count,
            target_snapshot_count;
    end if;

    if target_holding_count <> 86 then
        raise exception 'expected 86 synced common holdings, found %',
            target_holding_count;
    end if;

    if exists (
        select 1
        from public.mock_accounts as source_account
        join public.mock_scenarios as scenario
            on scenario.id = source_account.scenario_id
        left join public.pension_accounts as target_account
            on target_account.id = md5(
                'mock-account:' || scenario.code || ':'
                || source_account.account_type || ':' || source_account.label
            )::uuid
        left join public.account_snapshots as target_snapshot
            on target_snapshot.account_id = target_account.id
           and target_snapshot.as_of_date = date '2026-07-16'
        left join public.account_holding_snapshots as target_holding
            on target_holding.snapshot_id = target_snapshot.id
        where scenario.code in (
            'dc_dormant',
            'tax_contribution_uninvested',
            'overlap_risk_concentration',
            'young_retirement_distance',
            'family_budget_pressure',
            'pension_payout_transition'
        )
        group by
            source_account.id,
            source_account.balance_krw,
            target_snapshot.market_value_krw,
            target_snapshot.contributed_principal_krw
        having target_snapshot.market_value_krw
                is distinct from source_account.balance_krw
            or target_snapshot.contributed_principal_krw is not null
            or coalesce(sum(target_holding.market_value_krw), 0)
                is distinct from source_account.balance_krw
    ) then
        raise exception 'synced common holding total does not match source';
    end if;

    if exists (
        select 1
        from public.mock_holdings as source_holding
        join public.mock_accounts as source_account
            on source_account.id = source_holding.account_id
        join public.mock_scenarios as scenario
            on scenario.id = source_account.scenario_id
        left join public.account_holding_snapshots as target_holding
            on target_holding.id = md5(
                'mock-holding:' || scenario.code || ':'
                || source_account.account_type || ':' || source_account.label
                || ':' || source_holding.instrument_name || ':2026-07-16'
            )::uuid
        where scenario.code in (
            'dc_dormant',
            'tax_contribution_uninvested',
            'overlap_risk_concentration',
            'young_retirement_distance',
            'family_budget_pressure',
            'pension_payout_transition'
        )
          and (
              target_holding.id is null
              or target_holding.raw_instrument_name
                    is distinct from source_holding.instrument_name
              or target_holding.etf_isu_code
                    is distinct from source_holding.etf_isu_code
              or target_holding.asset_class_id
                    is distinct from source_holding.asset_class_id
              or target_holding.market_value_krw
                    is distinct from source_holding.market_value_krw
              or target_holding.risk_treatment
                    is distinct from source_holding.risk_treatment
              or target_holding.statutory_exception
                    is distinct from source_holding.statutory_exception
          )
    ) then
        raise exception 'synced common holding detail does not match source';
    end if;
end
$$;
