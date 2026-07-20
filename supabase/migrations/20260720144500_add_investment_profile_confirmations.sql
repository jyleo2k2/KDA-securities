create table public.investment_profile_confirmations (
    id uuid primary key default extensions.gen_random_uuid(),
    assessment_id uuid not null unique
        references public.investment_profile_assessments(id) on delete cascade,
    owner_id uuid not null references auth.users(id) on delete cascade,
    investment_advice_desired boolean not null,
    investor_information_provided boolean not null,
    policy_version text not null,
    confirmed_at timestamptz not null default now(),
    check (not (not investor_information_provided and investment_advice_desired))
);

create index investment_profile_confirmations_owner_confirmed_idx
    on public.investment_profile_confirmations (owner_id, confirmed_at desc);

alter table public.investment_profile_confirmations enable row level security;

create policy investment_profile_confirmations_select_own
    on public.investment_profile_confirmations
    for select to authenticated
    using (owner_id = (select auth.uid()));

create policy investment_profile_confirmations_insert_own
    on public.investment_profile_confirmations
    for insert to authenticated
    with check (owner_id = (select auth.uid()));

revoke all on table public.investment_profile_confirmations
    from public, anon, authenticated;
grant all on table public.investment_profile_confirmations to service_role;
