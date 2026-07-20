alter table public.news_items
    add column if not exists is_active boolean not null default true;

drop index if exists public.news_items_market_recent_idx;

create index news_items_market_recent_idx
    on public.news_items (published_at desc, fetched_at desc, id)
    where selection_policy_version is not null
      and summary_status = 'succeeded'
      and is_active;
