import re
from dataclasses import dataclass
from enum import StrEnum

from ..engine import AccountType
from .models import ChatIntent, ChatRequest, MarketRegion

CONTEXTUAL_FOLLOW_UP_TERMS = ("그럼", "그러면", "해당", "이 경우", "그 계좌")
_NEWS_ORDINAL = re.compile(
    r"(?P<first>첫(?:\s*번째)?|1\s*번(?:째)?)|"
    r"(?P<second>두\s*번째|둘째|2\s*번(?:째)?)|"
    r"(?P<third>세\s*번째|셋째|3\s*번(?:째)?)"
)
_NEWS_PRONOUN = re.compile(r"(?:그|이|해당|방금)\s*(?:뉴스|기사|소식)")
_NEWS_COMPARE = re.compile(r"비교|차이")
_NEWS_SOURCE = re.compile(r"출처|원문|링크|언론사|발행|게시|언제|날짜")
_NEWS_REFRESH = re.compile(
    r"새로\s*고침|(?:다른|새로운|새)\s*(?:뉴스|기사|소식)|"
    r"(?:뉴스|기사|소식).{0,8}(?:더|새로|다시)|"
    r"더\s*(?:보여|알려)"
)
_NEWS_KR = re.compile(r"한국|국내|코스피|코스닥")
_NEWS_US = re.compile(r"미국|뉴욕|나스닥|S\s*&\s*P|다우", re.I)


class NewsFollowUpAction(StrEnum):
    DETAIL = "detail"
    COMPARE = "compare"
    SOURCE = "source"
    REFRESH = "refresh"
    REGION = "region"
    CLARIFY = "clarify"


@dataclass(frozen=True, slots=True)
class NewsFollowUp:
    action: NewsFollowUpAction
    item_indexes: tuple[int, ...] = ()
    region: MarketRegion | None = None


class IntentRouter:
    """Add only server-backed context; the safety planner stays authoritative."""

    @classmethod
    def contextual_message(cls, request: ChatRequest) -> str:
        if cls.account_type(request.message) is not None:
            return request.message
        context = request.conversation_context
        if (
            context is not None
            and context.last_intent == ChatIntent.EDUCATIONAL_PORTFOLIO
        ):
            return f"연금 운용 전략 {request.message}"
        if (
            context is None
            or context.account_type is None
            or not cls._is_contextual_follow_up(request.message)
        ):
            return request.message
        return f"{context.account_type.value.upper()} {request.message}"

    @classmethod
    def news_follow_up(cls, request: ChatRequest) -> NewsFollowUp | None:
        context = request.conversation_context
        news = context.news if context is not None else None
        if news is None:
            return None

        message = request.message
        region = (
            MarketRegion.US
            if _NEWS_US.search(message)
            else MarketRegion.KR
            if _NEWS_KR.search(message)
            else None
        )
        if _NEWS_REFRESH.search(message):
            return NewsFollowUp(
                NewsFollowUpAction.REFRESH,
                region=region or news.market_region,
            )

        indexes: list[int] = []
        for match in _NEWS_ORDINAL.finditer(message):
            index = (
                0
                if match.lastgroup == "first"
                else 1
                if match.lastgroup == "second"
                else 2
            )
            if index not in indexes:
                indexes.append(index)

        uses_pronoun = _NEWS_PRONOUN.search(message) is not None
        asks_source = _NEWS_SOURCE.search(message) is not None
        asks_compare = _NEWS_COMPARE.search(message) is not None
        if not indexes and asks_compare:
            indexes = list(range(min(2, len(news.news_item_ids))))
        if not indexes and (uses_pronoun or asks_source):
            if news.focus_news_item_id is not None:
                indexes = [news.news_item_ids.index(news.focus_news_item_id)]
            elif len(news.news_item_ids) == 1:
                indexes = [0]
            else:
                return NewsFollowUp(NewsFollowUpAction.CLARIFY)
        if not indexes and region is not None and (
            "뉴스" in message or cls._is_contextual_follow_up(message)
        ):
            return NewsFollowUp(NewsFollowUpAction.REGION, region=region)
        if not indexes:
            return None
        if any(index >= len(news.news_item_ids) for index in indexes):
            return NewsFollowUp(NewsFollowUpAction.CLARIFY)
        if asks_compare or len(indexes) > 1:
            action = NewsFollowUpAction.COMPARE
        elif asks_source:
            action = NewsFollowUpAction.SOURCE
        else:
            action = NewsFollowUpAction.DETAIL
        return NewsFollowUp(action, tuple(indexes))

    @staticmethod
    def account_type(message: str) -> AccountType | None:
        lower = message.lower()
        if "연금저축" in message:
            return AccountType.PENSION_SAVINGS
        if "irp" in lower:
            return AccountType.IRP
        if "dc" in lower:
            return AccountType.DC
        return None

    @staticmethod
    def _is_contextual_follow_up(message: str) -> bool:
        return any(term in message for term in CONTEXTUAL_FOLLOW_UP_TERMS)
