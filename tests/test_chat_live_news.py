from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from backend.app.chat.handlers.disclosures_news import _historical_outcome_section
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.live_news import (
    LiveMarketNewsItem,
    LiveMarketNewsSnapshot,
    LiveNewsUnavailable,
    NaverLiveNewsSearch,
)
from backend.app.chat.models import (
    ChatRequest,
    ChatResponse,
    CompletedSurveyProfile,
)
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import (
    AccountType,
    EducationalRiskProfile,
)
from backend.app.etf_theme_repository import get_default_etf_theme_repository
from backend.app.ingestion.naver_news import NaverNewsItem, NaverNewsResponse
from backend.app.news_event_outcome_repository import NewsEventOutcomeRecord
from backend.app.retrieval.repository import NewsMatch


def _news_response(*, query: str, now: datetime) -> NaverNewsResponse:
    is_korean_market = query == "한국 증시"
    item = NaverNewsItem(
        title=(
            "반도체 2분기 영업이익 발표에 코스피 변동"
            if is_korean_market
            else "연준 금리 결정에 미국 증시 변동"
        ),
        description=(
            "삼성전자 실적 발표 뒤 반도체 업종 거래대금이 늘었다."
            if is_korean_market
            else "연준이 기준금리를 발표한 뒤 국채 금리가 움직였다."
        ),
        original_url=(
            "https://www.yna.co.kr/view/AKR20260720000100002"
            if is_korean_market
            else "https://www.reuters.com/markets/us/rates-2026-07-20/"
        ),
        portal_url=(
            "https://n.news.naver.com/mnews/article/001/0000000001"
            if is_korean_market
            else "https://n.news.naver.com/mnews/article/123/0000000002"
        ),
        published_at=now,
        raw_metadata={},
    )
    return NaverNewsResponse(
        total=1,
        start=1,
        display=1,
        raw_item_count=1,
        items=[item],
        rejected_reasons=(),
    )


def test_live_search_filters_ranks_and_caches_market_news(monkeypatch) -> None:
    calls: list[str] = []
    now = datetime.now(UTC)

    def fake_fetch_naver_news(client, **kwargs):
        del client
        calls.append(kwargs["query"])
        assert kwargs["display"] == 50
        assert kwargs["sort"] == "date"
        return _news_response(query=kwargs["query"], now=now)

    monkeypatch.setattr(
        "backend.app.chat.live_news.fetch_naver_news",
        fake_fetch_naver_news,
    )
    search = NaverLiveNewsSearch(client_id="client-id", client_secret="secret")

    first = search.fetch_market_news(region=None, limit=2)
    second = search.fetch_market_news(region=None, limit=2)

    assert len(first.items) == 2
    assert first.from_cache is False
    assert second.from_cache is True
    assert calls == ["한국 증시", "미국 증시"]
    assert {item.region for item in first.items} == {"kr", "us"}
    assert any("earnings" in item.topics for item in first.items)
    assert any("monetary_policy" in item.topics for item in first.items)


class FakeLiveNewsSearch:
    def fetch_market_news(self, *, region, limit):
        assert region in {None, "kr", "us"}
        assert limit == 3
        return LiveMarketNewsSnapshot(
            items=(
                LiveMarketNewsItem(
                    item_id="news-item-1",
                    canonical_url=("https://www.yna.co.kr/view/AKR20260720000100002"),
                    title="반도체 실적 발표에 코스피 변동",
                    description="삼성전자 영업이익 발표 뒤 반도체 업종이 움직였다.",
                    original_url="https://www.yna.co.kr/view/AKR20260720000100002",
                    published_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
                    publisher="연합뉴스",
                    region="kr",
                    topics=("indices", "earnings", "sector"),
                ),
            ),
            fetched_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
        )


class UnavailableLiveNewsSearch:
    def fetch_market_news(self, *, region, limit):
        del region, limit
        raise LiveNewsUnavailable("sanitized test failure")


