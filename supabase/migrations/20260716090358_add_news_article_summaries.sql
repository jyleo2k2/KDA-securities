alter table public.news_items
    add column summary_lines text[] not null default array[]::text[],
    add column summary_status text not null default 'pending',
    add column summary_source_kind text,
    add column summary_model text,
    add column summary_prompt_version text,
    add column source_content_sha256 text,
    add column summarized_at timestamptz,
    add column summary_attempt_count integer not null default 0,
    add column summary_error_code text,
    add column summary_claimed_at timestamptz;

alter table public.news_items
    add constraint news_items_summary_status_check
        check (
            summary_status in (
                'pending',
                'processing',
                'succeeded',
                'fetch_failed',
                'model_failed',
                'validation_failed'
            )
        ),
    add constraint news_items_summary_source_kind_check
        check (
            summary_source_kind is null
            or summary_source_kind = 'article_body'
        ),
    add constraint news_items_summary_attempt_count_check
        check (summary_attempt_count >= 0),
    add constraint news_items_source_content_sha256_check
        check (
            source_content_sha256 is null
            or source_content_sha256 ~ '^[0-9a-f]{64}$'
        ),
    add constraint news_items_summary_success_contract_check
        check (
            summary_status <> 'succeeded'
            or (
                cardinality(summary_lines) = 3
                and btrim(summary_lines[1]) <> ''
                and btrim(summary_lines[2]) <> ''
                and btrim(summary_lines[3]) <> ''
                and summary_source_kind = 'article_body'
                and summary_model is not null
                and summary_prompt_version is not null
                and source_content_sha256 is not null
                and summarized_at is not null
                and summary_error_code is null
                and summary_claimed_at is null
            )
        ),
    add constraint news_items_summary_processing_contract_check
        check (
            summary_status <> 'processing'
            or summary_claimed_at is not null
        ),
    add constraint news_items_summary_failure_contract_check
        check (
            summary_status not in (
                'fetch_failed', 'model_failed', 'validation_failed'
            )
            or (
                cardinality(summary_lines) = 0
                and summary_error_code is not null
                and summary_claimed_at is not null
            )
        );

create index news_items_ready_summary_idx
    on public.news_items (search_query, published_at desc)
    where summary_status = 'succeeded';

create index news_items_pending_summary_idx
    on public.news_items (published_at desc, summary_attempt_count)
    where summary_status in (
        'pending',
        'processing',
        'fetch_failed',
        'model_failed',
        'validation_failed'
    );

comment on column public.news_items.summary_lines is
    '기사 원문을 일시적으로 추출해 LLM이 생성한 정확히 세 줄의 요약';
comment on column public.news_items.source_content_sha256 is
    '저장하지 않은 정규화 기사 본문의 SHA-256 검증값';
