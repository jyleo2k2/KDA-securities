from pathlib import Path

from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_initial_data_foundation.sql")
)
DATA_API_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_tighten_data_api_grants.sql")
)
EMBEDDING_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_fix_embedding_dimension_bge_m3.sql")
)
IDEMPOTENCY_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_chat_request_idempotency.sql")
)
IDEMPOTENCY_POLICY_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_chat_idempotency_deny_policy.sql"
    )
)
USER_PENSION_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_user_pension_domain.sql")
)
PROFILE_ANSWER_FK_INDEX_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_profile_answer_fk_index.sql")
)
NEWS_SUMMARY_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_news_article_summaries.sql")
)
LIFECYCLE_SCENARIOS_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_lifecycle_demo_scenarios.sql")
)
ETF_UNIVERSE_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_etf_portfolio_universe.sql")
)
ETF_MARKET_SNAPSHOT_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_krx_etf_daily_market_snapshots.sql"
    )
)
ETF_THEME_VERIFICATION_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_etf_theme_content_verification.sql"
    ),
    None,
)
ETF_PRODUCT_DESCRIPTION_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_etf_product_descriptions.sql"
    ),
    None,
)
ETF_COMPONENT_SNAPSHOT_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_add_etf_component_snapshots.sql")
)
ETF_DISTRIBUTION_RAW_STORAGE_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_create_official_etf_distribution_raw_storage.sql"
    ),
    None,
)
ETF_UNIVERSE_CACHE_STORAGE_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_create_official_etf_universe_cache_storage.sql"
    ),
    None,
)
OFFICIAL_ETF_COMPONENT_SOURCE_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_official_etf_component_sources.sql"
    ),
    None,
)
OFFICIAL_ETF_BINDING_SOURCE_INDEX_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_official_etf_binding_source_index.sql"
    ),
    None,
)
HERO_ETF_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260718090000_link_demo_hero_etf_holdings.sql"
)
MOCK_ACCOUNT_BACKFILL_MIGRATION_GLOB = "*_backfill_mock_pension_accounts.sql"
DEMO_ETF_COMMON_SYNC_MIGRATION_GLOB = (
    "*_sync_demo_etf_holdings_to_common_accounts.sql"
)
DEMO_CUSTOMER_CONTRACT_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_unify_demo_customer_contract.sql")
)
BENCHMARK_LOADER = ROOT / "scripts" / "load_benchmark_mock_data.py"
DEMO_AUTH_PROVISIONER = ROOT / "scripts" / "provision_demo_auth_users.py"
DEMO_SQL_RENDERER = ROOT / "scripts" / "render_demo_customer_sql.py"
SEED = ROOT / "supabase" / "seed.sql"
SCHEMA_ADDITIVE_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_updated_at_triggers_and_holding_constraints.sql"
    )
)
BENCHMARK_SCHEMA_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_move_benchmark_tables_to_schema.sql")
)
BENCHMARK_SCHEMA_CLEANUP_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_drop_benchmark_public_compatibility_views.sql"
    )
)
REBALANCING_REMINDER_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_rebalancing_reminder_preferences.sql"
    )
)
BENCHMARK_FOLLOW_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_user_benchmark_portfolio_follows.sql"
    )
)
NEWS_EVENT_OUTCOME_LEDGER_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_news_event_outcome_ledger.sql"
    )
)


