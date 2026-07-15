from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_initial_data_foundation.sql")
)
DATA_API_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob("*_tighten_data_api_grants.sql")
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


def test_seed_contains_the_three_product_scenarios() -> None:
    sql = SEED.read_text(encoding="utf-8")

    assert "dc_dormant" in sql
    assert "tax_contribution_uninvested" in sql
    assert "overlap_risk_concentration" in sql
    assert "DC형 방치" in sql
    assert "세액공제 후 미운용" in sql
    assert "계좌별 중복·위험 편중" in sql
