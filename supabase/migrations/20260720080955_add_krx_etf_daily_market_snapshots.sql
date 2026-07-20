-- KRX ETF 일별매매정보의 전체 상장 종목 스냅샷.
-- 연금계좌 적격성·253관측 여부와 무관하게 기준일 API의 계산 가능한 모든 ETF를
-- 보존한다. 원본 JSON은 data/raw/krx에 두고 이 테이블에는 조회용 정규화 값과
-- ingestion run 근거만 적재한다.
create table public.etf_daily_market_snapshots (
    base_date date not null,
    isu_code text not null
        constraint etf_daily_market_snapshots_isu_code_check
            check (isu_code ~ '^[0-9A-Z]{6}$'),
    isu_name text not null
        constraint etf_daily_market_snapshots_isu_name_check
            check (length(btrim(isu_name)) > 0),
    close_price_krw numeric not null
        constraint etf_daily_market_snapshots_close_check
            check (close_price_krw > 0),
    previous_day_change_krw numeric,
    fluctuation_rate_percent numeric,
    nav_krw numeric
        constraint etf_daily_market_snapshots_nav_check
            check (nav_krw is null or nav_krw > 0),
    open_price_krw numeric
        constraint etf_daily_market_snapshots_open_check
            check (open_price_krw is null or open_price_krw > 0),
    high_price_krw numeric
        constraint etf_daily_market_snapshots_high_check
            check (high_price_krw is null or high_price_krw > 0),
    low_price_krw numeric
        constraint etf_daily_market_snapshots_low_check
            check (low_price_krw is null or low_price_krw > 0),
    trading_volume bigint not null
        constraint etf_daily_market_snapshots_volume_check
            check (trading_volume >= 0),
    trading_value_krw numeric not null
        constraint etf_daily_market_snapshots_value_check
            check (trading_value_krw >= 0),
    market_cap_krw numeric
        constraint etf_daily_market_snapshots_market_cap_check
            check (market_cap_krw is null or market_cap_krw > 0),
    net_assets_krw numeric
        constraint etf_daily_market_snapshots_net_assets_check
            check (net_assets_krw is null or net_assets_krw > 0),
    listed_shares bigint
        constraint etf_daily_market_snapshots_listed_shares_check
            check (listed_shares is null or listed_shares > 0),
    benchmark_name text,
    benchmark_index numeric
        constraint etf_daily_market_snapshots_benchmark_index_check
            check (benchmark_index is null or benchmark_index > 0),
    source_id bigint not null
        references public.data_sources (id) on delete restrict,
    ingestion_run_id uuid not null
        references public.ingestion_runs (id) on delete restrict,
    observed_at timestamptz not null default now(),
    primary key (base_date, isu_code)
);

create index etf_daily_market_snapshots_volume_idx
    on public.etf_daily_market_snapshots
        (base_date desc, trading_volume desc, isu_code);

create index etf_daily_market_snapshots_history_idx
    on public.etf_daily_market_snapshots (isu_code, base_date desc);

alter table public.etf_daily_market_snapshots enable row level security;

-- 내부 시장 데이터: 브라우저 직접 접근을 차단하고 FastAPI 경유만 허용한다.
revoke all privileges on table public.etf_daily_market_snapshots
from public, anon, authenticated;

grant all privileges on table public.etf_daily_market_snapshots
to service_role;

comment on table public.etf_daily_market_snapshots is
    'KRX ETF 일별매매정보 전체 상장 종목의 거래량·거래대금·NAV 정규화 스냅샷';
comment on column public.etf_daily_market_snapshots.trading_volume is
    'KRX ACC_TRDVOL 기준일 누적 거래량(좌)';
comment on column public.etf_daily_market_snapshots.trading_value_krw is
    'KRX ACC_TRDVAL 기준일 누적 거래대금(원)';
