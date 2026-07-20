"""Static guide-page cards and deterministic in-conversation follow-ups."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .models import ChatIntent, ChatResponse, MarketRegion, SuggestedFollowUp


class CardCondition(StrEnum):
    REQUIRES_SCENARIO = "requires_scenario"
    REQUIRES_SURVEY = "requires_survey"
    REQUIRES_AUTH = "requires_auth"


class ChatCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    card_id: str
    title: str
    message: str
    intent: ChatIntent
    conditions: list[CardCondition] = Field(default_factory=list)
    priority: int
    preview: str | None = None


class ChatCardCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cards: list[ChatCard] = Field(default_factory=list)


CHAT_CARDS = (
    ChatCard(
        card_id="news_market",
        title="오늘 증시 뉴스",
        message="오늘 증시 뉴스 알려줘.",
        intent=ChatIntent.NEWS,
        priority=10,
    ),
    ChatCard(
        card_id="tax_credit",
        title="연금세액공제",
        message="올해 받을 수 있는 연금세액공제가 궁금해.",
        intent=ChatIntent.PENSION_TAX,
        priority=20,
    ),
    ChatCard(
        card_id="withdrawal_tax",
        title="중도해지 세금",
        message="연금계좌를 중도에 해지하면 어떻게 돼?",
        intent=ChatIntent.ACCOUNT_RULE,
        priority=30,
    ),
    ChatCard(
        card_id="account_diff",
        title="연금계좌별 차이",
        message="DC형, IRP, 연금저축은 뭐가 달라?",
        intent=ChatIntent.ACCOUNT_RULE,
        priority=40,
    ),
    ChatCard(
        card_id="edu_portfolio",
        title="맞춤형 포트폴리오",
        message="내 상황에 맞는 연금저축전략을 알려줘.",
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        priority=50,
    ),
)


def chat_card_catalog() -> ChatCardCatalog:
    return ChatCardCatalog(cards=list(CHAT_CARDS))


def build_suggested_follow_ups(response: ChatResponse) -> list[SuggestedFollowUp]:
    if response.data_mode in {
        "live_news_event_strategy",
        "stored_news_event_strategy",
    }:
        return [
            SuggestedFollowUp(
                follow_up_id="live_news_kr_strategy",
                label="국내 뉴스 전술 가이드",
                message="국내 실시간 뉴스 기반 운용전략을 보여줘",
            ),
            SuggestedFollowUp(
                follow_up_id="live_news_us_strategy",
                label="미국 뉴스 전술 가이드",
                message="미국 실시간 뉴스 기반 운용전략을 보여줘",
            ),
        ]
    if response.intent == ChatIntent.NEWS and response.news_items:
        follow_ups = [
            SuggestedFollowUp(
                follow_up_id="news_detail_1",
                label="첫 번째 뉴스 자세히",
                message="첫 번째 뉴스 자세히 알려줘",
            )
        ]
        region = (
            response.conversation_context.news.market_region
            if response.conversation_context is not None
            and response.conversation_context.news is not None
            else MarketRegion.ALL
        )
        if region == MarketRegion.KR:
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="news_region_us",
                    label="미국 증시 뉴스도 보기",
                    message="미국 증시 뉴스도 보여줘",
                )
            )
        elif region == MarketRegion.US:
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="news_region_kr",
                    label="국내 증시 뉴스도 보기",
                    message="국내 증시 뉴스도 보여줘",
                )
            )
        follow_ups.append(
            SuggestedFollowUp(
                follow_up_id="news_refresh",
                label="다른 뉴스 더 보기",
                message="다른 뉴스 더 보여줘",
            )
        )
        return follow_ups
    if response.intent == ChatIntent.MOCK_PORTFOLIO:
        return [
            SuggestedFollowUp(
                follow_up_id="mock_risk_cap",
                label="위험자산 한도 기준",
                message="IRP 위험자산 한도 기준이 궁금해",
            ),
            SuggestedFollowUp(
                follow_up_id="mock_tax",
                label="연금 세액공제 계산",
                message="연금 세액공제도 계산해 줘",
            ),
        ]
    if (
        response.intent == ChatIntent.PENSION_TAX
        and response.pension_tax_result is not None
        and response.pension_tax_result.tax_credit is not None
    ):
        return [
            SuggestedFollowUp(
                follow_up_id="tax_withdrawal",
                label="중도해지 세금",
                message="연금저축을 중도에 해지하면 세금이 얼마나 나와?",
            )
        ]
    if response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO:
        return [
            SuggestedFollowUp(
                follow_up_id="education_risk_cap",
                label="위험자산 한도 적용",
                message="연금계좌의 위험자산 한도는 어떻게 적용돼?",
            )
        ]
    if response.intent == ChatIntent.ETF_THEME and response.sections:
        marker = " 테마"
        title = response.sections[0].title
        marker_position = title.find(marker)
        if marker_position <= 0:
            return []
        theme_name = title[:marker_position]
        follow_ups: list[SuggestedFollowUp] = []
        if response.data_mode == "theme_overview":
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="theme_representative_companies",
                    label="테마 대표기업",
                    message=f"{theme_name} 테마 대표기업은 뭐야?",
                )
            )
        elif response.data_mode != "theme_performance_drivers":
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="theme_performance_drivers",
                    label="성과 관찰요인",
                    message=(
                        f"{theme_name} 테마 성과에 영향을 주는 요인은 뭐야?"
                    ),
                )
            )
        if response.data_mode not in {
            "theme_risks",
            "theme_investment_considerations",
        }:
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="theme_pros_cons",
                    label="테마 장단점",
                    message=(
                        f"{theme_name} 테마 ETF에 투자할 때 장단점을 알려줘"
                    ),
                )
            )
        if response.data_mode != "theme_candidates":
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="theme_products",
                    label="테마 ETF상품",
                    message=f"{theme_name} 테마 ETF상품 3개를 보여줘",
                )
            )
        elif not any(
            section.title.endswith("주요 구성종목")
            for section in response.sections
        ):
            follow_ups.append(
                SuggestedFollowUp(
                    follow_up_id="theme_holdings",
                    label="구성종목 확인",
                    message=f"{theme_name} ETF 구성종목 비중을 보여줘",
                )
            )
        return follow_ups[:3]
    return []
