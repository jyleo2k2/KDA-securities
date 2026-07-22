alter table public.etf_component_snapshots
    add column as_of_date date,
    add column source_kind text not null default 'actual_portfolio'
        constraint etf_component_snapshots_source_kind_check
            check (source_kind in (
                'actual_portfolio', 'creation_basket',
                'index_exposure', 'collateral', 'look_through'
            )),
    add column coverage_kind text not null default 'full_portfolio'
        constraint etf_component_snapshots_coverage_kind_check
            check (coverage_kind in (
                'full_portfolio', 'published_top_n',
                'creation_basket', 'index_constituents',
                'collateral', 'look_through'
            )),
    add column completeness text not null default 'unknown'
        constraint etf_component_snapshots_completeness_check
            check (completeness in ('complete', 'partial', 'empty', 'unknown')),
    add column weight_basis text not null default 'reported_weight_percent'
        constraint etf_component_snapshots_weight_basis_check
            check (weight_basis in (
                'reported_weight_percent', 'fund_nav_percent',
                'basket_value_percent', 'index_percent',
                'collateral_percent', 'look_through_percent'
            )),
    add column source_locator text,
    add column source_component_count integer
        constraint etf_component_snapshots_source_component_count_check
            check (
                source_component_count is null
                or source_component_count >= 0
            );

create table public.etf_component_source_bindings (
    id bigint generated always as identity primary key,
    isu_code text not null
        constraint etf_component_source_bindings_isu_code_check
            check (isu_code ~ '^[0-9A-Z]{6}$'),
    source_id bigint not null
        references public.data_sources(id) on delete restrict,
    adapter_code text not null
        constraint etf_component_source_bindings_adapter_code_check
            check (adapter_code in (
                'sol_summary', 'tiger_pdf', 'kiwoom_pdf',
                'samsung_kodex_pdf', 'samsung_active_pdf'
            )),
    source_product_key text not null
        constraint etf_component_source_bindings_product_key_check
            check (coalesce(length(btrim(source_product_key)), 0) > 0),
    product_url text not null
        constraint etf_component_source_bindings_product_url_check
            check (product_url ~ '^https://'),
    holdings_url text not null
        constraint etf_component_source_bindings_holdings_url_check
            check (holdings_url ~ '^https://'),
    source_kind text not null
        constraint etf_component_source_bindings_source_kind_check
            check (source_kind in (
                'actual_portfolio', 'creation_basket',
                'index_exposure', 'collateral', 'look_through'
            )),
    coverage_kind text not null
        constraint etf_component_source_bindings_coverage_kind_check
            check (coverage_kind in (
                'full_portfolio', 'published_top_n',
                'creation_basket', 'index_constituents',
                'collateral', 'look_through'
            )),
    weight_basis text not null
        constraint etf_component_source_bindings_weight_basis_check
            check (weight_basis in (
                'reported_weight_percent', 'fund_nav_percent',
                'basket_value_percent', 'index_percent',
                'collateral_percent', 'look_through_percent'
            )),
    replication_type text not null
        constraint etf_component_source_bindings_replication_type_check
            check (replication_type in ('physical', 'synthetic')),
    management_type text not null
        constraint etf_component_source_bindings_management_type_check
            check (management_type in ('passive', 'active')),
    priority smallint not null default 100
        constraint etf_component_source_bindings_priority_check
            check (priority > 0),
    is_active boolean not null default true,
    metadata jsonb not null default '{}'::jsonb
        constraint etf_component_source_bindings_metadata_check
            check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    unique (isu_code, source_id, adapter_code)
);

create index etf_component_snapshots_official_latest_idx
    on public.etf_component_snapshots (
        isu_code, source_kind, completeness, as_of_date desc, captured_at desc
    );

create unique index etf_component_snapshots_official_dedupe_idx
    on public.etf_component_snapshots (
        isu_code, source_id, source_kind, as_of_date, raw_sha256
    )
    where as_of_date is not null;

create index etf_component_source_bindings_active_idx
    on public.etf_component_source_bindings (is_active, priority, isu_code);

alter table public.etf_component_source_bindings enable row level security;

revoke all privileges on table public.etf_component_source_bindings
from public, anon, authenticated;

grant all privileges on table public.etf_component_source_bindings
to service_role;

revoke all privileges on sequence public.etf_component_source_bindings_id_seq
from public, anon, authenticated;

grant usage, select on sequence public.etf_component_source_bindings_id_seq
to service_role;

