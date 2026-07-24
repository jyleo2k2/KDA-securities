-- Verified, descriptive historical news-event outcomes only.  They must never
-- serve as allocation, rebalancing, or order inputs.
create table public.news_event_outcomes (
    id bigint generated always as identity primary key,
    event_key text not null,
    occurred_on date not null,
    theme_id text not null check (theme_id ~ '^[a-z0-9_]+$'),
    isu_code text not null,
    isu_name text not null,
    horizon_months smallint not null check (horizon_months in (1, 3, 6)),
    start_date date not null,
    end_date date not null check (end_date > start_date),
    total_return_percent numeric not null,
    maximum_drawdown_percent numeric not null check (maximum_drawdown_percent >= 0),
    peer_median_total_return_percent numeric not null,
    peer_sample_count integer not null check (peer_sample_count > 0),
    event_source_url text not null check (event_source_url ~ '^https://'),
    event_source_label text not null,
    event_source_as_of date,
    history_source text not null,
    history_source_url text not null check (history_source_url ~ '^https://'),
    history_source_as_of date,
    engine_name text not null,
    engine_version text not null,
    policy_version text not null,
    report_sha256 text not null check (report_sha256 ~ '^[0-9a-f]{64}$'),
    loaded_at timestamptz not null default now(),
    unique (event_key, isu_code, horizon_months)
);

create index news_event_outcomes_theme_occurred_idx
    on public.news_event_outcomes (theme_id, occurred_on desc, horizon_months);

alter table public.news_event_outcomes enable row level security;

revoke all on table public.news_event_outcomes from public, anon, authenticated;
grant select, insert, update, delete on table public.news_event_outcomes to service_role;
grant usage, select on sequence public.news_event_outcomes_id_seq to service_role;