def test_benchmark_follows_are_owner_scoped_and_server_only() -> None:
    sql = BENCHMARK_FOLLOW_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.benchmark_follow_targets" in sql
    assert "create table public.user_benchmark_portfolio_follows" in sql
    assert (
        "primary key (owner_id, portfolio_id)" in sql
    )
    assert "references auth.users(id) on delete cascade" in sql
    assert "references public.benchmark_follow_targets(portfolio_id)" in sql
    assert "initial_follow_count integer not null" in sql
    assert (
        "alter table public.benchmark_follow_targets enable row level security"
        in sql
    )
    assert (
        "alter table public.user_benchmark_portfolio_follows "
        "enable row level security"
        in sql
    )
    assert sql.count("from public, anon, authenticated") == 2
    assert sql.count("to service_role") == 2
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_news_event_outcome_ledger_is_server_only_and_descriptive() -> None:
    sql = NEWS_EVENT_OUTCOME_LEDGER_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.news_event_outcomes" in sql
    assert "horizon_months in (1, 3, 6)" in sql
    assert "peer_median_total_return_percent" in sql
    assert "peer_sample_count" in sql
    assert "alter table public.news_event_outcomes enable row level security" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_rebalancing_reminder_preferences_are_owner_scoped_and_server_only() -> None:
    sql = REBALANCING_REMINDER_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.user_rebalancing_reminder_preferences" in sql
    assert (
        "owner_id uuid primary key references auth.users(id) on delete cascade" in sql
    )
    assert "enabled boolean not null default false" in sql
    assert "last_reviewed_at timestamptz" in sql
    assert "moddatetime" not in sql
    assert (
        "alter table public.user_rebalancing_reminder_preferences "
        "enable row level security"
        in sql
    )
    assert "from public, anon, authenticated" in sql
    assert (
        "grant all on table public.user_rebalancing_reminder_preferences "
        "to service_role" in sql
    )
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_benchmark_schema_move_is_additive_and_service_role_only() -> None:
    sql = BENCHMARK_SCHEMA_MIGRATION.read_text(encoding="utf-8").lower()
    tables = (
        "benchmark_mock_users",
        "benchmark_mock_accounts",
        "benchmark_mock_holdings",
    )
    assert "create schema if not exists benchmark" in sql
    assert "grant usage on schema benchmark to service_role" in sql
    for table in tables:
        assert f"alter table public.{table} set schema benchmark" in sql
        assert f"create view public.{table}" in sql
        assert f"select * from benchmark.{table}" in sql
    assert sql.count("security_invoker = true") == 3
    assert "grant select on public.benchmark_mock_users" in sql
    assert "to service_role" in sql
    assert "drop table" not in sql
    assert "delete from" not in sql
    assert "truncate" not in sql


def test_benchmark_schema_cleanup_drops_only_compatibility_views() -> None:
    sql = BENCHMARK_SCHEMA_CLEANUP_MIGRATION.read_text(encoding="utf-8").lower()
    for table in (
        "benchmark_mock_users",
        "benchmark_mock_accounts",
        "benchmark_mock_holdings",
    ):
        assert f"drop view public.{table}" in sql
    assert "drop table" not in sql
    assert "delete from" not in sql
    assert "truncate" not in sql


def test_schema_has_required_data_foundation_groups() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    required_tables = {
        "data_sources",
        "ingestion_runs",
        "pension_savings_provider_stats",
        "retirement_provider_stats",
        "mock_scenarios",
        "mock_accounts",
        "mock_holdings",
        "rule_sets",
        "pension_rules",
        "engine_runs",
        "engine_run_evidence",
        "knowledge_documents",
        "knowledge_chunks",
        "news_items",
        "chat_sessions",
        "chat_messages",
        "chat_message_evidence",
    }

    for table in required_tables:
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql


def test_rag_foundation_has_vector_and_full_text_search() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "embedding extensions.vector" in sql
    assert "search_vector tsvector generated always" in sql
    assert "using gin (search_vector)" in sql
    assert "search_knowledge_chunks" in sql


def test_disclosure_contract_does_not_invent_current_fee_rate() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "fee_rate_1y" in sql
    assert "fee_rate_current" not in sql
    assert "not (requested_params ? 'key')" in sql
    assert "news_items_ingestion_run_idx" in sql


def test_authenticated_users_cannot_forge_engine_results() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create policy engine_runs_insert_own" not in sql
    assert "grant select, insert on public.engine_runs" not in sql
    assert "and role = 'user'" in sql
    assert "and engine_run_id is null" in sql
    assert "and model_name is null" in sql
    assert "revoke execute on function public.search_knowledge_chunks" in sql
    assert "extensions.vector_dims(embedding) = embedding_dimensions" in sql


