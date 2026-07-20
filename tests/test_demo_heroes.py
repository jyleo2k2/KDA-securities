import json
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_demo_heroes_endpoint_exposes_six_named_profiles_and_etf_links() -> None:
    response = client.get("/chat/demo/heroes")

    assert response.status_code == 200
    heroes = response.json()
    assert len(heroes) == 6
    assert {hero["nickname"] for hero in heroes} == {
        "박준호(가상)",
        "이서연(가상)",
        "정민재(가상)",
        "김하린(가상)",
        "최지훈(가상)",
        "윤정희(가상)",
    }

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
    response = client.get("/chat/demo/heroes")

    overlap = next(
        hero
        for hero in response.json()
        if hero["scenario_code"] == "overlap_risk_concentration"
    )
    summary = overlap["risk_summary"]

    assert summary["dominant_asset_class"] == "domestic_equity"
    assert summary["dominant_asset_percent"] == "38.48"
    assert summary["general_risky_asset_percent"] == "64.13"
    assert summary["stress_scenario_code"] == "equity_drawdown"
    assert summary["estimated_stress_loss_percent"] == "23.28"
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

    assert "가상 고객" in response.answer
    assert "scenario_code" not in response.answer
    assert all("scenario_code" not in item for item in response.limitations)
