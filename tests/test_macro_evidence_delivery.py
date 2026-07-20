import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.deps import get_macro_evidence_repository
from backend.app.chat.models import ChatIntent, ChatRequest, DataBoundary
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.ingestion.macro import build_macro_evidence_report
from backend.app.ingestion.macro_clients import MacroObservation
from backend.app.macro_evidence import MacroEvidenceRepository
from backend.app.main import app


class EmptyKnowledgeRepository:
    def search_knowledge(self, query: str, *, limit: int = 8):
        return []


def _observation(
    metric_id: str,
    period: str,
    value: str,
    *,
    source: str,
    unit: str = "%",
) -> MacroObservation:
    references = {
        "BOK_ECOS": "https://ecos.bok.or.kr/api/",
        "KOSIS": "https://kosis.kr/openapi/",
        "FRED": "https://fred.stlouisfed.org/",
    }
    return MacroObservation(
        metric_id=metric_id,
        source=source,
        label=metric_id,
        period=period,
        value=Decimal(value),
        unit=unit,
        source_reference=references[source],
        dimensions={},
    )


def _report_path(tmp_path: Path) -> Path:
    observations = [
        _observation(
            "kr_cpi_index", "2025-06-01", "116", source="BOK_ECOS", unit="index"
        ),
        _observation(
            "kr_cpi_index",
            "2026-06-01",
            "119.48",
            source="BOK_ECOS",
            unit="index",
        ),
        _observation("kr_base_rate", "2026-07-17", "2.75", source="BOK_ECOS"),
        _observation(
            "kr_life_expectancy_65_a1",
            "2023-01-01",
            "23.6",
            source="KOSIS",
            unit="년",
        ),
        _observation(
            "kr_life_expectancy_65_a2",
            "2023-01-01",
            "19.2",
            source="KOSIS",
            unit="년",
        ),
        _observation(
            "us_federal_funds_rate", "2026-06-01", "3.63", source="FRED"
        ),
        _observation("us_cpi_yoy", "2026-06-01", "3.46", source="FRED"),
        _observation("us_treasury_10y", "2026-07-16", "4.57", source="FRED"),
        _observation(
            "us_breakeven_inflation_10y",
            "2026-07-17",
            "2.24",
            source="FRED",
        ),
    ]
    report = build_macro_evidence_report(
        observations=observations, as_of=date(2026, 7, 20)
    )
    report["source_manifests"] = [
        {
            "path": "data/raw/macro/private.json",
            "request_params": {"api_key": "must-not-leak"},
            "sha256": "private-hash",
        }
    ]
    path = tmp_path / "macro.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return path


def test_public_read_model_excludes_collector_internals(tmp_path: Path) -> None:
    snapshot = MacroEvidenceRepository(_report_path(tmp_path)).latest()
    payload = snapshot.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False)

    assert snapshot.outcome == "ready"
    assert len(snapshot.metrics) == 8
    assert "source_manifests" not in serialized
    assert "data/raw/macro" not in serialized
    assert "must-not-leak" not in serialized
    assert "private-hash" not in serialized
    assert snapshot.algorithm_usage.planning_return_input is False


def test_macro_evidence_api_returns_sanitized_snapshot(tmp_path: Path) -> None:
    repository = MacroEvidenceRepository(_report_path(tmp_path))
    app.dependency_overrides[get_macro_evidence_repository] = lambda: repository
    try:
        response = TestClient(app).get("/macro/evidence")
    finally:
        app.dependency_overrides.pop(get_macro_evidence_repository, None)

    assert response.status_code == 200
    body = response.json()
    assert body["policy_version"] == "macro-evidence-2026-07-20.1"
    assert len(body["metrics"]) == 8
    assert "source_manifests" not in body


def test_macro_evidence_api_fails_closed_when_report_is_missing(
    tmp_path: Path,
) -> None:
    repository = MacroEvidenceRepository(tmp_path / "missing.json")
    app.dependency_overrides[get_macro_evidence_repository] = lambda: repository
    try:
        response = TestClient(app).get("/macro/evidence")
    finally:
        app.dependency_overrides.pop(get_macro_evidence_repository, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Current macro evidence is not available"}


def test_chat_macro_answer_has_official_source_chips_and_no_forecast(
    tmp_path: Path,
) -> None:
    chatbot = ChatService(
        knowledge=EmptyKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        macro_evidence=MacroEvidenceRepository(_report_path(tmp_path)),
    )

    response = chatbot.ask(
        ChatRequest(message="한국 기준금리와 물가상승률을 알려줘")
    )

    assert response.intent is ChatIntent.MACRO_EVIDENCE
    assert response.data_mode == "official_macro_observations"
    assert {item.value for item in response.numeric_evidence} == {
        Decimal("2.75"),
        Decimal("3"),
    }
    assert all(
        source.data_boundary is DataBoundary.OFFICIAL_STATISTICS
        for source in response.sources
    )
    assert all(source.locator.startswith("https://") for source in response.sources)
    assert "미래 전망이 아니에요" in response.answer
    assert "직접 사용하지 않아요" in response.answer


def test_chat_macro_answer_does_not_invent_values_when_report_is_missing(
    tmp_path: Path,
) -> None:
    chatbot = ChatService(
        knowledge=EmptyKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        macro_evidence=MacroEvidenceRepository(tmp_path / "missing.json"),
    )

    response = chatbot.ask(ChatRequest(message="기준금리를 알려줘"))

    assert response.intent is ChatIntent.MACRO_EVIDENCE
    assert response.data_mode == "unavailable"
    assert response.sources == []
    assert response.numeric_evidence == []