def test_data_api_privileges_are_least_privilege() -> None:
    sql = DATA_API_MIGRATION.read_text(encoding="utf-8").lower()

    assert "from public, anon, authenticated" in sql
    assert "revoke all privileges on all sequences" in sql
    assert "alter default privileges for role postgres" in sql
    assert "grant select, insert, update, delete on table public.chat_sessions" in sql
    assert "grant select, insert on table public.chat_messages" in sql
    assert "grant select on table public.chat_message_evidence" in sql
    assert "public.knowledge_chunks" in sql
    assert "to service_role" in sql


def test_embedding_migration_fixes_bge_m3_dimension() -> None:
    sql = EMBEDDING_MIGRATION.read_text(encoding="utf-8").lower()

    assert "extensions.vector(1024)" in sql
    assert "using hnsw" in sql
    assert "extensions.vector_cosine_ops" in sql


def test_corrupted_column_comments_are_repaired_additively() -> None:
    migrations = sorted(
        (ROOT / "supabase" / "migrations").glob(
            "*_repair_corrupted_column_comments.sql"
        )
    )
    assert len(migrations) == 1

    sql = migrations[0].read_text(encoding="utf-8")
    normalized = sql.lower()
    expected_statements = (
        "comment on column public.pension_savings_provider_stats.fee_rate_1y is\n"
        "    'FSS psCorpList feeRate1: 과거 1년 수수료율. "
        "당기 수수료율로 해석하지 않는다.';",
        "comment on column public.retirement_provider_stats.response_division is\n"
        "    'FSS rpCorpResultList 실제 응답의 division 필드. "
        "공식 문서의 sysType 응답 표기와 다르다.';",
        "comment on column public.knowledge_chunks.embedding is\n"
        "    '검증된 공식 지식 청크의 BGE-M3 1024차원 임베딩. "
        "코사인 거리 HNSW 인덱스로 의미 검색에 사용한다.';",
    )

    for statement in expected_statements:
        assert statement in sql

    assert normalized.count("comment on column") == 3
    for forbidden in (
        "alter table",
        "create table",
        "drop ",
        "insert ",
        "update ",
        "delete ",
        "grant ",
        "revoke ",
    ):
        assert forbidden not in normalized


def test_chat_idempotency_is_owner_scoped_and_denies_browser_access() -> None:
    sql = IDEMPOTENCY_MIGRATION.read_text(encoding="utf-8").lower()
    policy_sql = IDEMPOTENCY_POLICY_MIGRATION.read_text(encoding="utf-8").lower()

    assert "unique (owner_id, idempotency_key)" in sql
    assert "chat_request_idempotency_owner_created_idx" in sql
    assert "enable row level security" in sql
    assert "revoke all on table public.chat_request_idempotency" in sql
    assert "using (false)" in policy_sql


def test_chat_session_delete_is_owner_scoped_and_cascades_children() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    idempotency_sql = IDEMPOTENCY_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create policy chat_sessions_delete_own" in sql
    assert "for delete to authenticated" in sql
    assert "using (owner_id = (select auth.uid()))" in sql
    assert (
        "session_id uuid not null references public.chat_sessions(id) "
        "on delete cascade"
    ) in sql
    assert (
        "message_id uuid not null references public.chat_messages(id) "
        "on delete cascade"
    ) in sql
    assert "references public.chat_sessions(id) on delete cascade" in idempotency_sql
    assert idempotency_sql.count(
        "references public.chat_messages(id) on delete cascade"
    ) == 2


def test_all_migrations_parse_as_postgres_sql() -> None:
    for migration in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        parse_sql(migration.read_text(encoding="utf-8"))


def test_news_summary_schema_is_additive_and_enforces_ready_contract() -> None:
    sql = NEWS_SUMMARY_MIGRATION.read_text(encoding="utf-8").lower()

    assert "alter table public.news_items" in sql
    assert "summary_lines text[]" in sql
    assert "summary_status text" in sql
    assert "source_content_sha256 text" in sql
    assert "cardinality(summary_lines) = 3" in sql
    assert "news_items_summary_failure_contract_check" in sql
    assert "summary_status = 'succeeded'" in sql
    assert "news_items_ready_summary_idx" in sql
    assert "drop table" not in sql
    assert "grant " not in sql


