create extension if not exists moddatetime with schema extensions;

create trigger chat_sessions_updated_at_trigger
before update on public.chat_sessions
for each row execute function extensions.moddatetime(updated_at);

create trigger data_sources_updated_at_trigger
before update on public.data_sources
for each row execute function extensions.moddatetime(updated_at);

create trigger demo_investor_profiles_updated_at_trigger
before update on public.demo_investor_profiles
for each row execute function extensions.moddatetime(updated_at);

create trigger demo_public_portfolio_metrics_updated_at_trigger
before update on public.demo_public_portfolio_metrics
for each row execute function extensions.moddatetime(updated_at);

create trigger demo_user_financial_context_updated_at_trigger
before update on public.demo_user_financial_context
for each row execute function extensions.moddatetime(updated_at);

create trigger etf_product_descriptions_updated_at_trigger
before update on public.etf_product_descriptions
for each row execute function extensions.moddatetime(updated_at);

create trigger etf_theme_content_reviews_updated_at_trigger
before update on public.etf_theme_content_reviews
for each row execute function extensions.moddatetime(updated_at);

create trigger financial_institutions_updated_at_trigger
before update on public.financial_institutions
for each row execute function extensions.moddatetime(updated_at);

create trigger financial_products_updated_at_trigger
before update on public.financial_products
for each row execute function extensions.moddatetime(updated_at);

create trigger knowledge_documents_updated_at_trigger
before update on public.knowledge_documents
for each row execute function extensions.moddatetime(updated_at);

create trigger mock_scenarios_updated_at_trigger
before update on public.mock_scenarios
for each row execute function extensions.moddatetime(updated_at);

create trigger pension_accounts_updated_at_trigger
before update on public.pension_accounts
for each row execute function extensions.moddatetime(updated_at);

create trigger user_profiles_updated_at_trigger
before update on public.user_profiles
for each row execute function extensions.moddatetime(updated_at);

create unique index account_holding_snapshots_snapshot_product_unique_idx
    on public.account_holding_snapshots (snapshot_id, product_id)
    where product_id is not null;

create unique index account_holding_snapshots_snapshot_raw_name_unique_idx
    on public.account_holding_snapshots (snapshot_id, raw_instrument_name)
    where product_id is null;

alter table public.account_holding_snapshots
    add constraint account_holding_snapshots_etf_isu_code_format_check
    check (
        etf_isu_code is null
        or etf_isu_code ~ '^[0-9A-Z]{6}$'
    );

alter table public.mock_holdings
    add constraint mock_holdings_etf_isu_code_format_check
    check (
        etf_isu_code is null
        or etf_isu_code ~ '^[0-9A-Z]{6}$'
    );