class StoredNewsRepository:
    def recent_market_news(
        self,
        *,
        region=None,
        days=5,
        limit=3,
        exclude_item_ids=(),
        preferred_topics=(),
    ):
        del region, days, exclude_item_ids, preferred_topics
        return [
            NewsMatch(
                item_id="00000000-0000-4000-8000-000000000001",
                title="연준 금리 발표 뒤 미국 증시 변동",
                description="연준의 공식 발표 뒤 국채 금리가 움직였다.",
                original_url="https://www.reuters.com/markets/us/rates-2026-07-20/",
                portal_url=None,
                published_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
                summary_lines=(
                    "연준이 기준금리를 발표했다.",
                    "미국 국채 금리가 움직였다.",
                    "미국 증시 변동성이 커졌다.",
                ),
            )
        ][:limit]

    def news_by_ids(self, item_ids):
        del item_ids
        return []

    def summarized_news_by_canonical_urls(self, canonical_urls):
        canonical_url = "https://www.yna.co.kr/view/AKR20260720000100002"
        if canonical_url not in canonical_urls:
            return {}
        return {
            canonical_url: NewsMatch(
                item_id="00000000-0000-4000-8000-000000000002",
                title="반도체 실적 발표에 코스피 변동",
                description=None,
                original_url=canonical_url,
                portal_url=None,
                published_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
                summary_lines=(
                    "반도체 실적 발표 뒤 코스피가 움직였다.",
                    "관련 업종의 거래대금이 늘었다.",
                    "기사 원문에서 시장 반응을 확인해야 한다.",
                ),
            )
        }


class EmptyStoredNewsRepository(StoredNewsRepository):
    def recent_market_news(self, **kwargs):
        del kwargs
        return []


def _survey(risk_profile: EducationalRiskProfile) -> CompletedSurveyProfile:
    return CompletedSurveyProfile(
        account_type=AccountType.IRP,
        current_age=35,
        retirement_start_age=60,
        risk_profile=risk_profile,
        loss_tolerance_percent=Decimal("40"),
    )


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        live_news=FakeLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )


def _event_strategy_text(response: ChatResponse) -> str:
    return "\n".join(
        [
            response.answer,
            *[section.content for section in response.sections],
            *[
                cell
                for section in response.sections
                for block in section.blocks
                for row in block.rows
                for cell in row
            ],
            *[
                item
                for section in response.sections
                for block in section.blocks
                for item in block.items
            ],
        ]
    )


def test_event_strategy_question_uses_live_news_for_tactical_guidance() -> None:
    response = _service().ask(
        ChatRequest(
            message="실시간 뉴스 기반 이벤트 드리븐 운용전략을 알려줘",
            survey_profile=_survey(EducationalRiskProfile.AGGRESSIVE),
        )
    )

    validated = ChatResponse.model_validate(response.model_dump())
    assert validated.data_mode == "live_news_event_strategy"
    assert validated.news_items
    assert any(
        source.evidence_id.startswith("live-news:") for source in validated.sources
    )
    strategy_text = _event_strategy_text(validated)
    assert "기존 장기 코어 배분과 규칙 엔진 목표비중을 먼저 유지" in strategy_text
    assert "5%p" not in strategy_text
    assert "10%" not in strategy_text
    assert "15%" not in strategy_text


def test_event_strategy_keeps_conservative_profile_outside_tactical_guidance() -> None:
    response = _service().ask(
        ChatRequest(
            message="실시간 뉴스 기반 이벤트 드리븐 운용전략을 알려줘",
            survey_profile=_survey(EducationalRiskProfile.STABLE),
        )
    )

    assert response.data_mode == "live_news_event_strategy"
    assert response.news_items
    assert "현재 설문 성향보다 공격적인 이벤트 전술은 제안하지 않아요" in (
        _event_strategy_text(response)
    )


def test_event_strategy_question_uses_recent_stored_news() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        live_news=UnavailableLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(
        ChatRequest(
            message="미국 실시간 뉴스 기반 운용전략을 보여줘",
            survey_profile=_survey(EducationalRiskProfile.ACTIVE),
        )
    )

    assert response.data_mode == "stored_news_event_strategy"
    assert response.news_items
    assert not any(
        source.evidence_id.startswith("live-news:") for source in response.sources
    )
    strategy_text = _event_strategy_text(response)
    assert "기존 장기 코어 배분과 규칙 엔진 목표비중을 먼저 유지" in strategy_text
    assert "5%p" not in strategy_text
    assert "10%" not in strategy_text
    assert "15%" not in strategy_text


