create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;

create table public.data_sources (
    id bigint generated always as identity primary key,
    code text not null unique,
    name text not null,
    source_type text not null check (
        source_type in ('regulator_api', 'market_api', 'news_api', 'official_document', 'curated')
    ),
    authority text not null,
    base_url text,
    default_source_unit text,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.ingestion_runs (
    id uuid primary key default extensions.gen_random_uuid(),
    source_id bigint not null references public.data_sources(id) on delete restrict,
    endpoint text not null,
    requested_params jsonb not null default '{}'::jsonb
        check (jsonb_typeof(requested_params) = 'object')
        check (not (requested_params ? 'key')),
    status text not null check (status in ('running', 'succeeded', 'failed')),
    requested_at timestamptz not null default now(),
    completed_at timestamptz,
    response_code text,
    response_message text,
    source_record_count integer check (source_record_count is null or source_record_count >= 0),
    normalized_record_count integer check (normalized_record_count is null or normalized_record_count >= 0),
    upserted_record_count integer check (upserted_record_count is null or upserted_record_count >= 0),
    error_message text,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    constraint ingestion_runs_completion_check check (
        (status = 'running' and completed_at is null)
        or (status in ('succeeded', 'failed') and completed_at is not null)
    )
);

create index ingestion_runs_source_requested_idx
    on public.ingestion_runs (source_id, requested_at desc);

create table public.financial_institutions (
    id bigint generated always as identity primary key,
    normalized_name text not null unique,
    institution_type text,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.institution_aliases (
    id bigint generated always as identity primary key,
    institution_id bigint not null references public.financial_institutions(id) on delete cascade,
    source_id bigint not null references public.data_sources(id) on delete cascade,
    alias_name text not null,
    created_at timestamptz not null default now(),
    unique (source_id, alias_name)
);

create index institution_aliases_institution_idx
    on public.institution_aliases (institution_id);

create table public.pension_savings_provider_stats (
    id bigint generated always as identity primary key,
    source_id bigint not null references public.data_sources(id) on delete restrict,
    ingestion_run_id uuid not null references public.ingestion_runs(id) on delete restrict,
    institution_id bigint references public.financial_institutions(id) on delete set null,
    year smallint not null check (year between 2000 and 2100),
    quarter smallint not null check (quarter between 1 and 4),
    area_name_raw text not null,
    company_name_raw text not null,
    reserve_source_value numeric(24, 6),
    reserve_source_value_1y numeric(24, 6),
    reserve_source_value_2y numeric(24, 6),
    reserve_source_value_3y numeric(24, 6),
    reserve_source_unit text not null check (reserve_source_unit in ('million_krw', 'hundred_million_krw')),
    reserve_unit_basis text not null,
    reserve_krw numeric(24, 0) generated always as (
        case
            when reserve_source_value is null then null
            when reserve_source_unit = 'million_krw' then reserve_source_value * 1000000
            when reserve_source_unit = 'hundred_million_krw' then reserve_source_value * 100000000
        end
    ) stored,
    reserve_krw_1y numeric(24, 0) generated always as (
        case
            when reserve_source_value_1y is null then null
            when reserve_source_unit = 'million_krw' then reserve_source_value_1y * 1000000
            when reserve_source_unit = 'hundred_million_krw' then reserve_source_value_1y * 100000000
        end
    ) stored,
    reserve_krw_2y numeric(24, 0) generated always as (
        case
            when reserve_source_value_2y is null then null
            when reserve_source_unit = 'million_krw' then reserve_source_value_2y * 1000000
            when reserve_source_unit = 'hundred_million_krw' then reserve_source_value_2y * 100000000
        end
    ) stored,
    reserve_krw_3y numeric(24, 0) generated always as (
        case
            when reserve_source_value_3y is null then null
            when reserve_source_unit = 'million_krw' then reserve_source_value_3y * 1000000
            when reserve_source_unit = 'hundred_million_krw' then reserve_source_value_3y * 100000000
        end
    ) stored,
    earn_rate_current numeric(12, 6),
    earn_rate_1y numeric(12, 6),
    earn_rate_2y numeric(12, 6),
    earn_rate_3y numeric(12, 6),
    fee_rate_1y numeric(12, 6),
    fee_rate_2y numeric(12, 6),
    fee_rate_3y numeric(12, 6),
    avg_earn_rate_3y numeric(12, 6),
    avg_earn_rate_5y numeric(12, 6),
    avg_earn_rate_7y numeric(12, 6),
    avg_earn_rate_10y numeric(12, 6),
    avg_fee_rate_3y numeric(12, 6),
    avg_fee_rate_5y numeric(12, 6),
    avg_fee_rate_7y numeric(12, 6),
    avg_fee_rate_10y numeric(12, 6),
    quality_flags jsonb not null default '[]'::jsonb check (jsonb_typeof(quality_flags) = 'array'),
    raw_payload jsonb not null check (jsonb_typeof(raw_payload) = 'object'),
    observed_at timestamptz not null default now(),
    unique (source_id, year, quarter, area_name_raw, company_name_raw)
);

create index pension_savings_provider_stats_institution_period_idx
    on public.pension_savings_provider_stats (institution_id, year desc, quarter desc);
create index pension_savings_provider_stats_ingestion_run_idx
    on public.pension_savings_provider_stats (ingestion_run_id);

create table public.retirement_provider_stats (
    id bigint generated always as identity primary key,
    source_id bigint not null references public.data_sources(id) on delete restrict,
    ingestion_run_id uuid not null references public.ingestion_runs(id) on delete restrict,
    institution_id bigint references public.financial_institutions(id) on delete set null,
    year smallint not null check (year between 2000 and 2100),
    quarter smallint not null check (quarter between 1 and 4),
    requested_sys_type smallint not null check (requested_sys_type between 1 and 5),
    response_division text not null,
    area_name_raw text not null,
    company_name_raw text not null,
    scheme text not null check (scheme in ('db', 'dc', 'irp')),
    reserve_source_value numeric(24, 6),
    reserve_source_unit text not null check (reserve_source_unit in ('million_krw', 'hundred_million_krw')),
    reserve_unit_basis text not null,
    reserve_krw numeric(24, 0) generated always as (
        case
            when reserve_source_value is null then null
            when reserve_source_unit = 'million_krw' then reserve_source_value * 1000000
            when reserve_source_unit = 'hundred_million_krw' then reserve_source_value * 100000000
        end
    ) stored,
    earn_rate_current numeric(12, 6),
    avg_earn_rate_3y numeric(12, 6),
    avg_earn_rate_5y numeric(12, 6),
    avg_earn_rate_7y numeric(12, 6),
    avg_earn_rate_10y numeric(12, 6),
    quality_flags jsonb not null default '[]'::jsonb check (jsonb_typeof(quality_flags) = 'array'),
    raw_payload jsonb not null check (jsonb_typeof(raw_payload) = 'object'),
    observed_at timestamptz not null default now(),
    unique (source_id, year, quarter, requested_sys_type, company_name_raw, scheme)
);

create index retirement_provider_stats_institution_period_idx
    on public.retirement_provider_stats (institution_id, year desc, quarter desc, scheme);

create index retirement_provider_stats_scheme_period_idx
    on public.retirement_provider_stats (scheme, year desc, quarter desc);
create index retirement_provider_stats_ingestion_run_idx
    on public.retirement_provider_stats (ingestion_run_id);

create table public.asset_classes (
    id bigint generated always as identity primary key,
    code text not null unique,
    name text not null,
    is_general_risky boolean not null,
    sort_order smallint not null default 0,
    created_at timestamptz not null default now()
);

create table public.mock_scenarios (
    id bigint generated always as identity primary key,
    code text not null unique,
    name text not null,
    description text not null,
    age_band text not null,
    risk_profile text not null check (risk_profile in ('conservative', 'balanced', 'growth')),
    investment_horizon_years smallint not null check (investment_horizon_years > 0),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.mock_accounts (
    id bigint generated always as identity primary key,
    scenario_id bigint not null references public.mock_scenarios(id) on delete cascade,
    account_type text not null check (account_type in ('dc', 'irp', 'pension_savings')),
    label text not null,
    balance_krw numeric(20, 0) not null check (balance_krw >= 0),
    created_at timestamptz not null default now(),
    unique (scenario_id, account_type, label)
);

create index mock_accounts_scenario_idx on public.mock_accounts (scenario_id);

create table public.mock_holdings (
    id bigint generated always as identity primary key,
    account_id bigint not null references public.mock_accounts(id) on delete cascade,
    asset_class_id bigint not null references public.asset_classes(id) on delete restrict,
    instrument_name text not null,
    market_value_krw numeric(20, 0) not null check (market_value_krw >= 0),
    risk_treatment text not null check (
        risk_treatment in ('capital_preservation', 'general_risky', 'statutory_exception')
    ),
    statutory_exception text check (statutory_exception in ('eligible_tdf', 'default_option')),
    created_at timestamptz not null default now(),
    unique (account_id, instrument_name),
    check (
        (risk_treatment = 'statutory_exception') = (statutory_exception is not null)
    )
);

create index mock_holdings_account_idx on public.mock_holdings (account_id);
create index mock_holdings_asset_class_idx on public.mock_holdings (asset_class_id);

create table public.mock_public_profiles (
    id bigint generated always as identity primary key,
    code text not null unique,
    nickname text not null,
    age_band text not null,
    risk_profile text not null check (risk_profile in ('conservative', 'balanced', 'growth')),
    investment_horizon_years smallint not null check (investment_horizon_years > 0),
    created_at timestamptz not null default now()
);

create table public.mock_public_portfolios (
    id bigint generated always as identity primary key,
    profile_id bigint not null references public.mock_public_profiles(id) on delete cascade,
    snapshot_date date not null,
    title text not null,
    description text not null,
    asset_range_label text not null,
    is_published boolean not null default true,
    created_at timestamptz not null default now(),
    unique (profile_id, snapshot_date)
);

create index mock_public_portfolios_snapshot_idx
    on public.mock_public_portfolios (snapshot_date desc) where is_published;

create table public.mock_public_portfolio_holdings (
    id bigint generated always as identity primary key,
    portfolio_id bigint not null references public.mock_public_portfolios(id) on delete cascade,
    asset_class_id bigint not null references public.asset_classes(id) on delete restrict,
    allocation_percent numeric(7, 4) not null check (allocation_percent >= 0 and allocation_percent <= 100),
    created_at timestamptz not null default now(),
    unique (portfolio_id, asset_class_id)
);

create index mock_public_portfolio_holdings_portfolio_idx
    on public.mock_public_portfolio_holdings (portfolio_id);
create index mock_public_portfolio_holdings_asset_class_idx
    on public.mock_public_portfolio_holdings (asset_class_id);

create table public.rule_sets (
    id bigint generated always as identity primary key,
    code text not null,
    version text not null,
    name text not null,
    status text not null check (status in ('draft', 'active', 'retired')),
    effective_from date not null,
    effective_to date,
    description text not null,
    created_at timestamptz not null default now(),
    unique (code, version),
    check (effective_to is null or effective_to >= effective_from)
);

create unique index rule_sets_one_active_version_idx
    on public.rule_sets (code) where status = 'active';

create table public.pension_rules (
    id bigint generated always as identity primary key,
    rule_set_id bigint not null references public.rule_sets(id) on delete restrict,
    source_id bigint references public.data_sources(id) on delete restrict,
    rule_code text not null,
    account_type text not null check (account_type in ('dc', 'irp', 'pension_savings')),
    rule_kind text not null check (rule_kind in ('risk_cap', 'product_eligibility', 'tax', 'withdrawal')),
    parameters jsonb not null check (jsonb_typeof(parameters) = 'object'),
    rationale text not null,
    source_locator text not null,
    is_exception boolean not null default false,
    created_at timestamptz not null default now(),
    unique (rule_set_id, rule_code, account_type)
);

create index pension_rules_rule_set_idx on public.pension_rules (rule_set_id);
create index pension_rules_source_idx on public.pension_rules (source_id);

create table public.engine_runs (
    id uuid primary key default extensions.gen_random_uuid(),
    owner_id uuid references auth.users(id) on delete cascade,
    scenario_id bigint references public.mock_scenarios(id) on delete set null,
    rule_set_id bigint not null references public.rule_sets(id) on delete restrict,
    engine_name text not null,
    engine_version text not null,
    status text not null check (status in ('running', 'succeeded', 'failed')),
    request_payload jsonb not null check (jsonb_typeof(request_payload) = 'object'),
    result_payload jsonb,
    error_message text,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint engine_runs_completion_check check (
        (status = 'running' and completed_at is null)
        or (status in ('succeeded', 'failed') and completed_at is not null)
    )
);

create index engine_runs_owner_started_idx on public.engine_runs (owner_id, started_at desc);
create index engine_runs_rule_set_idx on public.engine_runs (rule_set_id);
create index engine_runs_scenario_idx on public.engine_runs (scenario_id);

create table public.engine_run_evidence (
    id bigint generated always as identity primary key,
    engine_run_id uuid not null references public.engine_runs(id) on delete cascade,
    evidence_type text not null check (evidence_type in ('rule', 'source', 'disclosure', 'assumption')),
    source_id bigint references public.data_sources(id) on delete restrict,
    rule_id bigint references public.pension_rules(id) on delete restrict,
    source_locator text not null,
    as_of_date date,
    payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
    created_at timestamptz not null default now()
);

create index engine_run_evidence_run_idx on public.engine_run_evidence (engine_run_id);
create index engine_run_evidence_source_idx on public.engine_run_evidence (source_id);
create index engine_run_evidence_rule_idx on public.engine_run_evidence (rule_id);

create table public.knowledge_documents (
    id uuid primary key default extensions.gen_random_uuid(),
    source_id bigint not null references public.data_sources(id) on delete restrict,
    external_id text,
    document_type text not null check (document_type in ('official_guide', 'regulation', 'research', 'product_disclosure', 'news')),
    title text not null,
    publisher text not null,
    source_url text not null,
    published_at timestamptz,
    as_of_date date,
    license_status text not null check (license_status in ('metadata_only', 'permitted', 'review_required')),
    content_hash text,
    content text,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source_id, source_url)
);

create index knowledge_documents_source_published_idx
    on public.knowledge_documents (source_id, published_at desc);

create table public.knowledge_chunks (
    id bigint generated always as identity primary key,
    document_id uuid not null references public.knowledge_documents(id) on delete cascade,
    chunk_index integer not null check (chunk_index >= 0),
    content text not null,
    token_count integer check (token_count is null or token_count >= 0),
    embedding extensions.vector,
    embedding_model text,
    embedding_dimensions integer check (embedding_dimensions is null or embedding_dimensions > 0),
    search_vector tsvector generated always as (to_tsvector('simple', content)) stored,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    unique (document_id, chunk_index),
    check (
        (embedding is null and embedding_model is null and embedding_dimensions is null)
        or (
            embedding is not null
            and embedding_model is not null
            and embedding_dimensions is not null
            and extensions.vector_dims(embedding) = embedding_dimensions
        )
    )
);

create index knowledge_chunks_document_idx on public.knowledge_chunks (document_id);
create index knowledge_chunks_search_idx on public.knowledge_chunks using gin (search_vector);

create table public.news_items (
    id uuid primary key default extensions.gen_random_uuid(),
    source_id bigint not null references public.data_sources(id) on delete restrict,
    ingestion_run_id uuid not null references public.ingestion_runs(id) on delete restrict,
    provider_item_id text,
    search_query text not null,
    title text not null,
    description text,
    publisher text,
    original_url text not null,
    portal_url text,
    published_at timestamptz,
    fetched_at timestamptz not null default now(),
    license_status text not null default 'metadata_only'
        check (license_status in ('metadata_only', 'permitted', 'review_required')),
    raw_metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(raw_metadata) = 'object'),
    unique (source_id, original_url)
);

create index news_items_published_idx on public.news_items (published_at desc);
create index news_items_query_published_idx on public.news_items (search_query, published_at desc);
create index news_items_ingestion_run_idx on public.news_items (ingestion_run_id);

create table public.curated_contents (
    id uuid primary key default extensions.gen_random_uuid(),
    source_id bigint not null references public.data_sources(id) on delete restrict,
    content_type text not null check (content_type in ('daily_guide', 'weekly_macro', 'product_note', 'education')),
    title text not null,
    summary text not null,
    fact_or_opinion text not null check (fact_or_opinion in ('fact', 'scenario', 'service_interpretation')),
    source_url text not null,
    published_at timestamptz,
    as_of_date date not null,
    risk_notes text,
    reviewed_at timestamptz,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now()
);

create index curated_contents_type_as_of_idx
    on public.curated_contents (content_type, as_of_date desc);
create index curated_contents_source_idx on public.curated_contents (source_id);

create table public.chat_sessions (
    id uuid primary key default extensions.gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    title text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index chat_sessions_owner_updated_idx on public.chat_sessions (owner_id, updated_at desc);

create table public.chat_messages (
    id uuid primary key default extensions.gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system', 'tool')),
    content text not null,
    engine_run_id uuid references public.engine_runs(id) on delete set null,
    model_name text,
    created_at timestamptz not null default now()
);

create index chat_messages_session_created_idx on public.chat_messages (session_id, created_at);
create index chat_messages_engine_run_idx on public.chat_messages (engine_run_id);

create table public.chat_message_evidence (
    id bigint generated always as identity primary key,
    message_id uuid not null references public.chat_messages(id) on delete cascade,
    document_id uuid references public.knowledge_documents(id) on delete restrict,
    chunk_id bigint references public.knowledge_chunks(id) on delete restrict,
    news_item_id uuid references public.news_items(id) on delete restrict,
    source_locator text not null,
    quote_text text,
    rank smallint check (rank is null or rank > 0),
    created_at timestamptz not null default now(),
    check (num_nonnulls(document_id, chunk_id, news_item_id) >= 1)
);

create index chat_message_evidence_message_idx on public.chat_message_evidence (message_id);
create index chat_message_evidence_document_idx on public.chat_message_evidence (document_id);
create index chat_message_evidence_chunk_idx on public.chat_message_evidence (chunk_id);
create index chat_message_evidence_news_idx on public.chat_message_evidence (news_item_id);

create or replace function public.search_knowledge_chunks(
    query_text text,
    match_count integer default 8
)
returns table (
    chunk_id bigint,
    document_id uuid,
    title text,
    source_url text,
    content text,
    text_rank real
)
language sql
stable
security invoker
set search_path = ''
as $$
    select
        kc.id,
        kd.id,
        kd.title,
        kd.source_url,
        kc.content,
        ts_rank_cd(kc.search_vector, websearch_to_tsquery('simple', query_text)) as text_rank
    from public.knowledge_chunks as kc
    join public.knowledge_documents as kd on kd.id = kc.document_id
    where query_text <> ''
      and kc.search_vector @@ websearch_to_tsquery('simple', query_text)
    order by text_rank desc, kc.id
    limit greatest(1, least(match_count, 50));
$$;

alter table public.data_sources enable row level security;
alter table public.ingestion_runs enable row level security;
alter table public.financial_institutions enable row level security;
alter table public.institution_aliases enable row level security;
alter table public.pension_savings_provider_stats enable row level security;
alter table public.retirement_provider_stats enable row level security;
alter table public.asset_classes enable row level security;
alter table public.mock_scenarios enable row level security;
alter table public.mock_accounts enable row level security;
alter table public.mock_holdings enable row level security;
alter table public.mock_public_profiles enable row level security;
alter table public.mock_public_portfolios enable row level security;
alter table public.mock_public_portfolio_holdings enable row level security;
alter table public.rule_sets enable row level security;
alter table public.pension_rules enable row level security;
alter table public.engine_runs enable row level security;
alter table public.engine_run_evidence enable row level security;
alter table public.knowledge_documents enable row level security;
alter table public.knowledge_chunks enable row level security;
alter table public.news_items enable row level security;
alter table public.curated_contents enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;
alter table public.chat_message_evidence enable row level security;

create policy engine_runs_select_own on public.engine_runs
    for select to authenticated
    using (owner_id = (select auth.uid()));

create policy engine_run_evidence_select_own on public.engine_run_evidence
    for select to authenticated
    using (
        exists (
            select 1
            from public.engine_runs as er
            where er.id = engine_run_evidence.engine_run_id
              and er.owner_id = (select auth.uid())
        )
    );

create policy chat_sessions_select_own on public.chat_sessions
    for select to authenticated
    using (owner_id = (select auth.uid()));

create policy chat_sessions_insert_own on public.chat_sessions
    for insert to authenticated
    with check (owner_id = (select auth.uid()));

create policy chat_sessions_update_own on public.chat_sessions
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

create policy chat_sessions_delete_own on public.chat_sessions
    for delete to authenticated
    using (owner_id = (select auth.uid()));

create policy chat_messages_select_own on public.chat_messages
    for select to authenticated
    using (
        exists (
            select 1
            from public.chat_sessions as cs
            where cs.id = chat_messages.session_id
              and cs.owner_id = (select auth.uid())
        )
    );

create policy chat_messages_insert_own on public.chat_messages
    for insert to authenticated
    with check (
        exists (
            select 1
            from public.chat_sessions as cs
            where cs.id = chat_messages.session_id
              and cs.owner_id = (select auth.uid())
        )
        and role = 'user'
        and engine_run_id is null
        and model_name is null
    );

create policy chat_message_evidence_select_own on public.chat_message_evidence
    for select to authenticated
    using (
        exists (
            select 1
            from public.chat_messages as cm
            join public.chat_sessions as cs on cs.id = cm.session_id
            where cm.id = chat_message_evidence.message_id
              and cs.owner_id = (select auth.uid())
        )
    );

grant select on public.engine_runs to authenticated;
grant select on public.engine_run_evidence to authenticated;
grant select, insert, update, delete on public.chat_sessions to authenticated;
grant select, insert on public.chat_messages to authenticated;
grant select on public.chat_message_evidence to authenticated;

grant all on table
    public.data_sources,
    public.ingestion_runs,
    public.financial_institutions,
    public.institution_aliases,
    public.pension_savings_provider_stats,
    public.retirement_provider_stats,
    public.asset_classes,
    public.mock_scenarios,
    public.mock_accounts,
    public.mock_holdings,
    public.mock_public_profiles,
    public.mock_public_portfolios,
    public.mock_public_portfolio_holdings,
    public.rule_sets,
    public.pension_rules,
    public.engine_runs,
    public.engine_run_evidence,
    public.knowledge_documents,
    public.knowledge_chunks,
    public.news_items,
    public.curated_contents,
    public.chat_sessions,
    public.chat_messages,
    public.chat_message_evidence
to service_role;

grant usage, select on all sequences in schema public to service_role;
revoke execute on function public.search_knowledge_chunks(text, integer)
    from public, anon, authenticated;
grant execute on function public.search_knowledge_chunks(text, integer) to service_role;

comment on column public.pension_savings_provider_stats.fee_rate_1y is
    'FSS psCorpList feeRate1: 과거 1년 수수료율. 당기 수수료율로 해석하지 않는다.';
comment on column public.retirement_provider_stats.response_division is
    'FSS rpCorpResultList 실제 응답의 division 필드. 공식 문서의 sysType 응답 표기와 다르다.';
comment on column public.knowledge_chunks.embedding is
    '임베딩 모델 확정 전 무차원 vector. 모델 확정 후 차원 제약과 ANN 인덱스를 후속 migration으로 추가한다.';
