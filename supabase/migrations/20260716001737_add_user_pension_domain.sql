-- Additive user/profile/account domain foundation.
-- Existing mock tables remain intact until a separately reviewed backfill and
-- repository cutover prove result equivalence.

create table public.user_profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    nickname text check (nickname is null or length(btrim(nickname)) between 1 and 50),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.profile_question_sets (
    id bigint generated always as identity primary key,
    version text not null unique,
    status text not null check (status in ('draft', 'active', 'retired')),
    effective_from date not null,
    effective_to date,
    engine_name text not null,
    engine_version text not null,
    rule_version text not null,
    provisional boolean not null default true,
    created_at timestamptz not null default now(),
    check (effective_to is null or effective_to >= effective_from)
);

create unique index profile_question_sets_one_active_idx
    on public.profile_question_sets ((status)) where status = 'active';

create table public.profile_questions (
    id bigint generated always as identity primary key,
    question_set_id bigint not null
        references public.profile_question_sets(id) on delete restrict,
    code text not null,
    topic text not null,
    display_order smallint not null check (display_order > 0),
    created_at timestamptz not null default now(),
    unique (question_set_id, code),
    unique (question_set_id, display_order)
);

create index profile_questions_question_set_idx
    on public.profile_questions (question_set_id);

create table public.profile_question_options (
    id bigint generated always as identity primary key,
    question_id bigint not null
        references public.profile_questions(id) on delete restrict,
    answer_value text not null,
    label text not null,
    score smallint not null check (score between 1 and 5),
    display_order smallint not null check (display_order > 0),
    created_at timestamptz not null default now(),
    unique (question_id, answer_value),
    unique (question_id, display_order),
    unique (id, question_id)
);

create index profile_question_options_question_idx
    on public.profile_question_options (question_id);

create table public.investment_profile_assessments (
    id uuid primary key default extensions.gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    question_set_id bigint not null
        references public.profile_question_sets(id) on delete restrict,
    total_score smallint not null,
    min_score smallint not null,
    max_score smallint not null,
    score_percent numeric(5, 2) not null check (score_percent between 0 and 100),
    risk_profile text not null check (
        risk_profile in ('stable', 'stable_seeking', 'risk_neutral', 'active', 'aggressive')
    ),
    engine_name text not null,
    engine_version text not null,
    rule_version text not null,
    provisional boolean not null,
    assessed_at timestamptz not null default now(),
    check (max_score > min_score),
    check (total_score between min_score and max_score)
);

create index investment_profile_assessments_owner_assessed_idx
    on public.investment_profile_assessments (owner_id, assessed_at desc);
create index investment_profile_assessments_question_set_idx
    on public.investment_profile_assessments (question_set_id);

create table public.investment_profile_answers (
    id bigint generated always as identity primary key,
    assessment_id uuid not null
        references public.investment_profile_assessments(id) on delete cascade,
    question_id bigint not null
        references public.profile_questions(id) on delete restrict,
    option_id bigint not null,
    selected_value text not null,
    selected_label text not null,
    selected_score smallint not null check (selected_score between 1 and 5),
    created_at timestamptz not null default now(),
    unique (assessment_id, question_id),
    foreign key (option_id, question_id)
        references public.profile_question_options(id, question_id) on delete restrict
);

create index investment_profile_answers_assessment_idx
    on public.investment_profile_answers (assessment_id);
create index investment_profile_answers_question_idx
    on public.investment_profile_answers (question_id);
create index investment_profile_answers_option_idx
    on public.investment_profile_answers (option_id);

create table public.pension_accounts (
    id uuid primary key default extensions.gen_random_uuid(),
    owner_id uuid references auth.users(id) on delete cascade,
    scenario_id bigint references public.mock_scenarios(id) on delete restrict,
    institution_id bigint references public.financial_institutions(id) on delete restrict,
    account_type text not null check (account_type in ('dc', 'irp', 'pension_savings')),
    account_name text not null check (length(btrim(account_name)) > 0),
    data_kind text not null check (data_kind in ('real', 'mock')),
    origin text not null check (origin in ('user_input', 'provider_import', 'synthetic')),
    opened_on date,
    closed_on date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (closed_on is null or opened_on is null or closed_on >= opened_on),
    check (
        (data_kind = 'real' and owner_id is not null and scenario_id is null)
        or (data_kind = 'mock' and owner_id is null and scenario_id is not null)
    ),
    check (
        (data_kind = 'real' and origin in ('user_input', 'provider_import'))
        or (data_kind = 'mock' and origin = 'synthetic')
    )
);

