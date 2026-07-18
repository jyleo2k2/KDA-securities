alter table public.news_items
    add column market_region text,
    add column market_topics text[] not null default array[]::text[],
    add column canonical_url text,
    add column normalized_title_hash text,
    add column event_fingerprint text,
    add column is_active boolean not null default true,
    add column selection_score smallint,
    add column selection_reasons text[] not null default array[]::text[],
    add column selection_policy_version text,
    add column selection_embedding extensions.vector(1024),
    add column selection_embedding_model text;

alter table public.news_items
    add constraint news_items_market_region_check
        check (market_region is null or market_region in ('kr', 'us')),
    add constraint news_items_selection_score_check
        check (selection_score is null or selection_score between 0 and 100),
    add constraint news_items_normalized_title_hash_check
        check (
            normalized_title_hash is null
            or normalized_title_hash ~ '^[0-9a-f]{64}$'
        ),
    add constraint news_items_event_fingerprint_check
        check (
            event_fingerprint is null
            or event_fingerprint ~ '^[0-9a-f]{64}$'
        ),
    add constraint news_items_selection_embedding_contract_check
        check (
            (selection_embedding is null and selection_embedding_model is null)
            or (
                selection_embedding is not null
                and selection_embedding_model is not null
                and extensions.vector_dims(selection_embedding) = 1024
            )
        ),
    add constraint news_items_market_selection_contract_check
        check (
            selection_policy_version is null
            or (
                summary_status = 'succeeded'
                and market_region is not null
                and cardinality(market_topics) > 0
                and canonical_url is not null
                and normalized_title_hash is not null
                and event_fingerprint is not null
                and selection_score is not null
                and cardinality(selection_reasons) > 0
                and selection_embedding is not null
                and selection_embedding_model is not null
            )
        );

create unique index news_items_canonical_url_unique_idx
    on public.news_items (canonical_url)
    where canonical_url is not null;

create unique index news_items_normalized_title_hash_unique_idx
    on public.news_items (normalized_title_hash)
    where normalized_title_hash is not null;

create unique index news_items_source_content_sha256_unique_idx
    on public.news_items (source_content_sha256)
    where source_content_sha256 is not null;

create unique index news_items_event_fingerprint_unique_idx
    on public.news_items (event_fingerprint)
    where event_fingerprint is not null;

create index news_items_market_recent_idx
    on public.news_items (published_at desc, fetched_at desc, id)
    where selection_policy_version is not null
      and summary_status = 'succeeded'
      and is_active;

comment on column public.news_items.selection_score is
    '시장영향·직접관련성·구체성·출처신뢰도·최신성·새로움의 규칙 기반 100점 점수';
comment on column public.news_items.selection_reasons is
    'LLM이 아닌 규칙 엔진이 기록한 선별 근거';
comment on column public.news_items.selection_embedding is
    '중복 기사 차단용 제목·검색요약 BGE-M3 정규화 임베딩';
