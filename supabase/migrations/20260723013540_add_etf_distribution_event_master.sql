-- ETF 분배금·배당 및 권리 이벤트의 버전형 마스터.
-- KIND 현금분배 공시를 계산 근거로 유지하고, KIS KSD 일정·금융위 보조근거는
-- 원본 이벤트 payload와 함께 보존한다. DB는 이벤트를 재계산하거나 추정하지 않으며,
-- FastAPI(service_role)만 읽는다.

create table public.etf_distribution_event_versions (
    id bigint generated always as identity primary key,
    as_of date not null unique,
    status text not null default 'loading'
        constraint etf_distribution_event_versions_status_check
            check (status in ('loading', 'ready')),
    event_rows integer not null default 0
        constraint etf_distribution_event_versions_event_rows_check
            check (event_rows >= 0),
    source_sha256 text not null
        constraint etf_distribution_event_versions_source_sha256_check
            check (source_sha256 ~ '^[0-9a-f]{64}$'),
    engine_name text not null,
    engine_version text not null,
    source_files jsonb not null,
    loaded_at timestamptz,
    created_at timestamptz not null default now(),
    constraint etf_distribution_event_versions_ready_contract_check
        check (
            status <> 'ready'
            or (loaded_at is not null and event_rows > 0)
        )
);

-- 이벤트별 검색에 쓰는 정규화 컬럼과, 감사·출처 보존을 위한 원본 payload를 함께 둔다.
-- event_key는 정규화기에서 이벤트 전체 payload의 SHA-256으로 만들며, 같은 ETF·날짜에
-- 둘 이상의 서로 다른 공시가 있어도 유실되지 않게 한다.
create table public.etf_distribution_events (
    version_id bigint not null
        references public.etf_distribution_event_versions (id) on delete cascade,
    event_key text not null
        constraint etf_distribution_events_event_key_check
            check (event_key ~ '^[0-9a-f]{64}$'),
    isu_code text not null
        constraint etf_distribution_events_isu_code_check
            check (coalesce(length(btrim(isu_code)), 0) > 0),
    isu_name text,
    isin text,
    event_type text not null
        constraint etf_distribution_events_event_type_check
            check (coalesce(length(btrim(event_type)), 0) > 0),
    effective_date date not null,
    record_date date,
    payment_date date,
    cash_per_share_krw numeric
        constraint etf_distribution_events_cash_per_share_check
            check (cash_per_share_krw is null or cash_per_share_krw > 0),
    ratio numeric
        constraint etf_distribution_events_ratio_check
            check (ratio is null or ratio > 0),
    timing_basis text not null
        constraint etf_distribution_events_timing_basis_check
            check (coalesce(length(btrim(timing_basis)), 0) > 0),
    confidence text not null
        constraint etf_distribution_events_confidence_check
            check (coalesce(length(btrim(confidence)), 0) > 0),
    status text not null
        constraint etf_distribution_events_status_check
            check (coalesce(length(btrim(status)), 0) > 0),
    source_evidence jsonb not null,
    raw_payload jsonb not null,
    primary key (version_id, event_key)
);

create index etf_distribution_event_versions_latest_ready_idx
    on public.etf_distribution_event_versions (as_of desc, id desc)
    where status = 'ready';

create index etf_distribution_events_latest_etf_date_idx
    on public.etf_distribution_events (version_id, isu_code, effective_date desc);

alter table public.etf_distribution_event_versions enable row level security;
alter table public.etf_distribution_events enable row level security;

-- 원시 이벤트·출처는 브라우저로 노출하지 않는다. API 응답은 별도 계약에서
-- 필요한 필드와 출처 칩만 선별한다.
revoke all privileges on table
    public.etf_distribution_event_versions,
    public.etf_distribution_events
from public, anon, authenticated;

grant all privileges on table
    public.etf_distribution_event_versions,
    public.etf_distribution_events
to service_role;

revoke all privileges on sequence public.etf_distribution_event_versions_id_seq
from public, anon, authenticated;

grant usage, select on sequence public.etf_distribution_event_versions_id_seq
to service_role;

comment on table public.etf_distribution_event_versions is
    'ETF 분배금·배당·권리 이벤트 적재 버전. ready 최신 버전만 조회한다.';
comment on table public.etf_distribution_events is
    'KIND 현금분배와 KIS·금융위 보조근거를 포함한 ETF 이벤트 원본·정규화 마스터.';
comment on column public.etf_distribution_events.source_evidence is
    '공식 원천 URL·접수번호·검증 상태를 보존한 출처 증거. 브라우저에 직접 노출하지 않는다.';
comment on column public.etf_distribution_events.raw_payload is
    'etf_corporate_event_evidence가 산출한 이벤트 원본. DB에서 재계산하지 않는다.';
