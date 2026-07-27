"""Pure contracts for resolving references in Korean multi-turn questions.

This module is intentionally not connected to the production chat pipeline yet.
It defines the small, server-validated boundary that a future context classifier
may use after the colloquial single-turn routing work has settled.
"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..engine import AccountType
from .models import ChatIntent, ChatRequest
from .query_planner import BlockedReason, QueryPlan


class ContextResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFY = "clarify"
    NOT_APPLICABLE = "not_applicable"


class ContextAction(StrEnum):
    DETAIL = "detail"
    COMPARE = "compare"
    FEE = "fee"
    SOURCE = "source"
    ACCOUNT_RULE = "account_rule"
    WITHDRAWAL = "withdrawal"


class ContextReferentKind(StrEnum):
    ACCOUNT = "account"
    NEWS = "news"
    ETF = "etf"


class ContextReferent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    kind: ContextReferentKind


class ContextResolutionPayload(BaseModel):
    """Whitelisted, non-financial context allowed into a classifier prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_message: str = Field(min_length=2, max_length=1000)
    normalized_message: str = Field(min_length=1, max_length=1000)
    last_intent: ChatIntent | None = None
    referents: tuple[ContextReferent, ...] = Field(max_length=12)


class ContextResolutionDecision(BaseModel):
    """Strict classifier output; it cannot contain an answer or rewritten text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ContextResolutionStatus
    action: ContextAction | None = None
    referent_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> "ContextResolutionDecision":
        if len(set(self.referent_ids)) != len(self.referent_ids):
            raise ValueError("referent_ids must not contain duplicates")
        if self.status is ContextResolutionStatus.RESOLVED:
            if self.action is None or not self.referent_ids:
                raise ValueError("resolved decisions require an action and referents")
            return self
        if self.action is not None or self.referent_ids:
            raise ValueError(
                "unresolved decisions must not select an action or referents"
            )
        return self


_REFERENCE_SIGNAL = re.compile(
    r"(?:그거|이거|저거|그것|이것|저것)"
    r"|(?:그|이|해당)\s*(?:계좌|상품|기사|뉴스|전략)"
    r"|아까|방금|그럼|그러면"
    r"|(?:첫|두|둘|세|셋|네|넷|\d)\s*(?:번째|번\s*꺼|번\s*거)"
    r"|두\s*번째|세\s*번째|네\s*번째"
    r"|(?:두|세)\s*(?:계좌|상품|기사|ETF)"
    r"|뭐가\s*더|무엇이\s*더|둘\s*중|셋\s*중"
    r"|아니[^?]{0,12}(?:말고|아니고)",
    re.I,
)

_ELIGIBLE_BLOCKS = {
    BlockedReason.UNSUPPORTED,
    BlockedReason.FEE_TARGET_REQUIRED,
    BlockedReason.ACCOUNT_SELECTION_REQUIRED,
}

_ACCOUNT_LABELS = {
    AccountType.DC: "DC형",
    AccountType.IRP: "IRP",
    AccountType.PENSION_SAVINGS: "연금저축펀드",
}
_NEWS_ORDINALS = ("첫 번째 기사", "두 번째 기사", "세 번째 기사")
_REFERENT_KIND_BY_INTENT = {
    ChatIntent.ACCOUNT_RULE: ContextReferentKind.ACCOUNT,
    ChatIntent.PENSION_TAX: ContextReferentKind.ACCOUNT,
    ChatIntent.PROVIDER_DISCLOSURE: ContextReferentKind.ACCOUNT,
    ChatIntent.NEWS: ContextReferentKind.NEWS,
    ChatIntent.ETF_THEME: ContextReferentKind.ETF,
    ChatIntent.ETF_DISTRIBUTION: ContextReferentKind.ETF,
}


def build_context_resolution_payload(
    request: ChatRequest,
    plan: QueryPlan,
) -> ContextResolutionPayload:
    """Build a classifier payload from server-owned, non-sensitive context only."""

    context = request.conversation_context
    referents: list[ContextReferent] = []
    if context is not None:
        if context.referents is not None:
            kind = _REFERENT_KIND_BY_INTENT.get(context.referents.intent)
            if kind is not None:
                referents.extend(
                    ContextReferent(ref=item.ref, label=item.label, kind=kind)
                    for item in context.referents.items
                )
        if context.account_type is not None:
            referents.append(
                ContextReferent(
                    ref=context.account_type.value,
                    label=_ACCOUNT_LABELS[context.account_type],
                    kind=ContextReferentKind.ACCOUNT,
                )
            )
        if context.news is not None:
            referents.extend(
                ContextReferent(
                    ref=item_id,
                    label=(
                        _NEWS_ORDINALS[index]
                        if index < len(_NEWS_ORDINALS)
                        else f"{index + 1}번째 기사"
                    ),
                    kind=ContextReferentKind.NEWS,
                )
                for index, item_id in enumerate(context.news.news_item_ids)
            )
        if context.etf_theme is not None:
            referents.extend(
                ContextReferent(
                    ref=code,
                    label=name,
                    kind=ContextReferentKind.ETF,
                )
                for code, name in zip(
                    context.etf_theme.candidate_isu_codes,
                    context.etf_theme.candidate_names,
                    strict=True,
                )
            )

    unique_referents = tuple({item.ref: item for item in referents}.values())
    return ContextResolutionPayload(
        raw_message=request.message,
        normalized_message=plan.normalized_message,
        last_intent=context.last_intent if context is not None else None,
        referents=unique_referents,
    )


def is_context_resolution_candidate(
    request: ChatRequest,
    plan: QueryPlan,
) -> bool:
    """Return true only for unresolved, explicitly contextual utterances."""

    if plan.blocked_reason not in _ELIGIBLE_BLOCKS:
        return False
    if _REFERENCE_SIGNAL.search(request.message) is None:
        return False
    return bool(build_context_resolution_payload(request, plan).referents)


def validate_context_resolution_decision(
    decision: ContextResolutionDecision,
    payload: ContextResolutionPayload,
) -> ContextResolutionDecision:
    """Reject invented targets and action/target combinations before replanning."""

    if decision.status is not ContextResolutionStatus.RESOLVED:
        return decision

    referents_by_id = {item.ref: item for item in payload.referents}
    unknown_ids = set(decision.referent_ids) - set(referents_by_id)
    if unknown_ids:
        raise ValueError("decision selected referents outside the supplied context")
    selected = [referents_by_id[item_id] for item_id in decision.referent_ids]

    if decision.action is ContextAction.COMPARE:
        if len(selected) < 2:
            raise ValueError("compare decisions require at least two referents")
        if len({item.kind for item in selected}) != 1:
            raise ValueError("compare decisions require referents of the same kind")
        return decision
    if len(selected) != 1:
        raise ValueError("non-compare decisions require exactly one referent")

    selected_kind = selected[0].kind
    if (
        decision.action in {ContextAction.ACCOUNT_RULE, ContextAction.WITHDRAWAL}
        and selected_kind is not ContextReferentKind.ACCOUNT
    ):
        raise ValueError("account actions require an account referent")
    if (
        decision.action is ContextAction.SOURCE
        and selected_kind is not ContextReferentKind.NEWS
    ):
        raise ValueError("source actions require a news referent")
    if (
        decision.action is ContextAction.FEE
        and selected_kind
        not in {
            ContextReferentKind.ACCOUNT,
            ContextReferentKind.ETF,
        }
    ):
        raise ValueError("fee actions require an account or ETF referent")
    return decision