def test_user_pension_domain_is_additive_and_rls_protected() -> None:
    sql = USER_PENSION_MIGRATION.read_text(encoding="utf-8").lower()
    new_tables = {
        "user_profiles",
        "profile_question_sets",
        "profile_questions",
        "profile_question_options",
        "investment_profile_assessments",
        "investment_profile_answers",
        "pension_accounts",
        "account_snapshots",
        "account_cash_flows",
        "financial_products",
        "account_holding_snapshots",
    }

    for table in new_tables:
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql

    assert "drop table" not in sql
    assert "alter table public.mock_accounts" not in sql
    assert "alter table public.mock_holdings" not in sql
    assert "create table public.community_reviews" not in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql


def test_user_pension_domain_matches_engine_contracts() -> None:
    sql = USER_PENSION_MIGRATION.read_text(encoding="utf-8").lower()

    for account_type in ("dc", "irp", "pension_savings"):
        assert f"'{account_type}'" in sql
    for risk_profile in (
        "stable",
        "stable_seeking",
        "risk_neutral",
        "active",
        "aggressive",
    ):
        assert f"'{risk_profile}'" in sql
    for question_code in (
        "investment_horizon",
        "investment_experience",
        "financial_knowledge",
        "risky_asset_share",
        "loss_tolerance",
        "income_stability",
    ):
        assert f"'{question_code}'" in sql

    assert "'conservative', 'balanced', 'growth'" not in sql
    assert "extensions.gen_random_uuid()" in sql
    assert "chat_request_idempotency_session_idx" in sql
    assert "financial_products_institution_idx" in sql
    assert "data_kind = 'real' and owner_id is not null and scenario_id is null" in sql
    assert "data_kind = 'mock' and owner_id is null and scenario_id is not null" in sql
    assert "coalesce(length(btrim(raw_instrument_name)), 0) > 0" in sql


def test_user_owned_tables_have_update_with_check_policies() -> None:
    sql = USER_PENSION_MIGRATION.read_text(encoding="utf-8").lower()

    for policy in (
        "user_profiles_update_own",
        "investment_profile_assessments_update_own",
        "investment_profile_answers_update_own",
        "pension_accounts_update_own",
        "account_snapshots_update_own",
        "account_cash_flows_update_own",
        "account_holding_snapshots_update_own",
    ):
        policy_start = sql.index(f"create policy {policy}")
        policy_end = sql.index(";", policy_start)
        policy_sql = sql[policy_start:policy_end]
        assert "for update to authenticated" in policy_sql
        assert "using (" in policy_sql
        assert "with check (" in policy_sql


def test_profile_answer_composite_fk_has_a_covering_index() -> None:
    sql = PROFILE_ANSWER_FK_INDEX_MIGRATION.read_text(encoding="utf-8").lower()

    assert "investment_profile_answers_option_question_idx" in sql
    assert "(option_id, question_id)" in sql


def test_profile_confirmations_are_append_only_and_owner_scoped() -> None:
    migrations = list(
        (ROOT / "supabase" / "migrations").glob(
            "*_add_investment_profile_confirmations.sql"
        )
    )
    assert len(migrations) == 1

    sql = migrations[0].read_text(encoding="utf-8").lower()
    assert "create table public.investment_profile_confirmations" in sql
    assert "assessment_id uuid not null unique" in sql
    assert "owner_id uuid not null" in sql
    assert "investment_advice_desired boolean not null" in sql
    assert "investor_information_provided boolean not null" in sql
    assert (
        "not (not investor_information_provided and investment_advice_desired)"
        in sql
    )
    assert "enable row level security" in sql
    assert "for select to authenticated" in sql
    assert "for insert to authenticated" in sql
    assert "owner_id = (select auth.uid())" in sql
    assert "for update" not in sql