create index pension_accounts_owner_idx on public.pension_accounts (owner_id);
create index pension_accounts_scenario_idx on public.pension_accounts (scenario_id);
create index pension_accounts_institution_idx on public.pension_accounts (institution_id);

create table public.account_snapshots (
    id uuid primary key default extensions.gen_random_uuid(),
    account_id uuid not null references public.pension_accounts(id) on delete cascade,
    as_of_date date not null,
    contributed_principal_krw numeric(20, 0) not null
        check (contributed_principal_krw >= 0),
    market_value_krw numeric(20, 0) not null check (market_value_krw >= 0),
    source_id bigint references public.data_sources(id) on delete restrict,
    origin text not null check (origin in ('user_input', 'provider_import', 'synthetic')),
    captured_at timestamptz not null default now(),
    unique (account_id, as_of_date)
);

create index account_snapshots_account_as_of_idx
    on public.account_snapshots (account_id, as_of_date desc);
create index account_snapshots_source_idx on public.account_snapshots (source_id);

create table public.account_cash_flows (
    id uuid primary key default extensions.gen_random_uuid(),
    account_id uuid not null references public.pension_accounts(id) on delete cascade,
    occurred_on date not null,
    flow_type text not null check (
        flow_type in ('contribution', 'withdrawal', 'transfer_in', 'transfer_out')
    ),
    amount_krw numeric(20, 0) not null check (amount_krw > 0),
    source_id bigint references public.data_sources(id) on delete restrict,
    origin text not null check (origin in ('user_input', 'provider_import', 'synthetic')),
    external_reference text,
    created_at timestamptz not null default now()
);

create index account_cash_flows_account_occurred_idx
    on public.account_cash_flows (account_id, occurred_on);
create index account_cash_flows_source_idx on public.account_cash_flows (source_id);

create table public.financial_products (
    id uuid primary key default extensions.gen_random_uuid(),
    institution_id bigint not null
        references public.financial_institutions(id) on delete restrict,
    external_code text,
    product_name text not null check (length(btrim(product_name)) > 0),
    product_type text not null check (length(btrim(product_type)) > 0),
    asset_class_id bigint not null references public.asset_classes(id) on delete restrict,
    risk_treatment text not null check (
        risk_treatment in ('capital_preservation', 'general_risky', 'statutory_exception')
    ),
    statutory_exception text check (
        statutory_exception in ('eligible_tdf', 'default_option')
    ),
    data_kind text not null check (data_kind in ('real', 'synthetic')),
    source_id bigint references public.data_sources(id) on delete restrict,
    as_of_date date,
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (
        (risk_treatment = 'statutory_exception' and statutory_exception is not null)
        or (risk_treatment <> 'statutory_exception' and statutory_exception is null)
    ),
    check (
        (data_kind = 'real' and source_id is not null)
        or data_kind = 'synthetic'
    )
);

create unique index financial_products_institution_external_code_idx
    on public.financial_products (institution_id, external_code)
    where external_code is not null;
create index financial_products_institution_idx
    on public.financial_products (institution_id);
create index financial_products_asset_class_idx on public.financial_products (asset_class_id);
create index financial_products_source_idx on public.financial_products (source_id);

create table public.account_holding_snapshots (
    id uuid primary key default extensions.gen_random_uuid(),
    snapshot_id uuid not null references public.account_snapshots(id) on delete cascade,
    product_id uuid references public.financial_products(id) on delete restrict,
    raw_instrument_name text,
    asset_class_id bigint not null references public.asset_classes(id) on delete restrict,
    market_value_krw numeric(20, 0) not null check (market_value_krw >= 0),
    risk_treatment text not null check (
        risk_treatment in ('capital_preservation', 'general_risky', 'statutory_exception')
    ),
    statutory_exception text check (
        statutory_exception in ('eligible_tdf', 'default_option')
    ),
    source_id bigint references public.data_sources(id) on delete restrict,
    origin text not null check (origin in ('user_input', 'provider_import', 'synthetic')),
    created_at timestamptz not null default now(),
    check (
        product_id is not null
        or coalesce(length(btrim(raw_instrument_name)), 0) > 0
    ),
    check (
        (risk_treatment = 'statutory_exception' and statutory_exception is not null)
        or (risk_treatment <> 'statutory_exception' and statutory_exception is null)
    )
);

create index account_holding_snapshots_snapshot_idx
    on public.account_holding_snapshots (snapshot_id);
