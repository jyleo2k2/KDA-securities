from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.api.deps import get_retrieval_repository
from backend.app.engine.profile import QUESTIONS
from backend.app.main import app
from backend.app.retrieval.repository import KnowledgeMatch
from backend.app.settings import Settings, get_settings
from tests.scenario_fixtures import (
    dc_dormant_account,
    overlap_dc_account,
    overlap_irp_account,
    overlap_pension_savings_account,
)

client = TestClient(app)


def test_route_paths_cover_engine_tools_and_data_reads() -> None:
    paths = {route.path for route in app.routes}
    assert paths >= {
        "/health",
        "/engine/risk-cap",
        "/engine/risk-cap/audited",
        "/engine/profile",
        "/engine/diagnostics",
        "/engine/aggregation",
        "/engine/simulation",
        "/engine/allocation-example",
        "/engine/mock-scenario/{scenario_code}",
        "/engine/pension-tax-credit",
        "/engine/non-pension-withdrawal-estimate",
        "/retrieval/knowledge",
        "/retrieval/news",
        "/disclosures/pension-savings",
        "/disclosures/retirement",
    }


def test_profile_endpoint_scores_survey() -> None:
    answers = [
        {"question_code": question.code, "selected_score": 5}
        for question in QUESTIONS
    ]
    response = client.post("/engine/profile", json={"answers": answers})
    assert response.status_code == 200
    body = response.json()
    assert body["risk_profile"] == "aggressive"
    assert body["provisional"] is True


def test_profile_endpoint_rejects_incomplete_survey() -> None:
    answers = [
        {"question_code": question.code, "selected_score": 3}
        for question in QUESTIONS[:-1]
    ]
    response = client.post("/engine/profile", json={"answers": answers})
    assert response.status_code == 422


def test_diagnostics_endpoint_flags_dormant_dc() -> None:
    payload = dc_dormant_account().model_dump(mode="json")
    response = client.post("/engine/diagnostics", json=payload)
    assert response.status_code == 200
    findings = {
        finding["check_code"]: finding["status"]
        for finding in response.json()["findings"]
    }
    assert findings["CASH_IDLE"] == "fail"


def test_aggregation_endpoint_serializes_decimals_as_strings() -> None:
    payload = {
        "accounts": [
            overlap_dc_account().model_dump(mode="json"),
            overlap_irp_account().model_dump(mode="json"),
            overlap_pension_savings_account().model_dump(mode="json"),
        ]
    }
    response = client.post("/engine/aggregation", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["total_amount_krw"] == "190000000.00"
    assert isinstance(body["total_amount_krw"], str)
    assert body["overlaps"][0]["combined_weight_percent"] == "68.42"


def test_simulation_endpoint_matches_engine_golden_value() -> None:
    response = client.post(
        "/engine/simulation",
        json={
            "current_age": 25,
            "risk_profile": "risk_neutral",
            "current_balance_krw": "10000000",
            "monthly_contribution_krw": "300000",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_principal_krw"] == "118000000.00"
    base = next(
        projection
        for projection in body["projections"]
        if projection["scenario"] == "base"
    )
    nominal = Decimal(base["nominal_value_at_55_krw"])
    rounded = (nominal / Decimal("100000")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ) * Decimal("100000")
    assert rounded == Decimal("259900000")


def test_allocation_example_endpoint_returns_approved_cell() -> None:
    response = client.post(
        "/engine/allocation-example",
        json={
            "current_age": 25,
            "risk_profile": "risk_neutral",
            "account_type": "dc",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["weights"]["growth_percent"] == "60"
    assert body["display_net_return_percent_by_scenario"]["base"] == "5.2"
    assert body["market_shock_percent"] == "-19.5"


def test_mock_scenario_endpoint_evaluates_curated_scenario() -> None:
    response = client.get("/engine/mock-scenario/dc_dormant")
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_code"] == "dc_dormant"
    assert body["data_boundary"] == "mock"
    assert body["account_evaluations"][0]["evaluated_input"]["account_type"] == "dc"


def test_mock_scenario_endpoint_returns_404_for_unknown_code() -> None:
    response = client.get("/engine/mock-scenario/does_not_exist")
    assert response.status_code == 404


def test_data_read_endpoints_return_503_without_database() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url=None
    )
    try:
        for path, params in (
            ("/retrieval/knowledge", {"query": "irp"}),
            ("/retrieval/news", {"search_query": "연금"}),
            ("/disclosures/pension-savings", {}),
            ("/disclosures/retirement", {}),
        ):
            response = client.get(path, params=params)
            assert response.status_code == 503, path
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_knowledge_search_serializes_uuid_document_id() -> None:
    match = KnowledgeMatch(
        chunk_id=1,
        document_id=uuid4(),
        title="세 연금계좌의 위험자산 규칙 검증 요약",
        source_url="project://docs/20_리서치/연금_기초.md#4-2",
        content="DC형과 IRP는 일반 위험자산을 적립금의 70%까지 운용할 수 있다.",
        text_rank=0.5,
    )

    class FakeRetrievalRepository:
        def search_knowledge(self, query, *, limit=8):
            return [match]

    app.dependency_overrides[get_retrieval_repository] = FakeRetrievalRepository
    try:
        response = client.get(
            "/retrieval/knowledge", params={"query": "위험자산"}
        )
    finally:
        app.dependency_overrides.pop(get_retrieval_repository, None)
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["document_id"] == str(match.document_id)


def test_cors_allows_vite_dev_origin() -> None:
    response = client.get(
        "/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:5173"
    )
