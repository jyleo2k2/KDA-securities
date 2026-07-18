from fastapi.testclient import TestClient

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatRequest
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.main import app

client = TestClient(app)


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

    overlap = next(
        hero
        for hero in heroes
        if hero["scenario_code"] == "overlap_risk_concentration"
    )
    etf_codes = {
        holding["etf_isu_code"]
        for account in overlap["accounts"]
        for holding in account["holdings"]
        if holding["etf_isu_code"] is not None
    }
    assert etf_codes == {"273130", "379800", "434060"}
    assert overlap["total_amount_krw"] == "190000000.00"


def test_demo_hero_stress_is_rule_based_and_not_a_forecast() -> None:
    response = client.get("/chat/demo/heroes")

    overlap = next(
        hero
        for hero in response.json()
        if hero["scenario_code"] == "overlap_risk_concentration"
    )
    summary = overlap["risk_summary"]

    assert summary["dominant_asset_class"] == "global_equity"
    assert summary["dominant_asset_percent"] == "68.41"
    assert summary["general_risky_asset_percent"] == "68.42"
    assert summary["stress_scenario_code"] == "equity_drawdown"
    assert summary["estimated_stress_loss_percent"] == "28.30"
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
