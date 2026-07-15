import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..engine import AccountType
from ..text_normalization import normalize_search_text
from .models import ChatIntent


class BlockedReason(StrEnum):
    SENSITIVE_INFORMATION = "sensitive_information"
    FUTURE_PREDICTION = "future_prediction"
    ORDER_REQUEST = "order_request"
    PRODUCT_LEVEL_UNAVAILABLE = "product_level_unavailable"
    ACCOUNT_SELECTION_REQUIRED = "account_selection_required"
    UNSUPPORTED = "unsupported"


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_message: str = Field(min_length=1, max_length=1000)
    intent: ChatIntent
    account_types: tuple[AccountType, ...] = ()
    news_query: str | None = Field(default=None, min_length=1, max_length=200)
    max_results: int = Field(default=3, ge=1, le=5)
    combines_account_rules: bool = False
    blocked_reason: BlockedReason | None = None

    @model_validator(mode="after")
    def verify_intent_fields(self) -> "QueryPlan":
        if self.intent == ChatIntent.NEWS and self.news_query is None:
            raise ValueError("news intent requires news_query")
        if self.intent != ChatIntent.NEWS and self.news_query is not None:
            raise ValueError("news_query is only valid for news intent")
        if self.intent == ChatIntent.OUT_OF_SCOPE and self.blocked_reason is None:
            raise ValueError("out_of_scope intent requires blocked_reason")
        if self.intent != ChatIntent.OUT_OF_SCOPE and self.blocked_reason is not None:
            raise ValueError("blocked_reason is only valid for out_of_scope")
        return self


_RRN = re.compile(r"(?<!\d)\d{6}[ -]?[1-8]\d{6}(?!\d)")
_ACCOUNT_NUMBER = re.compile(
    r"(?:계좌\s*번호|account\s*(?:number|no\.?))"
    r"\s*(?:은|는|:|=)?\s*(?:\d[ -]?){8,20}",
    re.I,
)
_SECRET_AFTER_LABEL = re.compile(
    r"(?:비밀번호|패스워드|password)\s*(?:은|는|:|=)\s*"
    r"[A-Za-z0-9!@#$%^&*_.-]{4,}"
    r"|(?:OTP|보안카드(?:\s*번호)?)\s*(?:은|는|:|=)?\s*\d{4,}",
    re.I,
)
_SECRET_BEFORE_LABEL = re.compile(
    r"[A-Za-z0-9!@#$%^&*_.-]{4,}\s*(?:이|가|은|는)\s*"
    r"(?:비밀번호|패스워드|password|OTP|보안카드(?:\s*번호)?)",
    re.I,
)
_ORDER_REQUEST = re.compile(
    r"매수해|매도해|주문해|사\s*줘|팔아\s*줘|대신\s*사|대신\s*팔|자동\s*투자"
)
_FUTURE_PREDICTION = re.compile(
    r"(?:미래|향후|내년|다음\s*분기).{0,15}"
    r"(?:수익률|오를|내릴|예측|전망|보장)"
    r"|(?:수익률|가격).{0,15}(?:예측|보장|확정)|목표가"
)
_PRODUCT_LEVEL = re.compile(r"개별\s*상품|상품\s*추천|상품\s*비교|판매\s*중인\s*상품")
_COMBINED_ACCOUNT_RULE = re.compile(
    r"(?:합쳐|합산|통합).{0,20}(?:위험자산|한도|70\s*%)"
    r"|(?:위험자산|한도|70\s*%).{0,20}(?:합쳐|합산|통합)"
)
_DISCLOSURE_TERMS = re.compile(r"공시|수익률|수수료|적립금|준비금|사업자|회사")
_NEWS_TERMS = re.compile(r"뉴스|기사|소식")
_RULE_TERMS = re.compile(
    r"규칙|제도|한도|세금|인출|차이|위험자산|예외|적격|연금|TDF", re.I
)
_SCENARIO_TERMS = re.compile(
    r"목\s*계좌|모의\s*계좌|내\s*계좌|포트폴리오\s*진단|계좌\s*진단|방치|편중|중복"
)
_COUNT = re.compile(r"(?<!\d)([1-5])\s*(?:개|건)(?:만)?(?!\d)")
_KOREAN_COUNT = (
    (re.compile(r"(?:한\s*(?:개|건)|하나)(?:만)?"), 1),
    (re.compile(r"(?:두\s*(?:개|건)|둘)(?:만)?"), 2),
    (re.compile(r"(?:세\s*(?:개|건)|셋)(?:만)?"), 3),
    (re.compile(r"(?:네\s*(?:개|건)|넷)(?:만)?"), 4),
    (re.compile(r"(?:다섯\s*(?:개|건))(?:만)?"), 5),
)
_NEWS_REQUEST_WORDS = re.compile(
    r"가장|최신|최근|뉴스|기사|소식|네이버|검색(?:해\s*줘)?|"
    r"찾아\s*줘|알려\s*줘|보여\s*줘|해\s*줘"
)