create index account_holding_snapshots_product_idx
    on public.account_holding_snapshots (product_id);
create index account_holding_snapshots_asset_class_idx
    on public.account_holding_snapshots (asset_class_id);
create index account_holding_snapshots_source_idx
    on public.account_holding_snapshots (source_id);

-- The already-applied idempotency table has a session FK without a supporting
-- index. Add it here rather than altering its immutable migration history.
create index chat_request_idempotency_session_idx
    on public.chat_request_idempotency (session_id);

alter table public.user_profiles enable row level security;
alter table public.profile_question_sets enable row level security;
alter table public.profile_questions enable row level security;
alter table public.profile_question_options enable row level security;
alter table public.investment_profile_assessments enable row level security;
alter table public.investment_profile_answers enable row level security;
alter table public.pension_accounts enable row level security;
alter table public.account_snapshots enable row level security;
alter table public.account_cash_flows enable row level security;
alter table public.financial_products enable row level security;
alter table public.account_holding_snapshots enable row level security;

create policy user_profiles_select_own on public.user_profiles
    for select to authenticated
    using (user_id = (select auth.uid()));
create policy user_profiles_insert_own on public.user_profiles
    for insert to authenticated
    with check (user_id = (select auth.uid()));
create policy user_profiles_update_own on public.user_profiles
    for update to authenticated
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));
create policy user_profiles_delete_own on public.user_profiles
    for delete to authenticated
    using (user_id = (select auth.uid()));

create policy investment_profile_assessments_select_own
    on public.investment_profile_assessments
    for select to authenticated
    using (owner_id = (select auth.uid()));
create policy investment_profile_assessments_insert_own
    on public.investment_profile_assessments
    for insert to authenticated
    with check (owner_id = (select auth.uid()));
create policy investment_profile_assessments_update_own
    on public.investment_profile_assessments
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));
create policy investment_profile_assessments_delete_own
    on public.investment_profile_assessments
    for delete to authenticated
    using (owner_id = (select auth.uid()));

create policy investment_profile_answers_select_own
    on public.investment_profile_answers
    for select to authenticated
    using (
        exists (
            select 1
            from public.investment_profile_assessments as ipa
            where ipa.id = investment_profile_answers.assessment_id
              and ipa.owner_id = (select auth.uid())
        )
    );
create policy investment_profile_answers_insert_own
    on public.investment_profile_answers
    for insert to authenticated
    with check (
        exists (
            select 1
            from public.investment_profile_assessments as ipa
            where ipa.id = investment_profile_answers.assessment_id
              and ipa.owner_id = (select auth.uid())
        )
    );
create policy investment_profile_answers_update_own
    on public.investment_profile_answers
    for update to authenticated
    using (
        exists (
            select 1
            from public.investment_profile_assessments as ipa
            where ipa.id = investment_profile_answers.assessment_id
              and ipa.owner_id = (select auth.uid())
        )
    )
    with check (
        exists (
            select 1
            from public.investment_profile_assessments as ipa
            where ipa.id = investment_profile_answers.assessment_id
              and ipa.owner_id = (select auth.uid())
        )
    );
create policy investment_profile_answers_delete_own
    on public.investment_profile_answers
    for delete to authenticated
    using (
        exists (
            select 1
            from public.investment_profile_assessments as ipa
            where ipa.id = investment_profile_answers.assessment_id
              and ipa.owner_id = (select auth.uid())
        )
    );

create policy pension_accounts_select_own on public.pension_accounts
    for select to authenticated
    using (data_kind = 'real' and owner_id = (select auth.uid()));
create policy pension_accounts_insert_own on public.pension_accounts
    for insert to authenticated
    with check (data_kind = 'real' and owner_id = (select auth.uid()));
create policy pension_accounts_update_own on public.pension_accounts
    for update to authenticated
    using (data_kind = 'real' and owner_id = (select auth.uid()))
    with check (data_kind = 'real' and owner_id = (select auth.uid()));
create policy pension_accounts_delete_own on public.pension_accounts
    for delete to authenticated
    using (data_kind = 'real' and owner_id = (select auth.uid()));

