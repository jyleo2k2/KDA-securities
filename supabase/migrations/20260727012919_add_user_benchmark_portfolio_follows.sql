create table public.benchmark_follow_targets (
    portfolio_id text primary key,
    initial_follow_count integer not null check (initial_follow_count >= 0),
    display_order smallint not null unique check (display_order > 0),
    created_at timestamptz not null default now()
);

comment on table public.benchmark_follow_targets is
    '[benchmark/live] 이용자 Pick 팔로우 대상과 화면 도입 전 기준 팔로우 수';

create table public.user_benchmark_portfolio_follows (
    owner_id uuid not null references auth.users(id) on delete cascade,
    portfolio_id text not null
        references public.benchmark_follow_targets(portfolio_id) on delete cascade,
    followed_at timestamptz not null default now(),
    primary key (owner_id, portfolio_id)
);

comment on table public.user_benchmark_portfolio_follows is
    '[user_pension/live] 인증 이용자의 이용자 Pick 포트폴리오 팔로우 상태';

create index user_benchmark_portfolio_follows_portfolio_idx
    on public.user_benchmark_portfolio_follows (portfolio_id);

insert into public.benchmark_follow_targets (
    portfolio_id,
    initial_follow_count,
    display_order
)
values
    ('꾸준한거북이', 1204, 1),
    ('배당모으미', 876, 2),
    ('느긋한바벨러', 642, 3),
    ('중립러버', 415, 4),
    ('초보투자자', 37, 5);

alter table public.benchmark_follow_targets enable row level security;
alter table public.user_benchmark_portfolio_follows enable row level security;

revoke all on table public.benchmark_follow_targets
    from public, anon, authenticated;
revoke all on table public.user_benchmark_portfolio_follows
    from public, anon, authenticated;

grant all on table public.benchmark_follow_targets to service_role;
grant all on table public.user_benchmark_portfolio_follows to service_role;
