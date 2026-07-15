import re
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.app.engine import AccountType


class QueryIntent(StrEnum):
    ACCOUNT_RULE = "account_rule"
    MOCK_PORTFOLIO = "mock_portfolio"
    PROVIDER_DISCLOSURE = "provider_disclosure"
    NEWS = "news"
    OUT_OF_SCOPE = "out_of_scope"


class DisclosureMetric(StrEnum):
    RESERVE_KRW = "reserve_krw"
    EARN_RATE_CURRENT = "earn_rate_current"
    EARN_RATE_1Y = "earn_rate_1y"
    AVG_EARN_RATE_3Y = "avg_earn_rate_3y"
    AVG_EARN_RATE_5Y = "avg_earn_rate_5y"
    AVG_EARN_RATE_7Y = "avg_earn_rate_7y"
    AVG_EARN_RATE_10Y = "avg_earn_rate_10y"
    FEE_RATE_1Y = "fee_rate_1y"


class BlockedReason(StrEnum):
    SENSITIVE_INFORMATION = "sensitive_information"
    FUTURE_PREDICTION = "future_prediction"
    ORDER_REQUEST = "order_request"
    MIXED_ACCOUNT_TYPES = "mixed_account_types"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    INVALID_CLASSIFIER_OUTPUT = "invalid_classifier_output"


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: QueryIntent
    account_type: AccountType | None = None
    provider_name: str | None = Field(default=None, min_length=1, max_length=100)
    metrics: tuple[DisclosureMetric, ...] = ()
    period: str = Field(default="latest", pattern=r"^(latest|20\d{2}Q[1-4])$")
    max_results: int = Field(default=3, ge=1, le=10)
    search_query: str | None = Field(default=None, min_length=1, max_length=200)
    blocked_reason: BlockedReason | None = None

    @model_validator(mode="after")
    def validate_intent_fields(self) -> "QueryPlan":
        if self.intent == QueryIntent.PROVIDER_DISCLOSURE:
            if self.account_type is None:
                raise ValueError("provider_disclosure requires account_type")
            if not self.metrics:
                raise ValueError("provider_disclosure requires metrics")
        elif self.provider_name is not None or self.metrics:
            raise ValueError("provider filters require provider_disclosure intent")

        if self.intent == QueryIntent.NEWS and self.search_query is None:
            raise ValueError("news intent requires search_query")
        if self.intent != QueryIntent.NEWS and self.search_query is not None:
            raise ValueError("search_query is only allowed for news intent")
        if self.intent == QueryIntent.OUT_OF_SCOPE:
            if self.blocked_reason is None:
                raise ValueError("out_of_scope requires blocked_reason")
        elif self.blocked_reason is not None:
            raise ValueError("blocked_reason is only allowed for out_of_scope")
        return self


class AmbiguousQuestionClassifier(Protocol):
    def classify(self, question: str) -> QueryPlan | dict[str, Any]: ...


class ClassifierOutputError(ValueError):
    """The ambiguous-question classifier returned an invalid query plan."""


_RRN = re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)")
_ACCOUNT_NUMBER = re.compile(
    r"(?:계좌\s*번호|account\s*number)\D{0,8}\d{8,16}", re.I
)
_SENSITIVE_WORDS = re.compile(r"주민등록번호|비밀번호|패스워드|OTP|보안카드", re.I)
_ORDER_REQUEST = re.compile(
    r"매수해|매도해|주문해|사\s*줘|팔아\s*줘|대신\s*사|대신\s*팔"
)
_FUTURE_PREDICTION = re.compile(
    r"(?:미래|향후|내년|다음\s*분기).{0,12}(?:수익률|오를|내릴|예측|전망|보장)"
    r"|(?:수익률|가격).{0,12}(?:예측|보장해|확정해)"
)
_SQL_ATTACK = re.compile(
    r"(?:;\s*(?:drop|delete|update|insert|alter|truncate)\b|--|/\*|\bunion\s+select\b)",
    re.I,
)
_PROVIDER = re.compile(
    r"([가-힣A-Za-z0-9&().·-]{2,40}(?:증권|은행|보험|생명|손해보험))"
)
_PERIOD_Q = re.compile(r"(20\d{2})\s*(?:년\s*)?[Qq]?\s*([1-4])\s*(?:분기)?")
_MAX_RESULTS = re.compile(r"(?<!\d)(10|[1-9])\s*(?:개|건)")

_METRIC_ALIASES: tuple[tuple[DisclosureMetric, tuple[str, ...]], ...] = (
    (DisclosureMetric.RESERVE_KRW, ("적립금", "준비금")),
    (DisclosureMetric.EARN_RATE_CURRENT, ("현재 수익률", "당기 수익률")),
    (DisclosureMetric.EARN_RATE_1Y, ("1년 수익률", "연 수익률")),
    (DisclosureMetric.AVG_EARN_RATE_3Y, ("3년 평균", "3년 수익률")),
    (DisclosureMetric.AVG_EARN_RATE_5Y, ("5년 평균", "5년 수익률")),
    (DisclosureMetric.AVG_EARN_RATE_7Y, ("7년 평균", "7년 수익률")),
    (DisclosureMetric.AVG_EARN_RATE_10Y, ("10년 평균", "10년 수익률")),
    (DisclosureMetric.FEE_RATE_1Y, ("수수료", "1년 수수료")),
)


