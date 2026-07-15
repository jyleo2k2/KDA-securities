-- Keep all data access behind FastAPI unless a user-facing table is explicitly
-- listed below. RLS remains enabled as defense in depth, but it is not the
-- substitute for Data API privileges.
revoke all privileges on table
    public.data_sources,
    public.ingestion_runs,
    public.financial_institutions,
    public.institution_aliases,
    public.pension_savings_provider_stats,
    public.retirement_provider_stats,
    public.asset_classes,
    public.mock_scenarios,
    public.mock_accounts,
    public.mock_holdings,
    public.mock_public_profiles,
    public.mock_public_portfolios,
    public.mock_public_portfolio_holdings,
    public.rule_sets,
    public.pension_rules,
    public.engine_runs,
    public.engine_run_evidence,
    public.knowledge_documents,
    public.knowledge_chunks,
    public.news_items,
    public.curated_contents,
    public.chat_sessions,
    public.chat_messages,
    public.chat_message_evidence
from public, anon, authenticated;

revoke all privileges on all sequences in schema public
from public, anon, authenticated;

-- Prevent later tables, sequences, and functions created by the migration
-- owner from being exposed through inherited PostgreSQL defaults.
alter default privileges for role postgres in schema public
    revoke all on tables from public, anon, authenticated;
alter default privileges for role postgres in schema public
    revoke all on sequences from public, anon, authenticated;
alter default privileges for role postgres in schema public
    revoke execute on functions from public, anon, authenticated;

-- Authenticated clients may only work with their own engine results and chat
-- rows. The row-level ownership policies in the initial migration still apply.
grant select on table
    public.engine_runs,
    public.engine_run_evidence
to authenticated;

grant select, insert, update, delete on table public.chat_sessions
to authenticated;
grant select, insert on table public.chat_messages
to authenticated;
grant select on table public.chat_message_evidence
to authenticated;

-- Internal ingestion, disclosure, knowledge, and assistant-message writes stay
-- server-only. service_role bypasses RLS, so it receives explicit privileges.
grant all privileges on table
    public.data_sources,
    public.ingestion_runs,
    public.financial_institutions,
    public.institution_aliases,
    public.pension_savings_provider_stats,
    public.retirement_provider_stats,
    public.asset_classes,
    public.mock_scenarios,
    public.mock_accounts,
    public.mock_holdings,
    public.mock_public_profiles,
    public.mock_public_portfolios,
    public.mock_public_portfolio_holdings,
    public.rule_sets,
    public.pension_rules,
    public.engine_runs,
    public.engine_run_evidence,
    public.knowledge_documents,
    public.knowledge_chunks,
    public.news_items,
    public.curated_contents,
    public.chat_sessions,
    public.chat_messages,
    public.chat_message_evidence
to service_role;

grant usage, select on all sequences in schema public to service_role;
