-- ETF 포트폴리오 유니버스 원격 통합.
-- 로컬 파일 캐시(data/cache/returns·kis/adjusted_prices·events)에만 있던
-- 교육용 포트폴리오 엔진 입력을 Supabase로 옮긴다. 엔진이 실제 사용하는 형태
-- (계좌별 상품 마스터 + 253관측 총수익 지수)만 적재하고, 원시 수정주가 관측
-- (약 89.7만 행)은 파일 저장소에 감사용 원본으로 보존한다.
-- 계산은 Python 규칙 엔진이 한다. DB는 검증된 입력을 보관·제공만 한다.

-- 입고 전표: 적재 단위(버전)마다 1행. 리포지토리는 status = 'ready'인
-- 최신 버전만 읽으므로 적재가 중단돼도 반쪽 데이터가 노출되지 않는다.
create table public.etf_dataset_versions (
    id bigint generated always as identity primary key,
    as_of date not null unique,
    status text not null default 'loading'
        constraint etf_dataset_versions_status_check
            check (status in ('loading', 'ready')),
    product_rows integer not null default 0
        constraint etf_dataset_versions_product_rows_check
            check (product_rows >= 0),
    history_rows integer not null default 0
        constraint etf_dataset_versions_history_rows_check
            check (history_rows >= 0),
    source_sha256 text
        constraint etf_dataset_versions_source_sha256_check
            check (source_sha256 is null or source_sha256 ~ '^[0-9a-f]{64}$'),
    loaded_at timestamptz,
    created_at timestamptz not null default now(),
    constraint etf_dataset_versions_ready_contract_check
        check (
            status <> 'ready'
            or (
                loaded_at is not null
                and product_rows > 0
                and history_rows > 0
            )
        )
);

-- 계좌별 연금 적격 ETF 상품 마스터. payload는 총수익률·비용 마스터 계약의
-- product 객체를 그대로 보존해 파일 캐시와 같은 엔진 입력 계약을 유지한다.
create table public.etf_universe_products (
    version_id bigint not null
        references public.etf_dataset_versions (id) on delete cascade,
    account_type text not null
        constraint etf_universe_products_account_type_check
            check (account_type in ('dc', 'irp', 'pension_savings')),
    isu_code text not null
        constraint etf_universe_products_isu_code_check
            check (coalesce(length(btrim(isu_code)), 0) > 0),
    as_of date not null,
    payload jsonb not null,
    primary key (version_id, account_type, isu_code)
);

-- 종목별 총수익 지수(최근 253거래일). 분배금 반영 여부는 source로 구분하며
-- 값은 파일 캐시 기준 계산 결과를 그대로 적재한다(DB에서 재계산하지 않는다).
create table public.etf_return_histories (
    version_id bigint not null
        references public.etf_dataset_versions (id) on delete cascade,
    isu_code text not null
        constraint etf_return_histories_isu_code_check
            check (coalesce(length(btrim(isu_code)), 0) > 0),
    observed_on date not null,
    index_value numeric not null
        constraint etf_return_histories_index_value_check
            check (index_value > 0),
    source text not null
        constraint etf_return_histories_source_check
            check (
                source in (
                    'kis_adjusted_close_plus_kind_cash_distribution',
                    'kis_adjusted_close',
                    'krx_close_fallback'
                )
            ),
    primary key (version_id, isu_code, observed_on)
);

alter table public.etf_dataset_versions enable row level security;
alter table public.etf_universe_products enable row level security;
alter table public.etf_return_histories enable row level security;

-- 내부 데이터: 브라우저 접근을 차단하고 FastAPI(service_role) 경유만 허용한다.
revoke all privileges on table
    public.etf_dataset_versions,
    public.etf_universe_products,
    public.etf_return_histories
from public, anon, authenticated;

grant all privileges on table
    public.etf_dataset_versions,
    public.etf_universe_products,
    public.etf_return_histories
to service_role;

revoke all privileges on sequence public.etf_dataset_versions_id_seq
from public, anon, authenticated;

grant usage, select on sequence public.etf_dataset_versions_id_seq
to service_role;

comment on table public.etf_dataset_versions is
    'ETF 유니버스 적재 버전. ready 최신 버전만 리포지토리가 읽는다';
comment on table public.etf_universe_products is
    '계좌별 연금 적격 ETF 상품 마스터(총수익률·비용 마스터 계약 payload 보존)';
comment on table public.etf_return_histories is
    '종목별 253관측 총수익 지수(분배금 반영 여부는 source로 구분)';
comment on column public.etf_dataset_versions.source_sha256 is
    'cost-return·수정주가·종목 이벤트 등 실제 엔진 입력 전체의 결합 SHA-256 검증값';
