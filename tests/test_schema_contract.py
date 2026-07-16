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


def test_seed_contains_the_three_product_scenarios() -> None:
    sql = SEED.read_text(encoding="utf-8")

    assert "dc_dormant" in sql
    assert "tax_contribution_uninvested" in sql
    assert "overlap_risk_concentration" in sql
    assert "DC형 방치" in sql
    assert "세액공제 후 미운용" in sql
    assert "계좌별 중복·위험 편중" in sql
