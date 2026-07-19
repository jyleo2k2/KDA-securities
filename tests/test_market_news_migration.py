from pathlib import Path

from pglast import parse_sql


def test_market_news_migration_parses_and_limits_scope() -> None:
    root = Path(__file__).resolve().parents[1]
    migrations = list(
        (root / "supabase" / "migrations").glob("*_add_market_news_selection.sql")
    )

    assert len(migrations) == 1
    sql = migrations[0].read_text(encoding="utf-8")
    assert parse_sql(sql)
    assert "add column selection_policy_version text" in sql
    assert "add column selection_embedding extensions.vector(1024)" in sql
    assert "news_items_canonical_url_unique_idx" in sql
    assert "news_items_normalized_title_hash_unique_idx" in sql
    assert "news_items_event_fingerprint_unique_idx" in sql
    assert "news_items_source_content_sha256_unique_idx" in sql
    assert "on delete cascade" in sql
    assert "alter table public.chat_message_evidence" in sql
    assert "drop table" not in sql.casefold()


def test_market_news_active_retention_is_additive_and_parseable() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (
        root
        / "supabase"
        / "migrations"
        / "20260719184500_repair_market_news_is_active.sql"
    )

    sql = migration.read_text(encoding="utf-8")
    assert parse_sql(sql)
    assert "add column if not exists is_active boolean not null default true" in sql
    assert "summary_status = 'succeeded'" in sql
    assert "and is_active" in sql
    assert "drop table" not in sql.casefold()