insert into public.data_sources (
    code, name, source_type, authority, base_url,
    default_source_unit, metadata
)
values
    (
        'official_sol_etf', 'SOL ETF 공식 상품정보', 'official_document',
        '신한자산운용', 'https://www.soletf.com', 'percent',
        '{"data_boundary":"official_disclosure","is_mock":false}'::jsonb
    ),
    (
        'official_tiger_etf', 'TIGER ETF 공식 구성종목', 'official_document',
        '미래에셋자산운용', 'https://www.tigeretf.com', 'percent',
        '{"data_boundary":"official_disclosure","is_mock":false}'::jsonb
    ),
    (
        'official_kiwoom_etf', 'KIWOOM ETF 공식 구성종목', 'official_document',
        '키움투자자산운용', 'https://www.kiwoometf.com', 'percent',
        '{"data_boundary":"official_disclosure","is_mock":false}'::jsonb
    ),
    (
        'official_kodex_etf', 'KODEX ETF 공식 구성종목', 'official_document',
        '삼성자산운용', 'https://www.samsungfund.com', 'percent',
        '{"data_boundary":"official_disclosure","is_mock":false}'::jsonb
    ),
    (
        'official_koact_etf', 'KoAct ETF 공식 구성종목', 'official_document',
        '삼성액티브자산운용', 'https://www.samsungactive.co.kr', 'percent',
        '{"data_boundary":"official_disclosure","is_mock":false}'::jsonb
    )
on conflict (code) do update set
    name = excluded.name,
    source_type = excluded.source_type,
    authority = excluded.authority,
    base_url = excluded.base_url,
    default_source_unit = excluded.default_source_unit,
    metadata = public.data_sources.metadata || excluded.metadata,
    is_active = true,
    updated_at = now();

with binding_rows (
    isu_code, source_code, adapter_code, source_product_key,
    product_url, holdings_url, source_kind, coverage_kind,
    weight_basis, replication_type, management_type, priority
) as (
    values
        ('486450', 'official_sol_etf', 'sol_summary', '211063',
         'https://www.soletf.com/ko/fund/etf/211063',
         'https://www.soletf.com/ko/fund/etf/summary/211063',
         'actual_portfolio', 'published_top_n', 'fund_nav_percent',
         'physical', 'passive', 10),
        ('0051G0', 'official_sol_etf', 'sol_summary', '211091',
         'https://www.soletf.com/ko/fund/etf/211091',
         'https://www.soletf.com/ko/fund/etf/summary/211091',
         'actual_portfolio', 'published_top_n', 'fund_nav_percent',
         'physical', 'passive', 10),
        ('0023A0', 'official_sol_etf', 'sol_summary', '211084',
         'https://www.soletf.com/ko/fund/etf/211084',
         'https://www.soletf.com/ko/fund/etf/summary/211084',
         'actual_portfolio', 'published_top_n', 'fund_nav_percent',
         'physical', 'passive', 10),
        ('466950', 'official_tiger_etf', 'tiger_pdf', 'KR7466950003',
         'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7466950003',
         'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7466950003',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'active', 10),
        ('381180', 'official_tiger_etf', 'tiger_pdf', 'KR7381180009',
         'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7381180009',
         'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7381180009',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'passive', 10),
        ('371460', 'official_tiger_etf', 'tiger_pdf', 'KR7371460007',
         'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7371460007',
         'https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7371460007',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'passive', 10),
        ('474800', 'official_kiwoom_etf', 'kiwoom_pdf', '474800',
         'https://www.kiwoometf.com/service/etf/KO02010200M?gcode=474800',
         'https://www.kiwoometf.com/service/etf/KO02010200M?gcode=474800',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'passive', 10),
        ('498270', 'official_kiwoom_etf', 'kiwoom_pdf', '498270',
         'https://www.kiwoometf.com/service/etf/KO02010200M?gcode=498270',
         'https://www.kiwoometf.com/service/etf/KO02010200M?gcode=498270',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'passive', 10),
        ('0048K0', 'official_kodex_etf', 'samsung_kodex_pdf', '2ETFR1',
         'https://www.samsungfund.com/etf/product/view.do?id=2ETFR1',
         'https://www.samsungfund.com/api/v1/kodex/product/2ETFR1.do',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'passive', 10),
        ('475070', 'official_koact_etf', 'samsung_active_pdf', '2ETFL9',
         'https://www.samsungactive.co.kr/etf/view.do?id=2ETFL9',
         'https://www.samsungactive.co.kr/api/v1/product/etf/2ETFL9.do',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'active', 10),
        ('0020H0', 'official_koact_etf', 'samsung_active_pdf', '2ETFQ5',
         'https://www.samsungactive.co.kr/etf/view.do?id=2ETFQ5',
         'https://www.samsungactive.co.kr/api/v1/product/etf/2ETFQ5.do',
         'creation_basket', 'creation_basket', 'basket_value_percent',
         'physical', 'active', 10)
)
insert into public.etf_component_source_bindings (
    isu_code, source_id, adapter_code, source_product_key,
    product_url, holdings_url, source_kind, coverage_kind,
    weight_basis, replication_type, management_type, priority,
    metadata
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
    '{"approved_scope":"non_deferred_theme_candidates_2026_07_22"}'::jsonb
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

comment on table public.etf_component_source_bindings is
    '해외 ETF 공식 구성정보 수집을 위한 종목별 승인 출처와 어댑터 계약';

comment on column public.etf_component_snapshots.source_kind is
    '실제 포트폴리오, 설정·환매 바스켓, 지수 노출, 담보, 룩스루 구분';