def test_event_strategy_does_not_personalize_etf_candidates_from_news() -> None:
    universe_calls: list[AccountType] = []

    def load_universe(account_type: AccountType):
        universe_calls.append(account_type)
        raise AssertionError("news event guidance must not load a product universe")

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        live_news=FakeLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
        portfolio_universe_loader=load_universe,
    )

    response = service.ask(
        ChatRequest(
            message="실시간 뉴스 기반 이벤트 드리븐 운용전략을 알려줘",
            survey_profile=_survey(EducationalRiskProfile.ACTIVE),
        )
    )

    assert universe_calls == []
    assert not any(
        section.title == "이벤트 드리븐 포트폴리오 가이드"
        for section in response.sections
    )
    assert not any(
        source.evidence_id == "engine:event_tactical_candidates"
        for source in response.sources
    )


def test_event_strategy_shows_verified_historical_outcome_card_only_from_ledger() -> (
    None
):
    class OutcomeReader:
        def list_for_theme_ids(self, theme_ids, *, limit=12):
            assert theme_ids
            assert limit == 500
            return [
                NewsEventOutcomeRecord(
                    event_key="news:official-2024-01-01",
                    occurred_on=datetime(2024, 1, 1, tzinfo=UTC).date(),
                    theme_id="semiconductors",
                    isu_code="111111",
                    isu_name="검증 ETF",
                    horizon_months=3,
                    total_return_percent=Decimal("12.5"),
                    maximum_drawdown_percent=Decimal("4.25"),
                    peer_median_total_return_percent=Decimal("8.75"),
                    peer_sample_count=4,
                    event_source_url="https://example.test/event",
                    event_source_label="공식 이벤트",
                    event_source_as_of=datetime(2024, 1, 1, tzinfo=UTC).date(),
                    history_source="kis_adjusted_close_plus_kind_cash_distribution",
                    history_source_url="https://example.test/returns",
                    history_source_as_of=datetime(2024, 4, 1, tzinfo=UTC).date(),
                )
            ]

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        live_news=FakeLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
        news_event_outcomes=OutcomeReader(),
    )

    response = service.ask(
        ChatRequest(
            message="실시간 뉴스 기반 이벤트 운용전략을 알려줘",
            survey_profile=_survey(EducationalRiskProfile.ACTIVE),
        )
    )

    card = next(
        section
        for section in response.sections
        if section.title == "과거 뉴스 이벤트 성과 검증"
    )
    assert card.blocks[0].rows[0][1] == "검증 ETF"
    assert card.blocks[0].rows[0][3] == "12.50%"
    assert "자동 비중 변경" in card.content
    assert any(
        source.evidence_id.startswith("news-event-outcome:")
        for source in response.sources
    )


def test_historical_outcome_card_shows_full_coverage_with_bounded_rows() -> None:
    base = NewsEventOutcomeRecord(
        event_key="fed-fomc-2025-01-01",
        occurred_on=date(2025, 1, 1),
        theme_id="bank_finance",
        isu_code="091170",
        isu_name="KODEX 은행",
        horizon_months=3,
        total_return_percent=Decimal("1.5"),
        maximum_drawdown_percent=Decimal("2.5"),
        peer_median_total_return_percent=Decimal("1.0"),
        peer_sample_count=3,
        event_source_url="https://example.test/event",
        event_source_label="Federal Reserve FOMC",
        event_source_as_of=date(2025, 1, 1),
        history_source="kis_adjusted_close_plus_kind_cash_distribution",
        history_source_url="https://example.test/returns",
        history_source_as_of=date(2025, 7, 1),
    )
    rows = [
        replace(
            base,
            event_key=f"fed-fomc-{2011 + index}-01-01",
            occurred_on=date(2011 + index, 1, 1),
            isu_code=f"{index:06d}",
            isu_name=f"ETF {index}",
        )
        for index in range(13)
    ]

    section, _ = _historical_outcome_section(rows)

    assert "2011-01-01~2023-01-01" in section.content
    assert "공식 이벤트 13건" in section.content
    assert len(section.blocks[0].rows) == 12
    assert section.blocks[0].rows[0][1] == "ETF 0"
    assert section.blocks[0].rows[-1][1] == "ETF 12"