create policy account_snapshots_select_own on public.account_snapshots
    for select to authenticated
    using (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_snapshots.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_snapshots_insert_own on public.account_snapshots
    for insert to authenticated
    with check (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_snapshots.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_snapshots_update_own on public.account_snapshots
    for update to authenticated
    using (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_snapshots.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    )
    with check (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_snapshots.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_snapshots_delete_own on public.account_snapshots
    for delete to authenticated
    using (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_snapshots.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );

create policy account_cash_flows_select_own on public.account_cash_flows
    for select to authenticated
    using (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_cash_flows.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_cash_flows_insert_own on public.account_cash_flows
    for insert to authenticated
    with check (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_cash_flows.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_cash_flows_update_own on public.account_cash_flows
    for update to authenticated
    using (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_cash_flows.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    )
    with check (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_cash_flows.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_cash_flows_delete_own on public.account_cash_flows
    for delete to authenticated
    using (
        exists (
            select 1 from public.pension_accounts as pa
            where pa.id = account_cash_flows.account_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );

create policy account_holding_snapshots_select_own
    on public.account_holding_snapshots
    for select to authenticated
    using (
        exists (
            select 1
            from public.account_snapshots as acs
            join public.pension_accounts as pa on pa.id = acs.account_id
            where acs.id = account_holding_snapshots.snapshot_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_holding_snapshots_insert_own
    on public.account_holding_snapshots
    for insert to authenticated
    with check (
        exists (
            select 1
            from public.account_snapshots as acs
            join public.pension_accounts as pa on pa.id = acs.account_id
            where acs.id = account_holding_snapshots.snapshot_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_holding_snapshots_update_own
    on public.account_holding_snapshots
    for update to authenticated
    using (
        exists (
            select 1
            from public.account_snapshots as acs
            join public.pension_accounts as pa on pa.id = acs.account_id
            where acs.id = account_holding_snapshots.snapshot_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    )
    with check (
        exists (
            select 1
            from public.account_snapshots as acs
            join public.pension_accounts as pa on pa.id = acs.account_id
            where acs.id = account_holding_snapshots.snapshot_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );
create policy account_holding_snapshots_delete_own
    on public.account_holding_snapshots
    for delete to authenticated
    using (
        exists (
            select 1
            from public.account_snapshots as acs
            join public.pension_accounts as pa on pa.id = acs.account_id
            where acs.id = account_holding_snapshots.snapshot_id
              and pa.data_kind = 'real'
              and pa.owner_id = (select auth.uid())
        )
    );

-- FastAPI remains the only supported data path for these tables. Ownership
-- policies are defense in depth and prepare a later, explicit Data API grant.
revoke all privileges on table
    public.user_profiles,
    public.profile_question_sets,
    public.profile_questions,
    public.profile_question_options,
    public.investment_profile_assessments,
    public.investment_profile_answers,
    public.pension_accounts,
    public.account_snapshots,
    public.account_cash_flows,
    public.financial_products,
    public.account_holding_snapshots
from public, anon, authenticated;

grant all privileges on table
    public.user_profiles,
    public.profile_question_sets,
    public.profile_questions,
    public.profile_question_options,
    public.investment_profile_assessments,
    public.investment_profile_answers,
    public.pension_accounts,
    public.account_snapshots,
    public.account_cash_flows,
    public.financial_products,
    public.account_holding_snapshots
to service_role;

grant usage, select on all sequences in schema public to service_role;

-- Reference data mirrors backend/app/engine/profile.py exactly. The generic
-- 1-to-5 labels remain provisional until the team approves final survey copy.
with inserted_set as (
    insert into public.profile_question_sets (
        version,
        status,
        effective_from,
        engine_name,
        engine_version,
        rule_version,
        provisional
    ) values (
        '2026-07-15-provisional',
        'active',
        date '2026-07-15',
        'investor_profile',
        '2026-07-15.1',
        '2026-07-15-provisional',
        true
    )
    returning id
), inserted_questions as (
    insert into public.profile_questions (question_set_id, code, topic, display_order)
    select inserted_set.id, question.code, question.topic, question.display_order
    from inserted_set
    cross join (
        values
            ('investment_horizon', '투자 예정 기간', 1),
            ('investment_experience', '투자 경험', 2),
            ('financial_knowledge', '금융상품 지식 수준', 3),
            ('risky_asset_share', '현재 위험자산 비중', 4),
            ('loss_tolerance', '감내 가능한 손실 수준', 5),
            ('income_stability', '소득 안정성', 6)
    ) as question(code, topic, display_order)
    returning id
)
insert into public.profile_question_options (
    question_id,
    answer_value,
    label,
    score,
    display_order
)
select
    inserted_questions.id,
    'score_' || score.value,
    score.value || '점',
    score.value,
    score.value
from inserted_questions
cross join generate_series(1, 5) as score(value);
