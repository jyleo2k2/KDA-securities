"""Account-rule retrieval and blocked-response handlers."""


import re

from ...engine import AccountType
from ...retrieval.repository import KnowledgeSearch
from ..models import (
    AnswerSection,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    NumericEvidence,
    SectionKind,
    SuggestedFollowUp,
    extract_numeric_claims,
)
from ..pension_account_overview import (
    build_deferred_pension_topic_response,
    build_pension_account_overview_response,
)
from ..query_planner import AccountRuleTopic, BlockedReason, QueryPlan
from ._shared import (
    _ACCOUNT_TYPE_LABELS,
    _knowledge_evidence_id,
    _knowledge_sources,
    _knowledge_topic,
    _plain_knowledge_excerpt,
    _select_knowledge_match,
)
from .graceful_decline import GracefulDeclineKind, graceful_decline_response

_NUMBERED_SECTION_HEADING = re.compile(r"^\d+(?:-\d+)?\.\s+")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_MEAL_SMALLTALK = re.compile(
    r"배\s*고프|밥.{0,10}(?:먹|뭐)|(?:밥|식사)\s*(?:은|는|도)?\s*(?:했|하셨)",
    re.I,
)
_MAX_VISIBLE_ANSWER_CHARS = 320
_DEFAULT_UNSUPPORTED_ANSWER = (
    "그 질문은 제가 잘 아는 분야는 아니에요. 대신 연금 이야기는 쉽고 "
    "편하게 풀어드릴게요. 아래에서 궁금한 걸 골라봐요."
)
_MEAL_SMALLTALK_ANSWER = (
    "저는 밥을 먹지는 못하지만, 고객님은 식사하셨어요? "
    "연금 이야기도 편하게 물어봐 주세요."
)


def _concise_knowledge_answer(excerpt: str) -> str:
    """Keep the visible lead short while preserving full evidence in sections."""

    lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
    if lines and _NUMBERED_SECTION_HEADING.match(lines[0]):
        lines = lines[1:]
    if lines:
        first_end = _SENTENCE_END.search(lines[0])
        if first_end is not None:
            lines[0] = lines[0][: first_end.end()]
        lines[0] = lines[0].removeprefix("- ")

    selected: list[str] = []
    for line in lines:
        candidate = "\n".join((*selected, line))
        if len(candidate) > _MAX_VISIBLE_ANSWER_CHARS:
            break
        selected.append(line)
    return "\n".join(selected) or excerpt


def _unsupported_answer(user_message: str) -> str:
    if _MEAL_SMALLTALK.search(user_message) is not None:
        return _MEAL_SMALLTALK_ANSWER
    return _DEFAULT_UNSUPPORTED_ANSWER


def blocked_response(reason: BlockedReason, *, user_message: str = "") -> ChatResponse:
    if reason == BlockedReason.SENSITIVE_INFORMATION:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "개인 식별정보나 인증정보가 포함된 질문은 처리하지 않아요. "
                "해당 값을 지운 뒤 제도나 운용 원리만 질문해 주세요."
            ),
            data_mode="blocked",
            limitations=[
                "입력 원문은 검색이나 AI 설명 단계로 전달하지 않았습니다."
            ],
        )
    if reason in {BlockedReason.FUTURE_PREDICTION, BlockedReason.ORDER_REQUEST}:
        return graceful_decline_response(
            GracefulDeclineKind.PREDICTION_OR_ORDER,
            user_message,
        )
    if reason == BlockedReason.FOREIGN_MARKET_OR_INDIVIDUAL_STOCK:
        return graceful_decline_response(
            GracefulDeclineKind.FOREIGN_MARKET_OR_INDIVIDUAL_STOCK,
            user_message,
        )
    if reason == BlockedReason.PRODUCT_LEVEL_UNAVAILABLE:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "현재 데이터는 연금저축 회사와 퇴직연금 사업자 단위로 모여 "
                "있어요. 개별 상품 데이터가 아니어서 상품별 비교·추천은 "
                "제공하지 않아요."
            ),
            data_mode="unavailable",
            limitations=["검증된 개별 상품 식별자와 적격성 데이터가 필요합니다."],
        )
    if reason == BlockedReason.ACCOUNT_SELECTION_REQUIRED:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "공시 수치는 계좌 제도별 항목이 달라 한 번에 섞어 비교하지 "
                "않아요. DC형, IRP, 연금저축 중 하나를 지정해 주세요."
            ),
            data_mode="blocked",
            limitations=["계좌별 공시 계약을 분리해 조회합니다."],
        )
    return ChatResponse(
        intent=ChatIntent.OUT_OF_SCOPE,
        answer=_unsupported_answer(user_message),
        data_mode="safe_fallback",
        suggested_follow_ups=[
            SuggestedFollowUp(
                follow_up_id="fallback_account_diff",
                label="연금계좌별 차이",
                message="DC형, IRP, 연금저축은 뭐가 달라?",
            ),
            SuggestedFollowUp(
                follow_up_id="fallback_tax_credit",
                label="연금 세액공제 계산",
                message="올해 연금저축에 600만원 넣으면 세액공제 얼마야?",
            ),
            SuggestedFollowUp(
                follow_up_id="fallback_educational_portfolio",
                label="맞춤형 포트폴리오",
                message="내 상황에 맞는 연금저축전략을 알려줘.",
            ),
        ],
        limitations=["범용 투자·세무·법률 상담은 지원하지 않습니다."],
    )


