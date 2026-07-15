from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.app.chat.service import (
    DataSourceUnavailableError,
    LocalMarkdownKnowledgeRepository,
    get_chat_service,
)
from backend.app.engine import (
    AccountType,
    HoldingInput,
    PortfolioInput,
    RiskTreatment,
)
from backend.app.retrieval.repository import KnowledgeMatch, RetrievalRepository
from backend.app.settings import Settings


def _settings(database_url: str | None) -> Settings:
    return Settings(
        _env_file=None,
        database_url=SecretStr(database_url) if database_url else None,
    )


def test_chat_service_uses_database_repository_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = KnowledgeMatch(
        chunk_id=41,
        document_id="2a83f318-b14d-43eb-9ce6-904a8967d00a",
        title="DB 공식 문서",
        source_url="https://official.example/guide",
        content="DB 청크 내용",
        text_rank=0.75,
    )
    monkeypatch.setattr(
        RetrievalRepository,
        "search_knowledge",
        lambda self, query, *, limit=8: [expected],
    )
    service = get_chat_service(_settings("postgresql://server-only.example/db"))

    assert service.backend == "supabase"
    assert isinstance(service.knowledge, RetrievalRepository)
    assert service.news is service.knowledge
    assert service.disclosures is not None
    assert service.search_knowledge("IRP") == [expected]


def test_chat_service_uses_verified_local_markdown_without_database() -> None:
    service = get_chat_service(_settings(None))

    assert service.backend == "local"
    assert isinstance(service.knowledge, LocalMarkdownKnowledgeRepository)
    matches = service.search_knowledge("IRP 위험자산", limit=3)
    assert matches
    assert all(match.document_id.startswith("local:") for match in matches)
    assert all(match.chunk_id > 0 for match in matches)
    assert all(match.source_url.startswith("project://docs/") for match in matches)


def test_local_repository_rejects_fixture_sources(tmp_path: Path) -> None:
    fixture = tmp_path / "data" / "scenario_fixture.md"
    fixture.parent.mkdir()
    fixture.write_text("# 사용자 계좌", encoding="utf-8")

    with pytest.raises(ValueError, match="fixtures and account data"):
        LocalMarkdownKnowledgeRepository(
            project_root=tmp_path,
            document_paths=(Path("data/scenario_fixture.md"),),
        )


def test_database_failure_is_not_hidden_by_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(self: RetrievalRepository, query: str, *, limit: int = 8) -> None:
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(RetrievalRepository, "search_knowledge", fail)
    service = get_chat_service(
        _settings("postgresql://unavailable.example/database")
    )

    with pytest.raises(ConnectionError, match="database unavailable"):
        service.search_knowledge("IRP")
    assert service.backend == "supabase"


def test_live_tools_do_not_use_fixtures_without_database() -> None:
    service = get_chat_service(_settings(None))

    with pytest.raises(DataSourceUnavailableError, match="FSS disclosures"):
        service.search_disclosures("irp")
    with pytest.raises(DataSourceUnavailableError, match="latest news"):
        service.latest_news("연금")


def test_evaluate_portfolio_delegates_to_rule_engine() -> None:
    service = get_chat_service(_settings(None))
    portfolio = PortfolioInput(
        account_type=AccountType.DC,
        holdings=[
            HoldingInput(
                holding_id="risky",
                amount_krw=Decimal("700000"),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
            HoldingInput(
                holding_id="safe",
                amount_krw=Decimal("300000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
        ],
    )

    result = service.evaluate_portfolio(portfolio)

    assert result.general_risky_ratio_percent == Decimal("70.00")
    assert result.within_limit is True
