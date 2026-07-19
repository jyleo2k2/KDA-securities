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
        card_id="portfolio_diag",
        title="내 연금 진단",
        message="내 연금 포트폴리오를 진단해 줘.",
        intent=ChatIntent.MOCK_PORTFOLIO,
        conditions=[CardCondition.REQUIRES_SCENARIO],
        priority=5,
    ),
    ChatCard(
        card_id="edu_portfolio",
        title="성향별 포트폴리오",
        message="내 성향에 맞는 연금 포트폴리오 예시를 보여줘.",
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        conditions=[CardCondition.REQUIRES_SURVEY],
        priority=8,
    ),
    ChatCard(
        card_id="news_kr",
        title="오늘 국내 증시 뉴스",
        message="오늘 국내 증시 뉴스 알려줘.",
        intent=ChatIntent.NEWS,
        priority=10,
    ),
    ChatCard(
        card_id="return_diag",
        title="계좌 수익률 진단",
        message="내 IRP·연금저축 수익률을 진단해 줄래?",
        intent=ChatIntent.MOCK_PORTFOLIO,
        conditions=[CardCondition.REQUIRES_SCENARIO],
        priority=15,
    ),
    ChatCard(
        card_id="age_strategy",
        title="나이별 저축 전략",
        message="내 나이에 맞는 연금 저축 전략을 알려줘.",
        intent=ChatIntent.EDUCATIONAL_PORTFOLIO,
        conditions=[CardCondition.REQUIRES_SURVEY],
        priority=18,
    ),
    ChatCard(
        card_id="news_us",
        title="미국 증시 뉴스",
        message="미국 증시 뉴스 알려줘.",
        intent=ChatIntent.NEWS,
        priority=20,
    ),
    ChatCard(
        card_id="etf_theme_semiconductor",
        title="반도체 ETF 테마",
        message="반도체 테마의 특징과 위험을 알려줘.",
        intent=ChatIntent.ETF_THEME,
        priority=25,
    ),
    ChatCard(
        card_id="tax_credit",
        title="연금 세액공제",
        message="올해 받을 수 있는 연금 세액공제가 궁금해.",
        intent=ChatIntent.PENSION_TAX,
        priority=30,
    ),
    ChatCard(
        card_id="withdrawal_tax",
        title="중도해지 세금",
        message="연금저축을 중도에 해지하면 세금이 얼마나 나와?",
        intent=ChatIntent.PENSION_TAX,
        priority=40,
    ),
    ChatCard(
        card_id="account_diff",
        title="계좌별 차이",
        message="DC형·IRP·연금저축은 뭐가 달라?",
        intent=ChatIntent.ACCOUNT_RULE,
        priority=50,
    ),
    ChatCard(
        card_id="risk_cap",
        title="위험자산 한도",
        message="IRP에서 위험자산은 몇 퍼센트까지 담을 수 있어?",
        intent=ChatIntent.ACCOUNT_RULE,
        priority=60,
    ),
    ChatCard(
        card_id="provider_compare",
        title="IRP 사업자 비교",
        message="증권사별 IRP 수익률을 비교해 줘.",
        intent=ChatIntent.PROVIDER_DISCLOSURE,
        priority=70,
    ),
)


def chat_card_catalog() -> ChatCardCatalog:
    return ChatCardCatalog(cards=list(CHAT_CARDS))


def build_suggested_follow_ups(response: ChatResponse) -> list[SuggestedFollowUp]:
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
    return []