def test_seed_contains_all_six_demo_scenarios() -> None:
    sql = SEED.read_text(encoding="utf-8")

    assert "dc_dormant" in sql
    assert "tax_contribution_uninvested" in sql
    assert "overlap_risk_concentration" in sql
    assert "DC형 방치" in sql
    assert "세액공제 후 미운용" in sql
    assert "계좌별 중복·위험 편중" in sql
    assert "young_retirement_distance" in sql
    assert "family_budget_pressure" in sql
    assert "pension_payout_transition" in sql
    assert "연금이 멀게 느껴지는 청년층" in sql
    assert "가계지출로 납입이 빠듯한 중년층" in sql
    assert "연금 수령을 시작하는 55세 이상" in sql


def test_etf_universe_is_server_only_and_versioned() -> None:
    sql = ETF_UNIVERSE_MIGRATION.read_text(encoding="utf-8").lower()
    new_tables = {
        "etf_dataset_versions",
        "etf_universe_products",
        "etf_return_histories",
    }

    for table in new_tables:
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql

    # 반쪽 적재가 노출되지 않도록 ready 계약을 강제한다.
    assert "etf_dataset_versions_ready_contract_check" in sql
    assert "status in ('loading', 'ready')" in sql
    # 엔진 계약과 동일한 계좌 유형·이력 출처만 허용한다.
    assert "account_type in ('dc', 'irp', 'pension_savings')" in sql
    assert "'kis_adjusted_close_plus_kind_cash_distribution'" in sql
    assert "'krx_close_fallback'" in sql
    # 내부 테이블: 브라우저 권한 차단, service_role만 부여한다.
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "etf_dataset_versions_id_seq" in sql
    assert "grant usage, select on sequence" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_krx_etf_daily_market_snapshots_are_server_only_and_indexed() -> None:
    sql = ETF_MARKET_SNAPSHOT_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.etf_daily_market_snapshots" in sql
    assert "primary key (base_date, isu_code)" in sql
    assert "^[0-9a-z]{6}$" in sql
    assert "trading_volume bigint not null" in sql
    assert "trading_value_krw numeric not null" in sql
    assert "ingestion_run_id uuid not null" in sql
    assert "etf_daily_market_snapshots_volume_idx" in sql
    assert "(base_date desc, trading_volume desc, isu_code)" in sql
    assert "etf_daily_market_snapshots_history_idx" in sql
    assert "(isu_code, base_date desc)" in sql
    assert (
        "alter table public.etf_daily_market_snapshots enable row level security" in sql
    )
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_etf_theme_verification_is_hash_bound_and_server_only() -> None:
    assert ETF_THEME_VERIFICATION_MIGRATION is not None
    sql = ETF_THEME_VERIFICATION_MIGRATION.read_text(encoding="utf-8").lower()

    for table in (
        "etf_theme_content_reviews",
        "etf_theme_content_evidence",
    ):
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql

    assert "content_sha256" in sql
    assert "^[0-9a-f]{64}$" in sql
    assert "overview" in sql
    assert "representative_companies" in sql
    assert "investment_considerations" in sql
    assert "performance_drivers" in sql
    assert "risks" in sql
    assert "status in ('draft', 'verified', 'rejected')" in sql
    assert "knowledge_documents" in sql
    assert "knowledge_chunks" in sql
    assert "knowledge_chunk_id bigint not null" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_etf_product_descriptions_are_name_keyed_and_server_only() -> None:
    assert ETF_PRODUCT_DESCRIPTION_MIGRATION is not None
    sql = ETF_PRODUCT_DESCRIPTION_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.etf_product_descriptions" in sql
    assert "product_name text not null" in sql
    assert "normalized_product_name text not null" in sql
    assert "unique (catalog_version, normalized_product_name)" in sql
    assert "isu_code" not in sql
    assert "content_sha256" in sql
    assert "^[0-9a-f]{64}$" in sql
    assert "source_document_ids text[] not null" in sql
    assert (
        "alter table public.etf_product_descriptions enable row level security"
        in sql
    )
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_etf_component_snapshots_are_server_only_and_ranked_top3() -> None:
    sql = ETF_COMPONENT_SNAPSHOT_MIGRATION.read_text(encoding="utf-8").lower()

    for table in ("etf_component_snapshots", "etf_component_snapshot_items"):
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
    assert "rank between 1 and 3" in sql
    assert "raw_payload jsonb not null" in sql
    assert "raw_sha256 text not null" in sql
    assert "etf_component_snapshots_latest_idx" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql


