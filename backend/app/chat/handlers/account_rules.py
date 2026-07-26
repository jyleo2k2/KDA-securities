"""Account-rule retrieval and blocked-response handlers."""


import re

from ...engine import AccountType
from ...retrieval.repository import KnowledgeSearch
from ..models import (
    AnswerBlock,
    AnswerBlockKind,
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
_MAX_VISIBLE_ANSWER_CHARS = 320

# 근거 발췌는 승인 문서 원문이라 '-한다'체다. 내레이션이 폴백되면 이 원문이
# 그대로 첫 문장이 되어 한 대화 안에서 말투가 튄다. 원문을 고쳐 쓰면 출처 칩이
# 가리키는 문장과 화면 문장이 달라지므로, 원문은 그대로 두고 앞에 해요체 결론을
# 한 줄 얹는다. 결론 문장은 뒤따르는 발췌에 이미 있는 사실만 말한다.
#
# 실제 폴백이 관측된 주제만 넣는다. 없는 주제는 종전처럼 발췌로 시작한다.
# 한 주제가 서로 다른 물음을 함께 받을 때는 heading으로 갈라낸다. 담보대출과
# 중도인출은 같은 withdrawal_requirements를 쓰지만 결론이 다르다.
_TOPIC_LEAD = {
    "3. 담보대출과 중도인출은 다르다": (
        "담보대출과 중도인출은 다른 제도라서, 가능한 조건과 상환 의무가 서로 "
        "달라요."
    ),
    "risk_cap": (
        "DC형과 IRP는 위험자산을 70%까지 담을 수 있고, 연금저축펀드에는 이 "
        "한도가 없어요."
    ),
    "tax_limit": (
        "세액공제를 받을 수 있는 납입액과 실제로 넣을 수 있는 납입액은 한도가 "
        "달라요."
    ),
    "withdrawal_requirements": (
        "중도인출은 자유로운 출금이 아니라 법에서 정한 사유와 증빙을 갖췄을 "
        "때만 가능해요."
    ),
    "receipt_start": "연금으로 받으려면 나이와 가입 기간 요건을 함께 채워야 해요.",
    "retirement_benefit_transfer": (
        "퇴직급여는 원칙적으로 본인이 지정한 IRP 계좌로 이전해서 받아요."
    ),
    "in_kind_transfer": (
        "금융회사를 옮길 때는 상품을 팔지 않고 그대로 이전할 수 있는 경우와 "
        "그렇지 않은 경우가 나뉘어요."
    ),
    "receipt_tax": (
        "같은 돈이라도 연금으로 나눠 받을 때와 일시금으로 받을 때 세금이 "
        "달라져요."
    ),
    "tax_rate": "세액공제율은 소득 구간에 따라 갈려요.",
    "account_opening": (
        "연금저축·IRP는 직접 열 수 있고, DC형은 회사를 통해 가입해요."
    ),
    "investable_assets": (
        "연금계좌에서는 개별 주식은 담을 수 없고 ETF와 펀드를 활용해요."
    ),
}
_ACCOUNT_BRIEF_QUESTION = re.compile(
    r"차이|비교|특징|"
    r"(?:란|은|는|이|가)\s*(?:뭐|무엇)|"
    r"어떤\s*(?:계좌|연금)|설명|알려",
    re.I,
)
_ACCOUNT_BRIEF_ONLY = re.compile(
    r"(?:DC|IRP|연금저축펀드)",
    re.I,
)
_ACCOUNT_BRIEF_NARROW_TOPIC = re.compile(
    r"위험\s*자산|한도|세액\s*공제|공제율|중도\s*인출|해지|"
    r"수령|세금|과세|편입|상품|수익률|납입",
    re.I,
)
_PENSION_TAX_RULE_BRIEF_QUESTION = re.compile(
    r"연금\s*계좌.{0,16}(?:세액\s*공제\s*(?:혜택|제도)|납입\s*규칙|규칙)",
    re.I,
)
# 계좌를 지목하지 않고 연금 자체의 뜻을 묻는 말. "연금저축이 뭐야"처럼 특정
# 계좌를 물으면 연금 바로 뒤가 이어지는 낱말이라 여기에 걸리지 않는다.
_PENSION_DEFINITION_QUESTION = re.compile(
    r"연금\s*(?:이란|이라는|은|는|이|을|를)?\s*"
    r"(?:뭐|뭔지|무엇|어떤\s*(?:거|것|제도))",
    re.I,
)
_ACCOUNT_BRIEF_ORDER = (
    AccountType.PENSION_SAVINGS,
    AccountType.IRP,
    AccountType.DC,
)
# "연금이 뭐야"는 제도 정의를 묻는 말이다. 규칙을 나열하기 전에 무엇을 위한
# 돈인지 한 번에 그려주고, 우리가 다루는 계좌 세 가지로 자연스럽게 잇는다.
_PENSION_DEFINITION = (
    "연금은 일해서 버는 동안 소득의 일부를 미리 떼어 두었다가, 더 이상 "
    "일하지 않는 나이가 됐을 때 나눠 받는 돈이에요. 지금의 내가 나중의 "
    "나에게 월급을 보내주는 셈이죠.\n\n"
    "여기서는 그중 스스로 넣고 굴리는 연금저축·IRP·DC형 세 가지를 다뤄요."
)
_ACCOUNT_BRIEF_COPY = {
    AccountType.PENSION_SAVINGS: (
        "연금저축펀드: 절세하면서 비교적 자유롭게 투자하는 개인 연금",
        (
            "펀드와 국내 상장 ETF를 담을 수 있고, 퇴직연금과 달리 위험자산 "
            "70% 제한이 없어요."
        ),
    ),
    AccountType.IRP: (
        (
            "개인형 퇴직연금(IRP): 세액공제 한도를 확대하고 퇴직금을 모아 "
            "관리하는 개인 퇴직연금"
        ),
        (
            "세액공제 한도를 600만 원에서 900만 원까지 넓혀 주고, 여러 직장의 "
            "퇴직금을 한 계좌에 모을 수 있어요."
        ),
    ),
    AccountType.DC: (
        (
            "DC형 퇴직연금: 회사가 납입하는 퇴직급여를 근로자가 직접 "
            "투자하는 퇴직연금"
        ),
        (
            "회사가 넣어준 돈을 내가 직접 굴리고, 그 결과가 퇴직급여에 그대로 "
            "반영돼요."
        ),
    ),
}
_DEFAULT_UNSUPPORTED_ANSWER = (
    "그 질문은 제가 잘 아는 분야는 아니에요. 대신 연금 이야기는 쉽고 "
    "편하게 풀어드릴게요. 아래에서 궁금한 걸 골라봐요."
)
_SMALLTALK_RULES = (
    (
        re.compile(
            r"배\s*고프|밥.{0,10}(?:먹|뭐)"
            r"|(?:밥|식사)\s*(?:은|는|도)?\s*(?:했|하셨)",
            re.I,
        ),
        "저는 밥을 먹지는 못하지만, 고객님은 식사하셨어요? "
        "연금 이야기도 편하게 물어봐 주세요.",
    ),
    (
        re.compile(r"잘\s*가|다음에\s*봐|또\s*보자|안녕히", re.I),
        "다음에 또 만나요, 고객님. 연금이 궁금할 때 언제든 편하게 찾아와 주세요.",
    ),
    (
        re.compile(r"안녕|하이|헬로|반가워", re.I),
        "안녕하세요, 고객님! 만나서 반가워요. 오늘은 어떤 이야기를 나눠볼까요?",
    ),
    (
        re.compile(r"(?:너|네|니|챗봇).{0,6}(?:이름|누구)|정체가\s*뭐", re.I),
        "제 이름은 연그미예요. 어렵게 느껴지는 연금 이야기를 "
        "편하게 풀어드리는 친구예요.",
    ),
    (
        re.compile(r"(?:너|네|니).{0,6}(?:몇\s*살|나이)", re.I),
        "저는 나이를 먹지는 않지만, 고객님의 든든한 노후 준비는 "
        "오래 함께 도와드릴 수 있어요.",
    ),
    (
        re.compile(r"뭐\s*해|뭐하니|잘\s*지내|기분\s*어때", re.I),
        "저는 여기서 고객님의 질문을 기다리고 있어요. "
        "고객님은 오늘 어떻게 지내고 계세요?",
    ),
    (
        re.compile(r"피곤|졸려|잠\s*와|쉬고\s*싶", re.I),
        "오늘 조금 지치셨나 봐요. 잠깐 쉬어가도 괜찮아요. "
        "연금 이야기는 준비되실 때 편하게 이어가요.",
    ),
    (
        re.compile(r"고마워|감사(?:해|합니다)?|너\s*최고|잘했어", re.I),
        "고마워요, 고객님! 도움이 됐다니 저도 기뻐요. "
        "다른 궁금한 것도 편하게 물어봐 주세요.",
    ),
    (
        re.compile(r"농담|웃겨\s*줘|재밌는\s*말", re.I),
        "연금이 급하게 뛰지 않는 이유는 뭘까요? 오래오래 가는 게 더 중요해서래요. "
        "연금 이야기도 이렇게 편하게 물어봐 주세요.",
    ),
    (
        re.compile(r"날씨|비\s*(?:와|오)|눈\s*(?:와|오)|더워|추워", re.I),
        "실시간 날씨는 확인할 수 없지만, 외출 전 날씨 앱을 한 번 확인해 보세요. "
        "저는 연금 궁금증을 편하게 풀어드릴게요.",
    ),
    (
        re.compile(r"심심", re.I),
        "심심하셨군요. 저와 가볍게 이야기 나눠도 좋아요. "
        "연금이 궁금한 것도 편하게 꺼내 주세요.",
    ),
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
    for pattern, answer in _SMALLTALK_RULES:
        if pattern.search(user_message) is not None:
            return answer
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
    if reason == BlockedReason.CONTRIBUTION_AMOUNT_ADVICE:
        return graceful_decline_response(
            GracefulDeclineKind.CONTRIBUTION_AMOUNT_ADVICE,
            user_message,
        )
    if reason == BlockedReason.PROVIDER_CHOICE_ADVICE:
        return graceful_decline_response(
            GracefulDeclineKind.PROVIDER_CHOICE_ADVICE,
            user_message,
        )
    if reason == BlockedReason.PERSONAL_ALLOCATION_ADVICE:
        return graceful_decline_response(
            GracefulDeclineKind.PERSONAL_ALLOCATION_ADVICE,
            user_message,
        )
    if reason == BlockedReason.PRINCIPAL_GUARANTEE_QUESTION:
        return graceful_decline_response(
            GracefulDeclineKind.PRINCIPAL_GUARANTEE_QUESTION,
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
    # heading이 더 구체적이므로 먼저 찾는다(담보대출 vs 중도인출).
    # heading이 더 구체적이므로 먼저 찾는다(담보대출 vs 중도인출).
    lead = _TOPIC_LEAD.get(heading) or _TOPIC_LEAD.get(topic)
    if lead is not None:
        # 두괄식: 결론이 첫 문장, 그 근거인 원문이 뒤따른다.
        answer = f"{lead}\n{answer}"
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


def _requests_account_brief(request: ChatRequest, plan: QueryPlan) -> bool:
    # 계좌를 지목하지 않은 물음은 원래 전용 응답(전체 정리·수령 요건 등)으로
    # 간다. 제도 자체의 뜻을 묻는 경우만 예외로 짧은 소개를 쓴다.
    if not plan.account_types and not _asks_pension_definition(request.message, plan):
        return False
    if _ACCOUNT_BRIEF_NARROW_TOPIC.search(request.message):
        return False
    return (
        plan.account_rule_topic == AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW
        or _ACCOUNT_BRIEF_QUESTION.search(request.message) is not None
        or _ACCOUNT_BRIEF_ONLY.fullmatch(request.message.strip()) is not None
    )


def _asks_pension_definition(message: str, plan: QueryPlan) -> bool:
    """계좌를 지목하지 않고 연금 자체의 뜻을 물었는지 판단한다."""

    if plan.account_types:
        return False
    return _PENSION_DEFINITION_QUESTION.search(message) is not None


def _account_brief_response(
    account_types: tuple[AccountType, ...],
    *,
    define_pension: bool = False,
) -> ChatResponse:
    selected = tuple(
        account_type
        for account_type in _ACCOUNT_BRIEF_ORDER
        if account_type in account_types
    )
    # "연금이 뭐야"처럼 계좌를 지목하지 않은 물음은 세 계좌를 모두 보여준다.
    if not selected:
        selected = _ACCOUNT_BRIEF_ORDER
    account_cards: list[AnswerBlock] = []
    account_titles: list[str] = []
    for account_type in selected:
        title, summary = _ACCOUNT_BRIEF_COPY[account_type][0].split(": ", 1)
        account_titles.append(title)
        account_cards.append(
            AnswerBlock(
                kind=AnswerBlockKind.CALLOUT,
                title=title,
                text=(
                    f"한눈에 보면: {summary}\n\n"
                    f"핵심 특징: {' '.join(_ACCOUNT_BRIEF_COPY[account_type][1:])}"
                ),
            )
        )

    if selected == _ACCOUNT_BRIEF_ORDER:
        answer = "연금계좌별 특징을 정리했어요."
        section_title = "연금계좌별 차이"
        section_content = "각 계좌의 역할과 특징을 비교해 보세요."
    elif len(selected) == 1:
        answer = f"{account_titles[0]}의 핵심 특징을 정리했어요."
        section_title = f"{account_titles[0]} 특징"
        section_content = "이 계좌의 역할과 핵심 특징을 확인해 보세요."
    else:
        answer = f"{'·'.join(account_titles)}의 차이를 정리했어요."
        section_title = f"{'·'.join(account_titles)} 차이"
        section_content = "두 계좌의 역할과 특징을 비교해 보세요."

    # 정의를 물었으면 규칙보다 "연금이 무엇인지"를 먼저 말한다.
    if define_pension:
        answer = _PENSION_DEFINITION

    evidence_id = "rule:pension_overview:law"
    section = AnswerSection(
        kind=SectionKind.SERVICE_EXPLANATION,
        title=section_title,
        content=section_content,
        evidence_ids=[evidence_id],
        blocks=account_cards,
    )
    evidence_text = "\n".join(
        (
            answer,
            section.plain_text(),
        )
    )
    overview = build_pension_account_overview_response()
    numeric_evidence = [
        NumericEvidence(
            label=f"연금계좌 특징 수치 근거 {index}",
            value=value,
            unit=unit,
            evidence_id=evidence_id,
            basis="검증된 연금계좌 제도 근거",
        )
        for index, (value, unit) in enumerate(
            sorted(extract_numeric_claims(evidence_text)),
            start=1,
        )
    ]
    return ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer=answer,
        data_mode="verified_pension_account_brief",
        sections=[section],
        sources=overview.sources,
        numeric_evidence=numeric_evidence,
        limitations=overview.limitations,
    )


def _pension_tax_rule_brief_response() -> ChatResponse:
    tax_credit_source = "rule:pension_overview:tax_credit"
    receipt_source = "rule:pension_overview:receipt"
    law_source = "rule:pension_overview:law"
    section = AnswerSection(
        kind=SectionKind.SERVICE_EXPLANATION,
        title="연금계좌 세액공제 혜택",
        content="납입 한도와 ISA 만기 특례, 소득구간별 공제율을 확인해 보세요.",
        evidence_ids=[tax_credit_source, receipt_source, law_source],
        blocks=[
            AnswerBlock(
                kind=AnswerBlockKind.CALLOUT,
                title="기본 세액공제 대상 한도",
                text=(
                    "연금저축은 1년에 600만 원까지 세액공제 대상이 됩니다.\n\n"
                    "연금저축·IRP·DC형 근로자 본인 추가납입액은 합산해 연간 "
                    "900만 원까지 세액공제 대상이 됩니다. IRP 또는 DC형 본인 "
                    "추가납입만으로도 합산 한도 900만 원을 채울 수 있습니다.\n\n"
                    "DC형 회사 부담금과 퇴직급여 이전액은 개인의 세액공제 대상 "
                    "납입액에서 제외됩니다."
                ),
            ),
            AnswerBlock(
                kind=AnswerBlockKind.CALLOUT,
                title="ISA 만기자금 이전 특례",
                text=(
                    "ISA 계약기간 만료일부터 60일 이내에 만기자금의 전부 또는 "
                    "일부를 연금저축이나 IRP로 옮겨야 합니다.\n\n"
                    "옮긴 금액의 10%와 300만 원 중 작은 금액만큼 세액공제 대상 "
                    "한도가 추가됩니다."
                ),
            ),
            AnswerBlock(
                kind=AnswerBlockKind.CALLOUT,
                title="소득구간별 세액공제율",
                text=(
                    "총급여액 5,500만 원 이하 또는 종합소득금액 4,500만 원 "
                    "이하: 법정 공제율 15%, 지방소득세 효과 포함 16.5%\n\n"
                    "위 기준 초과: 법정 공제율 12%, 지방소득세 효과 포함 13.2%"
                ),
            ),
            AnswerBlock(
                kind=AnswerBlockKind.CALLOUT,
                title="정리하면",
                text=(
                    "연금저축은 연 600만 원까지, 연금저축·IRP·DC형 근로자 본인 "
                    "추가납입액은 합산해 연 900만 원까지 세액공제 대상이 됩니다. "
                    "ISA 만기자금 이전 특례가 적용되면 최대 1,200만 원까지 "
                    "늘어날 수 있습니다."
                ),
            ),
        ],
    )
    answer = (
        "매년 연금계좌에 납입한 금액의 일정 비율만큼 소득세를 "
        "줄여주는 제도예요."
    )
    evidence_text = "\n".join((answer, section.plain_text()))
    overview = build_pension_account_overview_response()
    source_ids = {tax_credit_source, receipt_source, law_source}
    sources = [
        source for source in overview.sources if source.evidence_id in source_ids
    ]
    numeric_evidence = [
        NumericEvidence(
            label=f"연금계좌 세액공제 규칙 수치 근거 {index}",
            value=value,
            unit=unit,
            evidence_id=tax_credit_source,
            basis="국세청·소득세법 연금계좌 세액공제 규칙",
        )
        for index, (value, unit) in enumerate(
            sorted(extract_numeric_claims(evidence_text)),
            start=1,
        )
    ]
    return ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer=answer,
        data_mode="verified_pension_tax_rule_brief",
        sections=[section],
        sources=sources,
        numeric_evidence=numeric_evidence,
        limitations=overview.limitations,
    )


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
    if _PENSION_TAX_RULE_BRIEF_QUESTION.search(request.message):
        return _pension_tax_rule_brief_response()
    if _requests_account_brief(request, plan):
        return _account_brief_response(
            plan.account_types,
            define_pension=_asks_pension_definition(request.message, plan),
        )
    if plan.account_rule_topic == AccountRuleTopic.PENSION_ACCOUNT_OVERVIEW:
        return build_pension_account_overview_response()
    if plan.account_rule_topic is not None:
        return build_deferred_pension_topic_response(plan.account_rule_topic)
    return account_rule_response(request, plan, knowledge=knowledge)