def _out_of_scope(reason: BlockedReason) -> QueryPlan:
    return QueryPlan(intent=QueryIntent.OUT_OF_SCOPE, blocked_reason=reason)


def _account_types(question: str) -> set[AccountType]:
    found: set[AccountType] = set()
    if re.search(r"(?<![A-Za-z])DC(?![A-Za-z])|확정기여형", question, re.I):
        found.add(AccountType.DC)
    if re.search(
        r"(?<![A-Za-z])IRP(?![A-Za-z])|개인형\s*퇴직연금", question, re.I
    ):
        found.add(AccountType.IRP)
    if re.search(r"연금저축", question):
        found.add(AccountType.PENSION_SAVINGS)
    return found


def _period(question: str) -> str:
    match = _PERIOD_Q.search(question)
    return f"{match.group(1)}Q{match.group(2)}" if match else "latest"


def _metrics(question: str, account_type: AccountType) -> tuple[DisclosureMetric, ...]:
    found = [
        metric
        for metric, aliases in _METRIC_ALIASES
        if any(alias in question for alias in aliases)
    ]
    return_metrics = {
        DisclosureMetric.EARN_RATE_CURRENT,
        DisclosureMetric.EARN_RATE_1Y,
        DisclosureMetric.AVG_EARN_RATE_3Y,
        DisclosureMetric.AVG_EARN_RATE_5Y,
        DisclosureMetric.AVG_EARN_RATE_7Y,
        DisclosureMetric.AVG_EARN_RATE_10Y,
    }
    if "수익률" in question and not return_metrics.intersection(found):
        found.append(
            DisclosureMetric.EARN_RATE_1Y
            if account_type == AccountType.PENSION_SAVINGS
            else DisclosureMetric.EARN_RATE_CURRENT
        )
    return tuple(dict.fromkeys(found))


def _max_results(question: str) -> int:
    match = _MAX_RESULTS.search(question)
    return int(match.group(1)) if match else 3


def _rule_based_plan(question: str) -> QueryPlan | None:
    account_types = _account_types(question)
    if len(account_types) > 1:
        return _out_of_scope(BlockedReason.MIXED_ACCOUNT_TYPES)
    account_type = next(iter(account_types), None)

    if re.search(r"뉴스|기사|소식", question):
        return QueryPlan(
            intent=QueryIntent.NEWS,
            account_type=account_type,
            search_query=question,
            max_results=_max_results(question),
        )

    disclosure_terms = re.search(r"공시|수익률|수수료|적립금|준비금", question)
    if disclosure_terms and account_type is not None:
        metrics = _metrics(question, account_type)
        if metrics:
            provider = _PROVIDER.search(question)
            return QueryPlan(
                intent=QueryIntent.PROVIDER_DISCLOSURE,
                account_type=account_type,
                provider_name=provider.group(1) if provider else None,
                metrics=metrics,
                period=_period(question),
                max_results=_max_results(question),
            )

    if re.search(r"목\s*계좌|모의\s*계좌|포트폴리오\s*진단|계좌\s*진단", question):
        return QueryPlan(
            intent=QueryIntent.MOCK_PORTFOLIO,
            account_type=account_type,
        )

    if re.search(r"규칙|제도|한도|세금|인출|차이|위험자산|예외|적격", question):
        return QueryPlan(
            intent=QueryIntent.ACCOUNT_RULE,
            account_type=account_type,
        )
    return None


def plan_question(
    question: str,
    *,
    classifier: AmbiguousQuestionClassifier | None = None,
) -> QueryPlan:
    normalized = " ".join(question.split())
    if not normalized:
        return _out_of_scope(BlockedReason.UNSUPPORTED)
    if (
        _RRN.search(normalized)
        or _ACCOUNT_NUMBER.search(normalized)
        or _SENSITIVE_WORDS.search(normalized)
    ):
        return _out_of_scope(BlockedReason.SENSITIVE_INFORMATION)
    if _ORDER_REQUEST.search(normalized):
        return _out_of_scope(BlockedReason.ORDER_REQUEST)
    if _FUTURE_PREDICTION.search(normalized):
        return _out_of_scope(BlockedReason.FUTURE_PREDICTION)
    if _SQL_ATTACK.search(normalized):
        return _out_of_scope(BlockedReason.UNSUPPORTED)

    deterministic = _rule_based_plan(normalized)
    if deterministic is not None:
        return deterministic
    if classifier is None:
        return _out_of_scope(BlockedReason.AMBIGUOUS)
    try:
        raw_plan = classifier.classify(normalized)
        return (
            raw_plan
            if isinstance(raw_plan, QueryPlan)
            else QueryPlan.model_validate(raw_plan)
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ClassifierOutputError(
            "classifier returned an invalid query plan"
        ) from exc
