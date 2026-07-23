create table public.user_rebalancing_reminder_preferences (
    owner_id uuid primary key references auth.users(id) on delete cascade,
    enabled boolean not null default false,
    enabled_at timestamptz,
    last_reviewed_at timestamptz,
    updated_at timestamptz not null default now(),
    check (not enabled or enabled_at is not null)
);

comment on table public.user_rebalancing_reminder_preferences is
    '[user_pension/live] 사용자 동의 기반 리밸런싱 점검 알림 설정과 마지막 점검 완료 시각';

alter table public.user_rebalancing_reminder_preferences enable row level security;

revoke all on table public.user_rebalancing_reminder_preferences
    from public, anon, authenticated;
grant all on table public.user_rebalancing_reminder_preferences to service_role;
