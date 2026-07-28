import re
from dataclasses import dataclass
from enum import StrEnum

from ..engine import AccountType
from .models import ChatIntent, ChatRequest, MarketRegion

CONTEXTUAL_FOLLOW_UP_TERMS = ("그럼", "그러면", "해당", "이 경우", "그 계좌")
# 직전 전략 대화를 이어 묻는 신호. 계좌 문맥보다 넓게 잡아야 "그 전략의
# 계획수익률"처럼 지시어로 전략을 가리키는 후속 질문을 놓치지 않는다.
_STRATEGY_FOLLOW_UP = re.compile(
    r"그럼|그러면|해당|이\s*경우|"
    r"(?:그|이|위|방금|아까)\s*(?:전략|포트폴리오|배분|비중|구성|결과|추천)|"
    r"(?:그거|이거|저거).{0,16}(?:뭐|왜|이유|장단점|어떻게|운용|굴려|맞|적합|주의|위험)|"
    r"전략(?:의|은|는|을|도|이)|포트폴리오(?:의|은|는|을|도|이)|"
    r"계획수익률|리밸런싱|자산\s*배분|비중"
)
_NEWS_ORDINAL = re.compile(
    r"(?P<first>첫(?:\s*번째)?|1\s*번(?:째)?)|"
    r"(?P<second>두\s*번째|둘째|2\s*번(?:째)?)|"
    r"(?P<third>세\s*번째|셋째|3\s*번(?:째)?)"
)
_REFERENT_ORDINAL = re.compile(
    r"(?P<first>첫(?:\s*번째)?|1\s*번(?:째)?)|"
    r"(?P<second>두\s*번째|둘째|2\s*번(?:째)?)|"
    r"(?P<third>세\s*번째|셋째|3\s*번(?:째)?)|"
    r"(?P<fourth>네\s*번째|넷째|4\s*번(?:째)?)"
)
_REFERENT_PRONOUN = re.compile(
    r"그거|이거|저거|그건|이건|저건|"
    r"(?:그|이|저|해당)\s*(?:계좌|상품)|"
    r"방금\s*(?:그거|그\s*계좌|그\s*상품)|"
    r"아까\s*(?:그거|말한\s*계좌|말한\s*상품)"
)
_REFERENT_LAST = re.compile(r"마지막\s*(?:거|것|계좌|상품)")
_REFERENT_COMPARISON = re.compile(
    r"뭐가\s*더|무엇이\s*더|둘\s*중|셋\s*중|비교"
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


@dataclass(frozen=True, slots=True)
class ResolvedReferent:
    intent: ChatIntent
    topic: str | None
    ref: str
    label: str


class IntentRouter:
    """Add only server-backed context; the safety planner stays authoritative."""

    @classmethod
    def contextual_message(cls, request: ChatRequest) -> str:
        if cls.account_type(request.message) is not None:
            return request.message
        context = request.conversation_context
        referent = cls.resolve_referent(request)
        if referent is not None:
            return f"{referent.label} {request.message}"
        if (
            context is not None
            and context.referents is not None
            and cls._is_referent_request(request.message)
        ):
            return request.message
        # 직전이 전략 대화였어도 "그럼"처럼 이어 묻는 신호가 있을 때만 문맥을
        # 덧붙인다. 신호 없는 질문까지 전략 요청으로 승격하면, 분류기가 놓친
        # 오타 한 글자가 엉뚱한 전략·리밸런싱 답변으로 이어진다.
        if (
            context is not None
            and context.last_intent == ChatIntent.EDUCATIONAL_PORTFOLIO
            and _STRATEGY_FOLLOW_UP.search(request.message) is not None
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
    def resolve_referent(cls, request: ChatRequest) -> ResolvedReferent | None:
        context = request.conversation_context
        referents = context.referents if context is not None else None
        if referents is None or referents.intent in {
            ChatIntent.NEWS,
            ChatIntent.ETF_THEME,
        } or "테마" in request.message:
            return None

        ordinal = cls._ordinal_index(request.message)
        if ordinal is not None:
            if ordinal >= len(referents.items):
                return None
            item = referents.items[ordinal]
            return ResolvedReferent(
                intent=referents.intent,
                topic=referents.topic,
                ref=item.ref,
                label=item.label,
            )
        if _REFERENT_LAST.search(request.message) is not None:
            item = referents.items[-1]
            return ResolvedReferent(
                intent=referents.intent,
                topic=referents.topic,
                ref=item.ref,
                label=item.label,
            )
        if _REFERENT_PRONOUN.search(request.message) is None:
            return None
        if len(referents.items) != 1:
            return None
        item = referents.items[0]
        return ResolvedReferent(
            intent=referents.intent,
            topic=referents.topic,
            ref=item.ref,
            label=item.label,
        )

    @classmethod
    def needs_referent_clarification(cls, request: ChatRequest) -> bool:
        context = request.conversation_context
        referents = context.referents if context is not None else None
        if referents is None or cls.resolve_referent(request) is not None:
            return False
        message = request.message
        if "테마" in message:
            return False
        normalized_message = message.upper()
        if any(
            item.label.upper() in normalized_message
            or item.ref.upper() in normalized_message
            for item in referents.items
        ):
            return False
        return (
            _REFERENT_ORDINAL.search(message) is not None
            or _REFERENT_PRONOUN.search(message) is not None
            or _REFERENT_LAST.search(message) is not None
            or _REFERENT_COMPARISON.search(message) is not None
        )

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

    @staticmethod
    def _ordinal_index(message: str) -> int | None:
        match = _REFERENT_ORDINAL.search(message)
        if match is None:
            return None
        return {
            "first": 0,
            "second": 1,
            "third": 2,
            "fourth": 3,
        }[match.lastgroup]

    @staticmethod
    def _is_referent_request(message: str) -> bool:
        return (
            _REFERENT_ORDINAL.search(message) is not None
            or _REFERENT_PRONOUN.search(message) is not None
            or _REFERENT_LAST.search(message) is not None
            or _REFERENT_COMPARISON.search(message) is not None
        )
