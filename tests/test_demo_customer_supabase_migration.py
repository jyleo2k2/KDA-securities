from scripts.build_demo_customer_supabase_migration import OUTPUT_PATH, render


def test_demo_customer_supabase_migration_is_current_and_server_only() -> None:
    sql = OUTPUT_PATH.read_text(encoding="utf-8")

    assert sql == render()
    assert "create table public.demo_investor_profiles" in sql
    assert "create table public.demo_investor_profile_answers" in sql
    assert "create table public.demo_public_portfolio_metrics" in sql
    assert sql.count("enable row level security") == 3
    assert sql.count("from anon, authenticated") == 3
    assert sql.count("to service_role") == 3
    assert "check (score between 0 and 7)" in sql
    assert "check (is_forecast = false)" in sql
    assert "check (official_ranking_metric = false)" in sql
    assert "check (performance_based = false)" in sql


def test_demo_customer_supabase_migration_contains_all_scenario_rows() -> None:
    sql = OUTPUT_PATH.read_text(encoding="utf-8")
    scenario_codes = (
        "dc_dormant",
        "tax_contribution_uninvested",
        "overlap_risk_concentration",
        "young_retirement_distance",
        "family_budget_pressure",
        "pension_payout_transition",
    )

    for scenario_code in scenario_codes:
        assert sql.count(f"'{scenario_code}'") >= 13