def test_historical_outcome_card_summarizes_full_414_row_ledger() -> None:
    base = NewsEventOutcomeRecord(
        event_key="event-0",
        occurred_on=date(2011, 1, 1),
        theme_id="bank_finance",
        isu_code="000000",
        isu_name="ETF 0",
        horizon_months=1,
        total_return_percent=Decimal("1.5"),
        maximum_drawdown_percent=Decimal("2.5"),
        peer_median_total_return_percent=Decimal("1.0"),
        peer_sample_count=3,
        event_source_url="https://example.test/event",
        event_source_label="official event",
        event_source_as_of=date(2011, 1, 1),
        history_source="kis_adjusted_close_plus_kind_cash_distribution",
        history_source_url="https://example.test/returns",
        history_source_as_of=date(2025, 7, 1),
    )
    rows = [
        replace(
            base,
            event_key=f"event-{event_index}",
            occurred_on=date(2011 + event_index // 3, 1 + event_index % 3, 1),
            isu_code=f"{etf_index:06d}",
            isu_name=f"ETF {etf_index}",
            horizon_months=horizon_months,
        )
        for event_index in range(46)
        for etf_index in range(3)
        for horizon_months in (1, 3, 6)
    ]

    section, _ = _historical_outcome_section(rows)

    assert len(rows) == 414
    assert "공식 이벤트 46건" in section.content
    assert "이벤트-ETF 쌍 138건" in section.content
    assert len(section.blocks[0].rows) == 12


def test_empty_stored_news_does_not_offer_live_news_exit() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=EmptyStoredNewsRepository(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="증시 뉴스 알려줘"))

    assert "NAVER 검색" not in response.answer
    assert response.suggested_follow_ups == []


def test_pension_news_keeps_market_news_with_notice_and_pension_exit() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="연금저축 뉴스 보여줘"))

    assert response.news_items
    assert response.answer.startswith("연금 제도 뉴스는 제공하지 않아요")
    assert any(
        "연금 제도 뉴스는 제공하지 않아요" in item for item in response.limitations
    )
    assert any("가장 최신 기사는 약" in item for item in response.limitations)
    assert any(
        item.follow_up_id == "pension_account_basics"
        for item in response.suggested_follow_ups
    )


def test_company_news_keeps_market_news_with_graceful_alternatives() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="삼성전자 뉴스 보여줘"))

    assert response.intent.value == "news"
    assert "개별 종목 뉴스는 안내하지 않아요" in response.answer
    assert [item.follow_up_id for item in response.suggested_follow_ups] == [
        "decline_market_news",
        "decline_stock_related_etf_theme",
    ]


def test_timely_news_uses_stored_summary_without_live_lookup() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        live_news=FakeLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="오늘 증시 뉴스 알려줘"))

    assert response.data_mode == "news_summary"
    assert response.news_items
    assert not any(
        source.evidence_id.startswith("policy:") for source in response.sources
    )
    assert not any(
        source.evidence_id.startswith("live-news:") for source in response.sources
    )


def test_today_news_uses_stored_three_line_summaries() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        live_news=FakeLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="오늘 증시 뉴스 알려줘"))

    assert response.data_mode == "news_summary"
    assert response.news_items
    assert all(len(item.summary_lines) == 3 for item in response.news_items)
    assert all(item.evidence_id.startswith("news:") for item in response.news_items)


def test_explicit_live_news_reuses_matching_stored_summary() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        live_news=FakeLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="실시간 국내 증시 뉴스 알려줘"))

    assert response.data_mode == "news_summary"
    assert [len(item.summary_lines) for item in response.news_items] == [3]
    assert response.news_items[0].evidence_id.startswith("news:")
    assert response.conversation_context is not None


def test_timely_news_uses_stored_news_when_live_source_is_unavailable() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        live_news=UnavailableLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="방금 미국 증시 뉴스 알려줘"))

    assert response.data_mode == "news_summary"
    assert response.news_items
    assert response.answer.startswith("최근 증시 뉴스를 찾았어요")
    assert not any(
        source.evidence_id.startswith("live-news:") for source in response.sources
    )
