-- Internal, append-only cost observations for chatbot LLM calls. The ledger
-- deliberately excludes prompts, responses, user ids and session ids.
create table public.llm_usage_events (
    id bigint generated always as identity primary key,
    occurred_at timestamptz not null default now(),
    call_kind text not null check (
        call_kind in (
            'narration',
            'narration_prewarm',
            'topic_guard',
            'etf_product_feature'
        )
    ),
    intent text check (
        intent is null or intent ~ '^[a-z0-9_]+$'
    ),
    provider text not null check (
        provider in ('anthropic', 'google')
    ),
    model_name text not null check (
        length(model_name) between 1 and 128
    ),
    outcome text not null check (
        outcome in (
            'accepted',
            'cache_hit',
            'provider_error',
            'validation_rejected'
        )
    ),
    outcome_detail text check (
        outcome_detail is null or outcome_detail ~ '^[a-z0-9_]+$'
    ),
    provider_called boolean not null,
    application_cache_hit boolean not null default false,
    usage_available boolean not null,
    request_count integer not null default 0 check (request_count >= 0),
    input_tokens bigint not null default 0 check (input_tokens >= 0),
    output_tokens bigint not null default 0 check (output_tokens >= 0),
    cache_read_tokens bigint not null default 0 check (cache_read_tokens >= 0),
    cache_write_tokens bigint not null default 0 check (cache_write_tokens >= 0),
    latency_ms integer check (latency_ms is null or latency_ms >= 0),
    estimated_list_cost_usd numeric(20, 12) check (
        estimated_list_cost_usd is null or estimated_list_cost_usd >= 0
    ),
    pricing_version text,
    input_price_per_mtok_usd numeric(12, 6) check (
        input_price_per_mtok_usd is null or input_price_per_mtok_usd >= 0
    ),
    output_price_per_mtok_usd numeric(12, 6) check (
        output_price_per_mtok_usd is null or output_price_per_mtok_usd >= 0
    ),
    check (
        (application_cache_hit and not provider_called and outcome = 'cache_hit')
        or (not application_cache_hit and provider_called and outcome <> 'cache_hit')
    )
);

comment on table public.llm_usage_events is
    '[operations/internal] 챗봇 LLM 토큰 사용량과 정가 기준 예상 비용 장부';
comment on column public.llm_usage_events.estimated_list_cost_usd is
    '호출 당시 버전 단가로 계산한 정가 추정치이며 실제 청구액이 아님';

create index llm_usage_events_occurred_at_idx
    on public.llm_usage_events (occurred_at desc);
create index llm_usage_events_kind_occurred_idx
    on public.llm_usage_events (call_kind, occurred_at desc);
create index llm_usage_events_model_occurred_idx
    on public.llm_usage_events (model_name, occurred_at desc);

alter table public.llm_usage_events enable row level security;

revoke all on table public.llm_usage_events from public, anon, authenticated;
grant select, insert on table public.llm_usage_events to service_role;
grant usage, select on sequence public.llm_usage_events_id_seq to service_role;

create view public.llm_usage_daily_summary
with (security_invoker = true)
as
select
    (occurred_at at time zone 'Asia/Seoul')::date as usage_date_kst,
    call_kind,
    intent,
    provider,
    model_name,
    count(*) as observed_event_count,
    count(*) filter (where provider_called) as provider_call_count,
    count(*) filter (where application_cache_hit) as application_cache_hit_count,
    count(*) filter (
        where provider_called and not usage_available
    ) as usage_missing_call_count,
    count(*) filter (
        where provider_called and estimated_list_cost_usd is null
    ) as unpriced_call_count,
    count(*) filter (
        where outcome = 'validation_rejected'
    ) as validation_rejected_count,
    coalesce(sum(request_count), 0) as request_count,
    coalesce(sum(input_tokens), 0) as input_tokens,
    coalesce(sum(output_tokens), 0) as output_tokens,
    coalesce(sum(cache_read_tokens), 0) as cache_read_tokens,
    coalesce(sum(cache_write_tokens), 0) as cache_write_tokens,
    case
        when count(*) filter (
            where provider_called and estimated_list_cost_usd is null
        ) > 0 then null
        else coalesce(sum(estimated_list_cost_usd), 0)
    end as estimated_list_cost_usd,
    round(avg(latency_ms) filter (where provider_called), 1) as average_latency_ms,
    round(
        (
            percentile_cont(0.95) within group (order by latency_ms)
                filter (where provider_called)
        )::numeric,
        1
    ) as p95_latency_ms
from public.llm_usage_events
group by
    (occurred_at at time zone 'Asia/Seoul')::date,
    call_kind,
    intent,
    provider,
    model_name;

comment on view public.llm_usage_daily_summary is
    '[operations/internal] KST 일자·호출 종류·모델별 LLM 사용량과 예상 비용 집계';

revoke all on table public.llm_usage_daily_summary
    from public, anon, authenticated;
grant select on table public.llm_usage_daily_summary to service_role;
