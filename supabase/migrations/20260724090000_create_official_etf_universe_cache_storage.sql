-- Compact operational ETF cache files are server-side audit evidence.
-- Keep the bucket private; Storage service-role access bypasses RLS and no
-- browser policy is created here.
insert into storage.buckets (id, name, public)
values (
    'official-etf-universe-cache',
    'official-etf-universe-cache',
    false
)
on conflict (id) do update
set public = false;
