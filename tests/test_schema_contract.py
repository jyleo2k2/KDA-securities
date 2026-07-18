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
HERO_ETF_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260718090000_link_demo_hero_etf_holdings.sql"
)
SEED = ROOT / "supabase" / "seed.sql"


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
