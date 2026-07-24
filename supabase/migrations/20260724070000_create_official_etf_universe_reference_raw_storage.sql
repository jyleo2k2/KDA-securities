-- KOFIA cost and KIS retirement-eligibility workbooks are official source
-- evidence.  Keep them private; only server-side jobs use the service key.
insert into storage.buckets (id, name, public)
values (
    'official-etf-universe-reference-raw',
    'official-etf-universe-reference-raw',
    false
)
on conflict (id) do update
set public = false;
