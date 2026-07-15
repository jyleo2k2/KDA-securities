-- One owner can persist a given client-generated request only once.
-- The API serializes same-key retries with an advisory transaction lock; the
-- unique constraint remains the durable database backstop.
create table public.chat_request_idempotency (
    id uuid primary key default extensions.gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    idempotency_key uuid not null,
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    user_message_id uuid not null references public.chat_messages(id) on delete cascade,
    assistant_message_id uuid not null references public.chat_messages(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (owner_id, idempotency_key),
    unique (user_message_id),
    unique (assistant_message_id)
);

create index chat_request_idempotency_owner_created_idx
    on public.chat_request_idempotency (owner_id, created_at desc);

alter table public.chat_request_idempotency enable row level security;

-- Browser clients never need this internal replay ledger.  The authenticated
-- API owns writes through its server-side database connection.
revoke all on table public.chat_request_idempotency from public, anon, authenticated;
grant all on table public.chat_request_idempotency to service_role;
