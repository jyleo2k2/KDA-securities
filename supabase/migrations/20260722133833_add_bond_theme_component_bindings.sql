-- REMOTE-APPLIED: official issuer bindings for the bonds ETF theme.
alter table public.etf_component_source_bindings
    drop constraint etf_component_source_bindings_adapter_code_check,
    add constraint etf_component_source_bindings_adapter_code_check
        check (adapter_code in (
            'sol_summary', 'tiger_pdf', 'kiwoom_pdf',
            'samsung_kodex_pdf', 'samsung_active_pdf', 'ace_pdf'
        ));

insert into public.data_sources (
    code, name, source_type, authority, base_url, default_source_unit, metadata
)
values (
    'official_ace_etf', 'ACE ETF 공식 구성종목', 'official_document',
    '한국투자신탁운용', 'https://www.aceetf.co.kr', 'percent',
    '{"data_boundary":"official_disclosure","is_mock":false}'::jsonb
)
on conflict (code) do update set
    name = excluded.name, source_type = excluded.source_type,
    authority = excluded.authority, base_url = excluded.base_url,
    default_source_unit = excluded.default_source_unit,
    metadata = public.data_sources.metadata || excluded.metadata,
    is_active = true, updated_at = now();

with binding_rows (
    isu_code, source_code, adapter_code, source_product_key, product_url,
    holdings_url, source_kind, coverage_kind, weight_basis,
    replication_type, management_type, priority
) as (
    values
        ('0046A0', 'official_tiger_etf', 'tiger_pdf', 'KR70046A0008', 'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR70046A0008', 'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR70046A0008', 'creation_basket', 'creation_basket', 'basket_value_percent', 'physical', 'passive', 10),
        ('329750', 'official_tiger_etf', 'tiger_pdf', 'KR7329750004', 'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7329750004', 'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7329750004', 'creation_basket', 'creation_basket', 'basket_value_percent', 'physical', 'active', 10),
        ('484790', 'official_kodex_etf', 'samsung_kodex_pdf', '2ETFN5', 'https://www.samsungfund.com/etf/product/view.do?id=2ETFN5', 'https://www.samsungfund.com/api/v1/kodex/product/2ETFN5.do', 'creation_basket', 'creation_basket', 'basket_value_percent', 'physical', 'active', 10),
        ('453850', 'official_ace_etf', 'ace_pdf', 'K55101E03860', 'https://www.aceetf.co.kr/fund/K55101E03860', 'https://papi.aceetf.co.kr/api/funds/K55101E03860/pdf?page=1&size=1000&std_dt=', 'creation_basket', 'creation_basket', 'basket_value_percent', 'physical', 'active', 10),
        ('476760', 'official_ace_etf', 'ace_pdf', 'K55101E91865', 'https://www.aceetf.co.kr/fund/K55101E91865', 'https://papi.aceetf.co.kr/api/funds/K55101E91865/pdf?page=1&size=1000&std_dt=', 'creation_basket', 'creation_basket', 'basket_value_percent', 'physical', 'active', 10)
)
insert into public.etf_component_source_bindings (
    isu_code, source_id, adapter_code, source_product_key, product_url,
    holdings_url, source_kind, coverage_kind, weight_basis, replication_type,
    management_type, priority, metadata
)
select row.isu_code, source.id, row.adapter_code, row.source_product_key,
       row.product_url, row.holdings_url, row.source_kind, row.coverage_kind,
       row.weight_basis, row.replication_type, row.management_type, row.priority,
       '{"approved_scope":"bond_theme_component_bindings_2026_07_22"}'::jsonb
from binding_rows as row
join public.data_sources as source on source.code = row.source_code
on conflict (isu_code, source_id, adapter_code) do update set
    source_product_key = excluded.source_product_key,
    product_url = excluded.product_url, holdings_url = excluded.holdings_url,
    source_kind = excluded.source_kind, coverage_kind = excluded.coverage_kind,
    weight_basis = excluded.weight_basis,
    replication_type = excluded.replication_type,
    management_type = excluded.management_type, priority = excluded.priority,
    metadata = public.etf_component_source_bindings.metadata || excluded.metadata,
    is_active = true;
