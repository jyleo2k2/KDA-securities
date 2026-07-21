from datetime import UTC, datetime
from decimal import Decimal

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
    DataBoundary,
)
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import (
    AccountType,
    EducationalRiskProfile,
)
from backend.app.etf_theme_repository import get_default_etf_theme_repository
from backend.app.ingestion.naver_news import NaverNewsItem, NaverNewsResponse
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
        ]
    )


def test_aggressive_profile_gets_live_event_strategy_with_source_contract() -> None:
    response = _service().ask(
        ChatRequest(
            message="실시간 뉴스 기반 이벤트 드리븐 운용전략을 알려줘",
            survey_profile=_survey(EducationalRiskProfile.AGGRESSIVE),
        )
    )

    validated = ChatResponse.model_validate(response.model_dump())
    text = _event_strategy_text(validated)
    assert validated.data_mode == "live_news_event_strategy"
    assert "반도체" in text
    assert "전술 관찰 가이드" in text
    assert "뉴스만으로 비중이나 주문을 결정하지 않아요" in text
    assert any(
        source.data_boundary == DataBoundary.NEWS_METADATA
        for source in validated.sources
    )
    assert any(source.evidence_id.startswith("policy:") for source in validated.sources)
    assert [item.follow_up_id for item in validated.suggested_follow_ups] == [
        "live_news_kr_strategy",
        "live_news_us_strategy",
    ]


def test_stable_profile_does_not_receive_aggressive_event_strategy() -> None:
    response = _service().ask(
        ChatRequest(
            message="실시간 뉴스 기반 이벤트 드리븐 운용전략을 알려줘",
            survey_profile=_survey(EducationalRiskProfile.STABLE),
        )
    )

    text = _event_strategy_text(response)
    assert "현재 설문 성향보다 공격적인 이벤트 전술은 제안하지 않아요" in text
    assert "현재 설문 성향 범위에서 전술 관찰 가이드를 제공해요" not in text


def test_live_failure_falls_back_to_recent_stored_news() -> None:
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
    assert any(
        "실시간 조회가 아니라 최근 저장 뉴스 기반입니다" in limitation
        for limitation in response.limitations
    )


def test_empty_stored_news_offers_live_news_exit() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=EmptyStoredNewsRepository(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="증시 뉴스 알려줘"))

    assert "대신 NAVER 검색으로 실시간 증시 뉴스를 볼 수 있어요" in response.answer
    assert [(item.label, item.message) for item in response.suggested_follow_ups] == [
        ("실시간 증시 뉴스 보기", "실시간 증시 뉴스 보여줘")
    ]


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
        "연금 제도 뉴스는 제공하지 않아요" in item
        for item in response.limitations
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


def test_timely_news_uses_live_metadata_without_event_strategy() -> None:
    response = _service().ask(ChatRequest(message="오늘 증시 뉴스 알려줘"))

    assert response.data_mode == "news_metadata"
    assert response.news_items
    assert not any(
        source.evidence_id.startswith("policy:") for source in response.sources
    )
    assert any(
        source.evidence_id.startswith("live-news:") for source in response.sources
    )


def test_timely_news_falls_back_to_stored_news_when_live_lookup_fails() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        news=StoredNewsRepository(),
        live_news=UnavailableLiveNewsSearch(),
        theme_repository=get_default_etf_theme_repository(),
    )

    response = service.ask(ChatRequest(message="오늘 미국 증시 뉴스 알려줘"))

    assert response.data_mode == "news_summary"
    assert response.news_items
    assert response.answer.startswith("실시간 NAVER 조회를 사용할 수 없어")
    assert any(
        "실시간 조회가 아니라 최근 저장 뉴스 기반입니다" in limitation
        for limitation in response.limitations
    )
