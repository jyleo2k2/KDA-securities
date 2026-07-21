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

_NUMBERED_SECTION_HEADING = re.compile(r"^\d+(?:-\d+)?\.\s+")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_MAX_VISIBLE_ANSWER_CHARS = 320


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


def blocked_response(reason: BlockedReason) -> ChatResponse:
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
    if reason == BlockedReason.FUTURE_PREDICTION:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "미래 수익률 예측은 제공하지 않아요. 목표가나 수익 보장도 "
                "안내하지 않아요. 포트폴리오 입력이 있으면 규칙 엔진이 계산한 "
                "장기 계획가정과 과거 위험지표를 설명해 드려요."
            ),
            data_mode="blocked",
            limitations=[
                "LLM의 미래 수익 예측은 지원하지 않습니다.",
                "계획가정은 예측이나 보장 수익률이 아닙니다.",
            ],
        )
    if reason == BlockedReason.ORDER_REQUEST:
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "상품 선택과 주문은 이용자가 직접 해야 해요. 금융회사 공식 "
                "채널을 이용해 주세요. 챗봇은 판단 기준과 근거만 설명해 드려요."
            ),
            data_mode="blocked",
            limitations=["주문·자동운용은 지원하지 않습니다."],
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
        answer=(
            "연금계좌 규칙, 가상계좌 진단, 과거 공시와 뉴스 근거를 안내할 수 "
            "있어요. 질문에 계좌 유형이나 진단할 가상 시나리오를 적어 주세요."
        ),
        data_mode="safe_fallback",
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
    if plan.account_rule_topic == AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW:
        return build_pension_account_overview_response()
    if plan.account_rule_topic is not None:
        return build_deferred_pension_topic_response(plan.account_rule_topic)
    return account_rule_response(request, plan, knowledge=knowledge)
