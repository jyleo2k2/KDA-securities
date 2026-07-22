-- KIS may return an empty component list for an otherwise eligible domestic
-- ETF.  These issuer-published creation baskets are the approved, current
-- fallback for the three remaining theme candidates.
with binding_rows (
    isu_code, source_code, adapter_code, source_product_key,
    product_url, holdings_url, source_kind, coverage_kind,
    weight_basis, replication_type, management_type, priority
) as (
    values
        (
            '266420', 'official_kodex_etf', 'samsung_kodex_pdf', '2ETF78',
            'https://www.samsungfund.com/etf/product/view.do?id=2ETF78',
            'https://www.samsungfund.com/api/v1/kodex/product/2ETF78.do',
            'creation_basket', 'creation_basket', 'basket_value_percent',
            'physical', 'passive', 10
        ),
        (
            '352540', 'official_kodex_etf', 'samsung_kodex_pdf', '2ETFD1',
            'https://www.samsungfund.com/etf/product/view.do?id=2ETFD1',
            'https://www.samsungfund.com/api/v1/kodex/product/2ETFD1.do',
            'creation_basket', 'creation_basket', 'basket_value_percent',
            'physical', 'passive', 10
        )
)
insert into public.etf_component_source_bindings (
    isu_code, source_id, adapter_code, source_product_key,
    product_url, holdings_url, source_kind, coverage_kind,
    weight_basis, replication_type, management_type, priority, metadata
)
select
    row.isu_code,
    source.id,
    row.adapter_code,
    row.source_product_key,
    row.product_url,
    row.holdings_url,
    row.source_kind,
    row.coverage_kind,
    row.weight_basis,
    row.replication_type,
    row.management_type,
    row.priority,
    '{"approved_scope":"domestic_theme_component_fallback_2026_07_22"}'::jsonb
from binding_rows as row
join public.data_sources as source on source.code = row.source_code
on conflict (isu_code, source_id, adapter_code) do update set
    source_product_key = excluded.source_product_key,
    product_url = excluded.product_url,
    holdings_url = excluded.holdings_url,
    source_kind = excluded.source_kind,
    coverage_kind = excluded.coverage_kind,
    weight_basis = excluded.weight_basis,
    replication_type = excluded.replication_type,
    management_type = excluded.management_type,
    priority = excluded.priority,
    metadata = public.etf_component_source_bindings.metadata || excluded.metadata,
    is_active = true;
