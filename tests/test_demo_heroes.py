import json
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from backend.app.auth import require_supabase_user_id
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatRequest
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.main import app

client = TestClient(app)
EXAMPLES = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "mock"
    / "customer_data_examples.json"
)


def test_customer_examples_include_every_common_column_and_nested_row() -> None:
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    assert examples["contract_counts"] == {
        "customer_columns": 29,
        "account_columns_excluding_nested_holdings": 23,
        "benchmark_holding_columns": 6,
        "detailed_etf_holding_columns": 7,
    }
    for example in (
        examples["benchmark_customer_example"],
        examples["representative_customer_example"]["benchmark_contract"],
    ):
        assert len(example["customer"]) == 29
        assert example["accounts"]
        assert all(len(account) - 1 == 23 for account in example["accounts"])
        assert all(
            len(holding) == 6
            for account in example["accounts"]
            for holding in account["holdings"]
        )

    representative = examples["representative_customer_example"]
    assert (
        representative["demo_identity"]["benchmark_user_id"]
        == representative["benchmark_contract"]["customer"]["user_id"]
    )
    assessment = representative["investor_profile_assessment"]
    assert assessment["investor_profile"] == "active"
    assert assessment["total_score"] == 39
    assert assessment["data_boundary"] == "mock"
    public_metrics = representative["public_portfolio_metrics"]
    assert public_metrics["portfolio_trailing_12m_return_pct"] == "11.16"
    assert public_metrics["return_period_end"] == "2025-12-31"
    assert public_metrics["like_count"] == 173
    assert public_metrics["return_metric"]["is_forecast"] is False
    assert public_metrics["like_metric"]["performance_based"] is False


def test_demo_heroes_endpoint_exposes_six_named_profiles_and_etf_links() -> None:
    app.dependency_overrides[require_supabase_user_id] = lambda: UUID(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    )
    try:
        response = client.get("/chat/heroes")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    heroes = response.json()
    assert len(heroes) == 6
    assert {hero["nickname"] for hero in heroes} == {
        "박준호",
        "이서연",
        "정민재",
        "김하린",
        "최지훈",
        "윤정희",
    }
    assert sum(hero["is_demo_login_candidate"] for hero in heroes) == 5
    candidates = [hero for hero in heroes if hero["is_demo_login_candidate"]]
    assert {hero["investor_profile"] for hero in candidates} == {
        "stable",
        "stable_seeking",
        "risk_neutral",
        "active",
        "aggressive",
    }
    assert len({hero["investment_reason"] for hero in heroes}) == 6
    assert len({hero["portfolio_opinion_review"] for hero in heroes}) == 6
    assert len({hero["representative_etf_theme"] for hero in heroes}) == 6
    assert len({hero["representative_etf_theme_review"] for hero in heroes}) == 6
    expected_public_metrics = {
        "dc_dormant": ("7.72", 126),
        "tax_contribution_uninvested": ("11.20", 284),
        "overlap_risk_concentration": ("11.16", 173),
        "young_retirement_distance": ("0.74", 412),
        "family_budget_pressure": ("12.79", 358),
        "pension_payout_transition": ("4.69", 97),
    }
    for hero in heroes:
        expected_return, expected_likes = expected_public_metrics[
            hero["scenario_code"]
        ]
        assert hero["past_performance"]["trailing_12m_return_pct"] == expected_return
        assert hero["past_performance"]["period_start"] == "2025-01-01"
        assert hero["past_performance"]["period_end"] == "2025-12-31"
        assert hero["past_performance"]["is_forecast"] is False
        assert hero["past_performance"]["official_ranking_metric"] is False
        assert hero["like_summary"]["count"] == expected_likes
        assert hero["like_summary"]["is_synthetic"] is True
        assert hero["like_summary"]["performance_based"] is False
    assert all(hero["investor_profile_score"] > 0 for hero in heroes)
    assert all(
        hero["investor_profile_assessment"]["data_boundary"] == "mock"
        for hero in heroes
    )
    payout = next(
        hero
        for hero in heroes
        if hero["scenario_code"] == "pension_payout_transition"
    )
    assert payout["is_demo_login_candidate"] is False
    assert payout["investor_profile"] == "stable"

    issuer_names = {
        holding["instrument_name"].split()[0]
        for hero in heroes
        for account in hero["accounts"]
        for holding in account["holdings"]
        if holding["etf_isu_code"] is not None
    }
    assert issuer_names == {"KODEX", "TIGER", "ACE", "RISE", "SOL", "HANARO"}
    assert any(
        holding["instrument_name"].split()[0] == "KODEX"
        for hero in heroes
        for account in hero["accounts"]
        for holding in account["holdings"]
        if holding["etf_isu_code"] is not None
    )
    for hero in heroes:
        holding_codes = {
            holding["etf_isu_code"]
            for account in hero["accounts"]
            for holding in account["holdings"]
            if holding["etf_isu_code"] is not None
        }
        assert 1 <= len(hero["representative_etf_isu_codes"]) <= 2
        assert set(hero["representative_etf_isu_codes"]).issubset(holding_codes)
    for hero in heroes:
        benchmark = hero["benchmark_customer"]
        assert benchmark["user_id"].startswith("USR")
        assert "employment_type" in benchmark
        assert "pension_savings_contribution_krw" in benchmark
        assert "irp_contribution_krw" in benchmark
        assert all("source_ids" in account for account in benchmark["accounts"])
        assert all(
            "weight" in holding
            for account in benchmark["accounts"]
            for holding in account["holdings"]
        )
        benchmark_total = sum(
            int(account["balance_krw"]) for account in benchmark["accounts"]
        )
        assert int(hero["total_amount_krw"].split(".")[0]) == benchmark_total


def test_demo_hero_stress_is_rule_based_and_not_a_forecast() -> None:
    app.dependency_overrides[require_supabase_user_id] = lambda: UUID(
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    )
    try:
        response = client.get("/chat/heroes")
    finally:
        app.dependency_overrides.clear()

    overlap = next(
        hero
        for hero in response.json()
        if hero["scenario_code"] == "overlap_risk_concentration"
    )
    summary = overlap["risk_summary"]

    assert summary["dominant_asset_class"] == "global_equity"
    assert summary["dominant_asset_percent"] == "40.97"
    assert summary["general_risky_asset_percent"] == "65.11"
    assert summary["stress_scenario_code"] == "equity_drawdown"
    assert summary["estimated_stress_loss_percent"] == "24.39"
    assert summary["is_forecast"] is False
    assert summary["requires_rebalancing_review"] is True


def test_portfolio_question_without_hero_uses_customer_facing_selection_copy() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )
    response = service.ask(
        ChatRequest(message="내 포트폴리오와 리밸런싱 필요 여부를 알려줘")
    )

    assert "고객 유형" in response.answer
    assert "scenario_code" not in response.answer
    assert all("scenario_code" not in item for item in response.limitations)
