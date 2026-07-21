-- KIS ETF 구성종목은 시점별 스냅샷으로 보존한다. 챗봇은 이 테이블의 최신
-- 성공 스냅샷만 조회하며, 요청 시점에 KIS API를 직접 호출하지 않는다.

insert into public.data_sources (
    code, name, source_type, authority, base_url, default_source_unit, metadata
)
values (
    'kis_etf_components',
    '한국투자증권 ETF 구성종목 시세',
    'market_api',
    '한국투자증권',
    'https://openapi.koreainvestment.com:9443/uapi/etfetn/v1/quotations/inquire-component-stock-price',
    'percent',
    '{"data_boundary":"official_market_data","is_mock":false}'::jsonb
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

create table public.etf_component_snapshots (
    id bigint generated always as identity primary key,
    isu_code text not null
        constraint etf_component_snapshots_isu_code_check
            check (coalesce(length(btrim(isu_code)), 0) > 0),
    captured_at timestamptz not null,
    status text not null
        constraint etf_component_snapshots_status_check
            check (status in ('succeeded', 'empty')),
    component_count integer not null
        constraint etf_component_snapshots_component_count_check
            check (component_count >= 0),
    raw_payload jsonb not null
        constraint etf_component_snapshots_raw_payload_check
            check (jsonb_typeof(raw_payload) = 'object'),
    raw_sha256 text not null
        constraint etf_component_snapshots_raw_sha256_check
            check (raw_sha256 ~ '^[0-9a-f]{64}$'),
    source_id bigint not null references public.data_sources(id) on delete restrict,
    ingestion_run_id uuid not null references public.ingestion_runs(id) on delete restrict,
    created_at timestamptz not null default now(),
    unique (isu_code, captured_at),
    constraint etf_component_snapshots_empty_contract_check
        check (
            (status = 'empty' and component_count = 0)
            or (status = 'succeeded' and component_count > 0)
        )
);

create table public.etf_component_snapshot_items (
    snapshot_id bigint not null
        references public.etf_component_snapshots(id) on delete cascade,
    rank smallint not null
        constraint etf_component_snapshot_items_rank_check
            check (rank between 1 and 3),
    component_isu_code text,
    component_name text not null
        constraint etf_component_snapshot_items_component_name_check
            check (coalesce(length(btrim(component_name)), 0) > 0),
    weight_percent numeric(9, 6) not null
        constraint etf_component_snapshot_items_weight_percent_check
            check (weight_percent > 0 and weight_percent <= 100),
    primary key (snapshot_id, rank)
);

create index etf_component_snapshots_latest_idx
    on public.etf_component_snapshots (isu_code, captured_at desc);

alter table public.etf_component_snapshots enable row level security;
alter table public.etf_component_snapshot_items enable row level security;

revoke all privileges on table
    public.etf_component_snapshots,
    public.etf_component_snapshot_items
from public, anon, authenticated;

grant all privileges on table
    public.etf_component_snapshots,
    public.etf_component_snapshot_items
to service_role;

revoke all privileges on sequence public.etf_component_snapshots_id_seq
from public, anon, authenticated;

grant usage, select on sequence public.etf_component_snapshots_id_seq to service_role;

comment on table public.etf_component_snapshots is
    'KIS ETF 구성종목 원문과 수집시각을 보존한 ETF별 스냅샷';
comment on table public.etf_component_snapshot_items is
    'ETF 구성종목 스냅샷에서 비중 상위 3개만 정규화한 서비스 조회용 행';