def test_official_etf_distribution_raw_storage_is_private_and_service_only() -> None:
    assert ETF_DISTRIBUTION_RAW_STORAGE_MIGRATION is not None
    sql = ETF_DISTRIBUTION_RAW_STORAGE_MIGRATION.read_text(encoding="utf-8").lower()

    assert "insert into storage.buckets" in sql
    assert "official-etf-distribution-raw" in sql
    assert "public = false" in sql
    assert "on storage.objects" not in sql
    assert "to authenticated" not in sql
    assert "to anon" not in sql


def test_official_etf_universe_cache_storage_is_private_and_service_only() -> None:
    assert ETF_UNIVERSE_CACHE_STORAGE_MIGRATION is not None
    sql = ETF_UNIVERSE_CACHE_STORAGE_MIGRATION.read_text(encoding="utf-8").lower()

    assert "insert into storage.buckets" in sql
    assert "official-etf-universe-cache" in sql
    assert "public = false" in sql
    assert "on storage.objects" not in sql
    assert "to authenticated" not in sql
    assert "to anon" not in sql


def test_official_etf_component_sources_are_scoped_and_server_only() -> None:
    assert OFFICIAL_ETF_COMPONENT_SOURCE_MIGRATION is not None
    sql = OFFICIAL_ETF_COMPONENT_SOURCE_MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    assert "alter table public.etf_component_snapshots" in sql
    for column in (
        "as_of_date",
        "source_kind",
        "coverage_kind",
        "completeness",
        "weight_basis",
        "source_locator",
        "source_component_count",
    ):
        assert column in sql
    assert "create table public.etf_component_source_bindings" in sql
    assert (
        "alter table public.etf_component_source_bindings enable row level security"
        in sql
    )
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "to authenticated" not in sql
    assert "drop table" not in sql

    seed = SEED.read_text(encoding="utf-8").lower()
    for source_code in (
        "official_sol_etf",
        "official_tiger_etf",
        "official_kiwoom_etf",
        "official_kodex_etf",
        "official_koact_etf",
    ):
        assert source_code in seed


def test_official_etf_binding_source_fk_has_covering_index() -> None:
    assert OFFICIAL_ETF_BINDING_SOURCE_INDEX_MIGRATION is not None
    sql = OFFICIAL_ETF_BINDING_SOURCE_INDEX_MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    assert "create index etf_component_source_bindings_source_idx" in sql
    assert "on public.etf_component_source_bindings (source_id)" in sql
    assert "drop index" not in sql


def test_lifecycle_scenarios_are_additive_mock_data_only() -> None:
    sql = LIFECYCLE_SCENARIOS_MIGRATION.read_text(encoding="utf-8").lower()

    assert "insert into public.mock_scenarios" in sql
    assert "insert into public.mock_accounts" in sql
    assert "insert into public.mock_holdings" in sql
    assert "auth.users" not in sql
    assert "drop table" not in sql


def test_demo_hero_etf_links_are_additive_and_use_verified_universe() -> None:
    assert HERO_ETF_MIGRATION.exists()
    sql = HERO_ETF_MIGRATION.read_text(encoding="utf-8").lower()

    assert "alter table public.mock_holdings" in sql
    assert "etf_isu_code text" in sql
    assert "mock_holdings_etf_isu_code_idx" in sql
    assert "expected 12 hero etf links" in sql

    for code in ("379800", "273130", "434060"):
        assert f"'{code}'" in sql
    for scenario in (
        "family_budget_pressure",
        "overlap_risk_concentration",
        "pension_payout_transition",
    ):
        assert f"'{scenario}'" in sql

    assert "etf_universe_products" in sql
    assert "etf_return_histories" in sql
    assert "count(*) = 253" in sql
    assert "benchmark_mock" not in sql
    assert "drop table" not in sql


