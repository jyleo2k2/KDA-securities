-- ETF 테마 설명은 data/reference/etf_theme_catalog.json을 답변 SSOT로 유지한다.
-- 이 장부는 카탈로그 문구 자체를 복제하지 않고, 실제로 렌더링되는 질문 유형별
-- payload 해시와 승인된 공식 지식 근거만 연결한다. 문구가 바뀌면 해시가 달라져
-- 기존 승인을 자동으로 재사용할 수 없다.

create table public.etf_theme_content_reviews (
    id bigint generated always as identity primary key,
    catalog_version text not null
        constraint etf_theme_content_reviews_catalog_version_check
            check (coalesce(length(btrim(catalog_version)), 0) > 0),
    theme_id text not null
        constraint etf_theme_content_reviews_theme_id_check
            check (theme_id ~ '^[a-z0-9_]+$'),
    topic text not null
        constraint etf_theme_content_reviews_topic_check
            check (
                topic in (
                    'overview',
                    'representative_companies',
                    'investment_considerations'
                )
            ),
    content_sha256 text not null
        constraint etf_theme_content_reviews_sha256_check
            check (content_sha256 ~ '^[0-9a-f]{64}$'),
    status text not null default 'draft'
        constraint etf_theme_content_reviews_status_check
            check (status in ('draft', 'verified', 'rejected')),
    verified_at timestamptz,
    review_due_date date,
    reviewer text,
    review_notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint etf_theme_content_reviews_unique
        unique (catalog_version, theme_id, topic),
    constraint etf_theme_content_reviews_verified_contract_check
        check (
            status <> 'verified'
            or (
                verified_at is not null
                and review_due_date is not null
                and review_due_date >= verified_at::date
                and coalesce(length(btrim(reviewer)), 0) > 0
            )
        )
);

create index etf_theme_content_reviews_ready_idx
    on public.etf_theme_content_reviews (
        catalog_version,
        theme_id,
        topic,
        review_due_date
    )
    where status = 'verified';

-- knowledge_chunk가 선택됐을 때 그 청크가 같은 knowledge_document 소속임을
-- 복합 FK로 강제한다. 기존 PK(id)는 그대로 유지한다.
create unique index knowledge_chunks_document_id_id_unique
    on public.knowledge_chunks (document_id, id);

create table public.etf_theme_content_evidence (
    id bigint generated always as identity primary key,
    review_id bigint not null
        references public.etf_theme_content_reviews (id) on delete cascade,
    knowledge_document_id uuid not null
        references public.knowledge_documents (id) on delete restrict,
    knowledge_chunk_id bigint not null,
    official_source_url text not null
        constraint etf_theme_content_evidence_source_url_check
            check (official_source_url ~ '^https://'),
    source_label text not null
        constraint etf_theme_content_evidence_source_label_check
            check (coalesce(length(btrim(source_label)), 0) > 0),
    evidence_role text not null
        constraint etf_theme_content_evidence_role_check
            check (
                evidence_role in (
                    'definition',
                    'exposure',
                    'company_profile',
                    'benefit',
                    'risk',
                    'service_interpretation'
                )
            ),
    display_order smallint not null default 1
        constraint etf_theme_content_evidence_display_order_check
            check (display_order > 0),
    created_at timestamptz not null default now(),
    constraint etf_theme_content_evidence_unique
        unique (review_id, official_source_url, evidence_role),
    constraint etf_theme_content_evidence_review_chunk_unique
        unique (review_id, knowledge_chunk_id),
    constraint etf_theme_content_evidence_chunk_document_fk
        foreign key (knowledge_document_id, knowledge_chunk_id)
        references public.knowledge_chunks (document_id, id)
        on delete restrict
);

create index etf_theme_content_evidence_review_idx
    on public.etf_theme_content_evidence (review_id, display_order, id);

alter table public.etf_theme_content_reviews enable row level security;
alter table public.etf_theme_content_evidence enable row level security;

-- 공식 검증 장부는 FastAPI 서버와 승인 적재 작업만 접근한다. 브라우저에는
-- service_role 또는 직접 쓰기 권한을 노출하지 않는다.
revoke all privileges on table
    public.etf_theme_content_reviews,
    public.etf_theme_content_evidence
from public, anon, authenticated;

grant select, insert, update, delete on table
    public.etf_theme_content_reviews,
    public.etf_theme_content_evidence
to service_role;

revoke all privileges on sequence
    public.etf_theme_content_reviews_id_seq,
    public.etf_theme_content_evidence_id_seq
from public, anon, authenticated;

grant usage, select on sequence
    public.etf_theme_content_reviews_id_seq,
    public.etf_theme_content_evidence_id_seq
to service_role;

comment on table public.etf_theme_content_reviews is
    'ETF 테마 카탈로그의 질문 유형별 payload 해시·검토 상태 장부';
comment on table public.etf_theme_content_evidence is
    'ETF 테마 검토 단위와 승인 지식 문서·공식 URL의 근거 연결';