def _account_types(message: str) -> tuple[AccountType, ...]:
    found: list[AccountType] = []
    if re.search(r"(?<![A-Za-z])DC(?![A-Za-z])|확정기여형", message, re.I):
        found.append(AccountType.DC)
    if re.search(
        r"(?<![A-Za-z])IRP(?![A-Za-z])|개인형\s*퇴직연금", message, re.I
    ):
        found.append(AccountType.IRP)
    if "연금저축" in message:
        found.append(AccountType.PENSION_SAVINGS)
    return tuple(found)


def _contains_sensitive_information(message: str) -> bool:
    return any(
        pattern.search(message)
        for pattern in (
            _RRN,
            _ACCOUNT_NUMBER,
            _SECRET_AFTER_LABEL,
            _SECRET_BEFORE_LABEL,
        )
    )


def _max_results(message: str, default: int) -> int:
    match = _COUNT.search(message)
    if match is not None:
        return int(match.group(1))
    for pattern, value in _KOREAN_COUNT:
        if pattern.search(message):
            return value
    return max(1, min(default, 5))


def _news_query(message: str) -> str:
    query = _COUNT.sub(" ", message)
    for pattern, _ in _KOREAN_COUNT:
        query = pattern.sub(" ", query)
    query = _NEWS_REQUEST_WORDS.sub(" ", query)
    return normalize_search_text(query)[:200].rstrip() or "연금"


def _blocked(message: str, reason: BlockedReason, max_results: int) -> QueryPlan:
    return QueryPlan(
        normalized_message=message,
        intent=ChatIntent.OUT_OF_SCOPE,
        max_results=max_results,
        blocked_reason=reason,
    )


def plan_question(message: str, *, default_max_results: int = 3) -> QueryPlan:
    normalized = normalize_search_text(message)
    max_results = _max_results(normalized, default_max_results)
    if not normalized:
        return _blocked("질문 없음", BlockedReason.UNSUPPORTED, max_results)
    if _contains_sensitive_information(normalized):
        return _blocked(
            normalized, BlockedReason.SENSITIVE_INFORMATION, max_results
        )
    if _ORDER_REQUEST.search(normalized):
        return _blocked(normalized, BlockedReason.ORDER_REQUEST, max_results)
    if _FUTURE_PREDICTION.search(normalized):
        return _blocked(normalized, BlockedReason.FUTURE_PREDICTION, max_results)
    if _PRODUCT_LEVEL.search(normalized):
        return _blocked(
            normalized, BlockedReason.PRODUCT_LEVEL_UNAVAILABLE, max_results
        )

    account_types = _account_types(normalized)
    if _NEWS_TERMS.search(normalized):
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.NEWS,
            account_types=account_types,
            news_query=_news_query(normalized),
            max_results=max_results,
        )
    if _DISCLOSURE_TERMS.search(normalized) and account_types:
        if len(account_types) > 1:
            return _blocked(
                normalized,
                BlockedReason.ACCOUNT_SELECTION_REQUIRED,
                max_results,
            )
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.PROVIDER_DISCLOSURE,
            account_types=account_types,
            max_results=max_results,
        )
    if _SCENARIO_TERMS.search(normalized):
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.MOCK_PORTFOLIO,
            account_types=account_types,
            max_results=max_results,
        )
    if account_types or _RULE_TERMS.search(normalized):
        return QueryPlan(
            normalized_message=normalized,
            intent=ChatIntent.ACCOUNT_RULE,
            account_types=account_types,
            max_results=max_results,
            combines_account_rules=(
                len(account_types) > 1
                and _COMBINED_ACCOUNT_RULE.search(normalized) is not None
            ),
        )
    return _blocked(normalized, BlockedReason.UNSUPPORTED, max_results)