def test_mock_accounts_are_backfilled_into_common_account_tables() -> None:
    migrations = list(
        (ROOT / "supabase" / "migrations").glob(
            MOCK_ACCOUNT_BACKFILL_MIGRATION_GLOB
        )
    )
    assert len(migrations) == 1

    sql = migrations[0].read_text(encoding="utf-8").lower()

    assert "insert into public.pension_accounts" in sql
    assert "insert into public.account_snapshots" in sql
    assert "insert into public.account_holding_snapshots" in sql
    assert "alter column contributed_principal_krw drop not null" in sql
    assert "add column etf_isu_code text" in sql
    assert "account_holding_snapshots_etf_isu_code_idx" in sql
    assert "holding.etf_isu_code" in sql
    assert "null::numeric" in sql
    assert "on conflict (id) do update" in sql
    assert "expected 6 mock scenarios" in sql
    assert "expected 13 mock accounts" in sql
    assert "expected 26 mock holdings" in sql
    assert "mock account balance does not equal holding total" in sql
    assert "backfilled account balance does not match source" in sql
    assert "backfilled holding total does not match source" in sql

    for forbidden in ("drop table", "truncate", "delete from"):
        assert forbidden not in sql


def test_local_seed_writes_common_mock_accounts_directly() -> None:
    sql = SEED.read_text(encoding="utf-8").lower()

    assert "insert into public.pension_accounts" in sql
    assert "insert into public.account_snapshots" in sql
    assert "insert into public.account_holding_snapshots" in sql
    assert "on conflict (id) do update" in sql
    assert "expected 13 seeded mock accounts" in sql
    assert "expected 86 seeded mock holdings" in sql
    assert "public.mock_accounts" not in sql
    assert "public.mock_holdings" not in sql


def test_demo_seed_renderer_and_benchmark_loader_do_not_write_legacy_accounts() -> None:
    renderer = DEMO_SQL_RENDERER.read_text(encoding="utf-8").lower()
    loader = BENCHMARK_LOADER.read_text(encoding="utf-8").lower()

    for source in (renderer, loader):
        assert "public.mock_accounts" not in source
        assert "public.mock_holdings" not in source


def test_demo_etf_holdings_are_resynced_to_common_accounts() -> None:
    migrations = list(
        (ROOT / "supabase" / "migrations").glob(
            DEMO_ETF_COMMON_SYNC_MIGRATION_GLOB
        )
    )
    assert len(migrations) == 1

    sql = migrations[0].read_text(encoding="utf-8").lower()
    assert "expected 86 detailed mock holdings" in sql
    assert "delete from public.account_holding_snapshots" in sql
    assert "insert into public.account_holding_snapshots" in sql
    assert "expected 86 synced common holdings" in sql
    assert "synced common holding total does not match source" in sql
    assert "drop table" not in sql
    assert "truncate" not in sql


def test_demo_customer_runtime_tax_year_stays_on_supported_engine_year() -> None:
    migration_sql = DEMO_CUSTOMER_CONTRACT_MIGRATION.read_text(
        encoding="utf-8"
    ).lower()
    loader_source = BENCHMARK_LOADER.read_text(encoding="utf-8").lower()
    provisioner_source = DEMO_AUTH_PROVISIONER.read_text(encoding="utf-8").lower()
    renderer_source = DEMO_SQL_RENDERER.read_text(encoding="utf-8").lower()
    seed_sql = SEED.read_text(encoding="utf-8").lower()

    for source in (migration_sql, loader_source, renderer_source, seed_sql):
        assert "tax_year = 2026" in source
    assert "demo_context_tax_year = 2026" in provisioner_source
    for source in (
        migration_sql,
        loader_source,
        provisioner_source,
        renderer_source,
        seed_sql,
    ):
        assert "tax_year = benchmark.tax_year::smallint" not in source


def test_demo_customer_migration_caps_legacy_personal_pension_contributions() -> None:
    sql = DEMO_CUSTOMER_CONTRACT_MIGRATION.read_text(encoding="utf-8").lower()

    assert "monthly_personal_pension_limit_krw" in sql
    assert "1500000::numeric" in sql
    assert "floor(exact_units)" in sql
    assert "order by fractional_units desc, account_id" in sql
    assert "monthly_contribution_krw = capped.target_monthly_krw::text" in sql
    assert "annual_contribution_krw = (capped.target_monthly_krw * 12)::text" in sql