def account_rule_response(
    request: ChatRequest,
    plan: QueryPlan,
    *,
    knowledge: KnowledgeSearch,
) -> ChatResponse:
    topic, suffix, title, heading, required = _knowledge_topic(
        request.message, plan
    )
    query = " ".join(
        item
        for item in (
            request.message,
            suffix,
            *(_ACCOUNT_TYPE_LABELS[item] for item in plan.account_types),
        )
        if item
    )
    matches = knowledge.search_knowledge(query, limit=8)
    if not matches:
        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer="검증된 근거 문서를 찾지 못해 답변을 만들지 않았어요.",
            data_mode="verified_knowledge",
            limitations=["질문을 계좌 유형과 함께 더 구체적으로 입력해 주세요."],
        )
    match = _select_knowledge_match(
        matches,
        title=title,
        heading=heading,
        required=required,
    )
    if match is None:
        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer=(
                "검증 근거의 안전성과 질문 주제 적합성을 확인하지 못해 "
                "답변을 만들지 않았어요."
            ),
            data_mode="verified_knowledge",
            limitations=["공식 근거를 재검토한 뒤 다시 안내해야 합니다."],
        )
    sources = _knowledge_sources([match])
    if (
        AccountType.PENSION_SAVINGS in plan.account_types
        and is_eligibility_question(request.message)
    ):
        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer=(
                "연금저축의 상품별 적격성은 공식 상품 식별자와 금융회사 "
                "편입 목록으로 확인해야 해요. 현재 챗봇에는 그 데이터가 "
                "없어서 개별 상품의 편입 가능 여부를 확정하지 않아요."
            ),
            data_mode="verified_knowledge",
            sources=sources,
            limitations=[
                "상품별 적격성은 공식 상품 데이터로 별도 확인해야 합니다."
            ],
        )
    excerpt = _plain_knowledge_excerpt(match.content, heading=heading)
    if topic == "tax_rate":
        excerpt = "\n".join(
            line
            for line in excerpt.splitlines()
            if not ("최대" in line and "환급" in line)
        )
    if not excerpt:
        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer="검증된 근거에서 답변에 쓸 대목을 찾지 못했어요.",
            data_mode="verified_knowledge",
            sources=sources,
            limitations=["질문을 계좌 유형과 함께 더 구체적으로 입력해 주세요."],
        )
    answer = _concise_knowledge_answer(excerpt)
    risk_question = topic == "risk_cap"
    risk_label = (
        "DC형·IRP 위험자산 한도(연금저축 동일 한도 없음)"
        if "DC형·IRP에 적용" in excerpt
        and "연금저축펀드에는 동일한 한도가 없다" in excerpt
        else f"{match.title} 위험자산 한도"
    )
    numeric = [
        NumericEvidence(
            label=(
                risk_label
                if risk_question and unit == "%"
                else f"{match.title} 답변 수치 {index}"
            ),
            value=value,
            unit=unit,
            evidence_id=sources[0].evidence_id,
            basis="검증된 지식 문서에서 직접 발췌",
        )
        for index, (value, unit) in enumerate(
            sorted(extract_numeric_claims(excerpt)), start=1
        )
    ]

    return ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer=answer,
        data_mode="verified_knowledge",
        sections=[
            AnswerSection(
                kind=SectionKind.FACT,
                title="근거에서 확인한 내용",
                content=excerpt,
                evidence_ids=[_knowledge_evidence_id(match)],
            )
        ],
        sources=sources,
        numeric_evidence=numeric,
        limitations=["상품별 적격성은 공식 상품 데이터로 별도 확인해야 합니다."],
    )


def is_eligibility_question(message: str) -> bool:
    return any(term in message for term in ("편입", "적격", "가능한 상품"))


def handle_account_rule(
    request: ChatRequest,
    plan: QueryPlan,
    *,
    knowledge: KnowledgeSearch,
) -> ChatResponse:
    if plan.requests_pension_planner:
        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer=(
                "정확한 수치는 나이와 납입액, 가정에 따라 달라져요. "
                "연금계산기 화면에서 값을 직접 조정해 보시는 게 가장 정확해요."
            ),
            data_mode="pension_planner_redirect",
            suggested_follow_ups=[
                SuggestedFollowUp(
                    follow_up_id="open_pension_planner",
                    label="연금계산기 열기",
                    message="연금계산기 열기",
                )
            ],
            limitations=["미래 수익이나 수령액을 확정하거나 보장하지 않습니다."],
        )
    if plan.account_rule_topic == AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW:
        return build_pension_account_overview_response()
    if plan.account_rule_topic is not None:
        return build_deferred_pension_topic_response(plan.account_rule_topic)
    return account_rule_response(request, plan, knowledge=knowledge)