def test_updated_at_tables_have_moddatetime_triggers_and_holding_constraints() -> None:
    sql = SCHEMA_ADDITIVE_MIGRATION.read_text(encoding="utf-8").lower()

    updated_at_tables = (
        "chat_sessions",
        "data_sources",
        "demo_investor_profiles",
        "demo_public_portfolio_metrics",
        "demo_user_financial_context",
        "etf_product_descriptions",
        "etf_theme_content_reviews",
        "financial_institutions",
        "financial_products",
        "knowledge_documents",
        "mock_scenarios",
        "pension_accounts",
        "user_profiles",
    )
    assert "create extension if not exists moddatetime with schema extensions" in sql
    for table in updated_at_tables:
        assert f"create trigger {table}_updated_at_trigger" in sql
        assert f"before update on public.{table}" in sql
    assert sql.count("execute function extensions.moddatetime(updated_at)") == len(
        updated_at_tables
    )
    assert "account_holding_snapshots_snapshot_product_unique_idx" in sql
    assert "where product_id is not null" in sql
    assert "account_holding_snapshots_snapshot_raw_name_unique_idx" in sql
    assert "where product_id is null" in sql
    assert "account_holding_snapshots_etf_isu_code_format_check" in sql
    assert "mock_holdings_etf_isu_code_format_check" in sql
    assert "^[0-9a-z]{6}$" in sql
    assert "drop table" not in sql


ANNOTATE_DOMAINS_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_annotate_table_domains.sql")
)


def test_table_domain_annotations_are_additive_and_complete() -> None:
    import re

    sql = ANNOTATE_DOMAINS_MIGRATION.read_text(encoding="utf-8")
    normalized = sql.lower()

    # 순수 주석·조회 뷰만 추가한다. 스키마·데이터·권한 테이블은 바꾸지 않는다.
    for forbidden in ("alter table", "create table", "drop ", "insert into"):
        assert forbidden not in normalized

    # 코멘트가 없던 41개 테이블에만 도메인 태그를 단다.
    table_comments = re.findall(
        r"comment on table public\.(\w+) is\s*'(\[[^]]+\][^']*)'", sql
    )
    tagged = {name for name, _ in table_comments}
    assert len(tagged) == 41
    assert len(table_comments) == 41

    allowed_domains = {
        "source",
        "institution",
        "asset",
        "mock_scenario",
        "mock_public",
        "benchmark",
        "demo_customer",
        "engine_audit",
        "rag_news",
        "chat",
        "user_pension",
    }
    allowed_lifecycles = {"live", "retained", "reserved", "dead"}
    for _, comment in table_comments:
        match = re.match(r"\[([^/]+)/([^]]+)\]", comment)
        assert match is not None
        assert match.group(1) in allowed_domains
        assert match.group(2) in allowed_lifecycles

    # 이미 코멘트가 있던 15개 테이블은 이 마이그레이션에서 재정의하지 않는다.
    already_commented = {
        "demo_investor_profile_answers",
        "demo_investor_profiles",
        "demo_public_portfolio_metrics",
        "etf_component_snapshot_items",
        "etf_component_snapshots",
        "etf_component_source_bindings",
        "etf_daily_market_snapshots",
        "etf_dataset_versions",
        "etf_distribution_event_versions",
        "etf_distribution_events",
        "etf_product_descriptions",
        "etf_return_histories",
        "etf_theme_content_evidence",
        "etf_theme_content_reviews",
        "etf_universe_products",
    }
    assert tagged.isdisjoint(already_commented)

    # 관리자 식별용 카탈로그 뷰는 security_invoker로 만들고 브라우저 권한을 회수한다.
    assert "create view public.table_domain_catalog" in normalized
    assert "security_invoker = true" in normalized
    assert (
        "revoke all privileges on public.table_domain_catalog\n"
        "from public, anon, authenticated;" in normalized
    )
    assert "grant select on public.table_domain_catalog to service_role;" in normalized
