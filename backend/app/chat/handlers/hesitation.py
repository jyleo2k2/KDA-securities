"""Deterministic answers for hesitation and comparison questions.

타깃 사용자는 제도를 몰라서만 멈추지 않는다. "손실 나면 어떡하지?", "지금
시작해도 늦지 않았나?", "남들은 얼마나 모았어?"처럼 망설임이 담긴 질문에서도
멈춘다. 이 핸들러는 그 질문에 답하되 다음 두 가지를 지킨다.

1. 감정을 단정하지 않는다. "불안하시죠"처럼 확정하는 대신, 질문이 흔하고
   짚어볼 만하다는 사실로 연다. 정보만 물어본 사용자에게도 어색하지 않다.
2. 위로로 끝내지 않는다. 문을 연 다음에는 곧바로 승인 문서의 사실로 넘어가고,
   판단이 필요한 부분은 계산기와 성향별 비교로 넘긴다.

"괜찮아질 거예요"처럼 미래를 안심시키는 표현은 쓰지 않는다.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from ...retrieval.repository import KnowledgeSearch
from ..models import (
    ChatIntent,
    ChatResponse,
    NumericEvidence,
    SuggestedFollowUp,
)
from ._shared import _knowledge_sources

BASICS_DOCUMENT_TITLE = "연금 기초"
PERFORMANCE_DOCUMENT_TITLE = "퇴직연금 2025년 운용현황"

# 질문을 정상화(A)하면서 동시에 질문의 타당성을 인정(B)하는 문장. 감정을
# 단정하지 않으므로 정보만 물어본 사용자에게도 자연스럽다.
OPENERS: dict[str, str] = {
    "common": "많이들 물어보시는 부분이에요.",
    "worth_asking": "짚어볼 만한 질문이에요.",
    "common_and_worth": "많이들 물어보시고, 짚어볼 만한 질문이에요.",
}


@dataclass(frozen=True)
class HesitationAnswer:
    answer_id: str
    # 질문을 정상화하고 타당성을 인정하는 첫 문장.
    opener_key: str
    # 사실로 넘어가는 본문. 수치를 쓰면 반드시 근거 문서가 붙는다.
    body: str
    # 낙관적으로만 읽히지 않게 하는 한계 문장.
    caveat: str
    # 판단이 필요한 부분을 넘길 다음 단계.
    follow_ups: tuple[tuple[str, str, str], ...] = field(default=())
    # 근거로 삼을 승인 문서 제목.
    evidence_titles: tuple[str, ...] = field(default=(BASICS_DOCUMENT_TITLE,))
    # 본문에 수치를 쓰는 경우 그 수치의 근거. (라벨, 값, 단위, 기준) 형태다.
    numeric_claims: tuple[tuple[str, str, str, str], ...] = field(default=())


HESITATION_ANSWERS: tuple[HesitationAnswer, ...] = (
    HesitationAnswer(
        answer_id="loss_fear",
        opener_key="common",
        body=(
            "연금계좌에서 고를 수 있는 상품은 크게 두 갈래예요. 원리금보장 "
            "상품은 약정된 이자를 주는 대신 수익이 제한되고, 실적배당 "
            "상품은 운용 성과에 따라 오르내려요. 손실 가능성은 이 실적배당 "
            "상품에서 나오고, 얼마나 흔들리는지는 담는 자산의 종류와 "
            "비중에 따라 달라져요."
        ),
        caveat=(
            "어떤 조합이든 손실이 나지 않는다고 말씀드릴 수는 없어요. "
            "줄이려는 방법이 있을 뿐이에요."
        ),
        follow_ups=(
            (
                "hesitation_principal_guaranteed",
                "원리금보장상품이란",
                "원리금보장상품이 뭐야?",
            ),
            (
                "hesitation_why_diversify",
                "왜 나눠 담는지 보기",
                "분산투자를 왜 해야 해?",
            ),
            (
                "hesitation_deposit_protection",
                "예금자보호 범위 보기",
                "연금계좌도 예금자보호가 되나요?",
            ),
        ),
    ),
    HesitationAnswer(
        answer_id="market_drop_fear",
        opener_key="worth_asking",
        body=(
            "가격이 오르내리는 구간은 투자에서 되풀이돼 온 일이에요. 지금이 "
            "높은지 낮은지는 지나고 나서야 알 수 있어서, 연금처럼 기간이 긴 "
            "자금은 한 시점의 가격보다 자산을 어떻게 나눠 담았는지를 더 "
            "중요하게 봐요. 시점을 맞히기 어려울 때 여러 번에 나눠 넣는 "
            "적립식을 쓰는 것도 이런 이유예요."
        ),
        caveat=(
            "지금 사야 할지 기다려야 할지는 말씀드릴 수 없고, 시장이 앞으로 "
            "어떻게 움직일지도 예측하지 않아요. 분산과 적립식은 흔들림의 폭을 "
            "줄이려는 방법이지 손실을 없애는 장치가 아니에요."
        ),
        follow_ups=(
            ("hesitation_volatility", "변동성이란", "변동성이 뭐야?"),
            (
                "hesitation_long_term",
                "장기투자를 왜 하는지 보기",
                "장기투자를 왜 해야 해?",
            ),
            (
                "hesitation_installment_timing",
                "나눠 사는 이유 보기",
                "적립식으로 왜 나눠 사?",
            ),
        ),
    ),
    HesitationAnswer(
        answer_id="too_late_to_start",
        opener_key="common_and_worth",
        body=(
            "늦었는지는 나이 자체보다 남은 기간과 넣을 수 있는 금액으로 "
            "따져보는 편이에요. 연금계좌는 세액공제를 받으며 쌓고, 55세 "
            "이후 연금으로 받을 때 낮은 세율이 적용되는 구조라서 기간이 "
            "짧아도 쓸 수 있는 제도예요. 계산기에 나이와 금액을 넣으면 "
            "남은 기간으로 어떤 그림이 되는지 직접 확인할 수 있어요."
        ),
        caveat=(
            "기간이 짧으면 쌓이는 기간도 짧아요. 계산 결과는 입력한 "
            "가정에 따른 값이고 실제 수익을 약속하지 않아요."
        ),
        follow_ups=(
            (
                "hesitation_planner",
                "계산기로 확인하기",
                "연금 계산기로 예상 수령액을 계산해줘",
            ),
            (
                "hesitation_tax_credit",
                "세액공제 한도 보기",
                "연금계좌 세액공제 납입 한도를 알려줘",
            ),
            ("hesitation_compounding", "복리가 왜 좋은지 보기", "복리가 왜 좋아?"),
        ),
    ),
    HesitationAnswer(
        answer_id="small_amount_start",
        opener_key="common",
        body=(
            "연금계좌에는 매달 정해진 금액을 꼭 넣어야 하는 의무가 없어요. "
            "연금저축펀드는 자유납입이라 형편에 맞춰 넣는 금액과 시기를 "
            "조절할 수 있고, 사정이 생기면 납입을 쉬었다가 다시 넣을 수도 "
            "있어요. 세액공제 한도는 넣을 수 있는 상한이지 채워야 하는 "
            "목표가 아니에요."
        ),
        caveat=(
            "적정 금액은 소득과 지출에 따라 달라서 얼마가 좋다고 "
            "정해드리지는 않아요. 상품 유형에 따라 납입 조건이 다를 수 "
            "있어요."
        ),
        follow_ups=(
            (
                "hesitation_pause",
                "납입을 쉬어도 되는지 보기",
                "연금저축 납입을 한 달 쉬어도 되나요?",
            ),
            (
                "hesitation_limit",
                "세액공제 한도 보기",
                "연금계좌 세액공제 납입 한도를 알려줘",
            ),
            (
                "hesitation_installment",
                "나눠 사는 이유 보기",
                "적립식으로 왜 나눠 사?",
            ),
        ),
    ),
    HesitationAnswer(
        answer_id="peer_comparison",
        opener_key="worth_asking",
        body=(
            "개인별 적립금은 알려드릴 수 없지만, 시장 전체 통계는 공식 "
            "자료로 볼 수 있어요. 2025년 말 퇴직연금 적립금은 501.4조 "
            "원이었고 그해 전체 수익률은 6.5%였어요. 같은 해 수익률 상위 "
            "10% 가입자는 평균 19.5%였고 실적배당형 비중이 84%, 하위 10%는 "
            "평균 0.5%였고 원리금보장형 비중이 74%였어요. 남들과 견주기보다 "
            "이 차이가 어디서 왔는지를 보는 편이 도움이 돼요."
        ),
        caveat=(
            "2025년 한 해의 집단 통계예요. 시장 상황이 달라지면 결과도 "
            "달라지고, 시장 평균을 개인 수익률로 대신 볼 수는 없어요."
        ),
        follow_ups=(
            (
                "hesitation_performance_detail",
                "2025년 운용현황 자세히 보기",
                "2025년 퇴직연금 운용현황을 알려줘",
            ),
            (
                "hesitation_profile_compare",
                "성향별로 비교하기",
                "투자성향별 연금 운용 가이드를 비교해줘",
            ),
            (
                "hesitation_default_option",
                "디폴트옵션이란",
                "디폴트옵션이 뭐야?",
            ),
        ),
        evidence_titles=(PERFORMANCE_DOCUMENT_TITLE,),
        numeric_claims=(
            (
                "2025년 말 퇴직연금 적립금",
                "501.4",
                "조원",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
            (
                "2025년 전체 퇴직연금 수익률",
                "6.5",
                "%",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
            (
                "2025년 수익률 상위 10% 가입자 평균 수익률",
                "19.5",
                "%",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
            (
                "2025년 수익률 상위 10% 가입자 실적배당형 비중",
                "84",
                "%",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
            (
                "2025년 수익률 하위 10% 가입자 평균 수익률",
                "0.5",
                "%",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
            (
                "2025년 수익률 하위 10% 가입자 원리금보장형 비중",
                "74",
                "%",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
            (
                "비교 기준 가입자 구간",
                "10",
                "%",
                "고용노동부 2025년 퇴직연금 투자백서",
            ),
        ),
    ),
    HesitationAnswer(
        answer_id="doing_well_check",
        opener_key="common_and_worth",
        body=(
            "잘하고 있는지는 수익률 하나로만 보기 어려워요. 연금은 기간이 "
            "긴 자금이라 담은 자산이 투자성향과 맞는지, 계좌 규칙 안에서 "
            "한쪽으로 쏠리지 않았는지를 함께 봐요. 보유한 계좌를 "
            "불러오시면 자산이 어떻게 나뉘어 있는지 진단해 드릴 수 있어요."
        ),
        caveat=(
            "진단은 현재 구성이 성향과 규칙에 맞는지를 보는 것이지, "
            "성과가 좋다 나쁘다를 평가하거나 미래를 예측하지 않아요."
        ),
        follow_ups=(
            (
                "hesitation_diagnose",
                "내 계좌 진단하기",
                "내 계좌 포트폴리오를 진단해줘",
            ),
            (
                "hesitation_profile_guide_check",
                "성향별로 비교하기",
                "투자성향별 연금 운용 가이드를 비교해줘",
            ),
            (
                "hesitation_rebalance",
                "리밸런싱을 왜 하는지 보기",
                "리밸런싱을 왜 해야 해?",
            ),
        ),
    ),
)

_ANSWER_BY_ID = {item.answer_id: item for item in HESITATION_ANSWERS}


def hesitation_answer_by_id(answer_id: str) -> HesitationAnswer | None:
    return _ANSWER_BY_ID.get(answer_id)


def build_hesitation_response(
    answer: HesitationAnswer,
    knowledge: KnowledgeSearch,
) -> ChatResponse:
    """Open by normalising the question, then move straight to approved facts."""

    opener = OPENERS[answer.opener_key]
    lines = [f"{opener} {answer.body}", "", f"다만 {answer.caveat}"]
    sources = []
    for title in answer.evidence_titles:
        matches = knowledge.search_knowledge(title, limit=8)
        selected = [match for match in matches if match.title.startswith(title)]
        if selected:
            sources.extend(_knowledge_sources(selected[:1]))
    numeric_evidence = [
        NumericEvidence(
            label=label,
            value=Decimal(value),
            unit=unit,
            evidence_id=sources[0].evidence_id if sources else "",
            basis=basis,
        )
        for label, value, unit, basis in answer.numeric_claims
    ]
    return ChatResponse(
        intent=ChatIntent.HESITATION_SUPPORT,
        answer="\n".join(lines),
        data_mode="verified_knowledge",
        sources=sources,
        numeric_evidence=numeric_evidence,
        suggested_follow_ups=[
            SuggestedFollowUp(follow_up_id=item[0], label=item[1], message=item[2])
            for item in answer.follow_ups
        ],
        limitations=[
            "미래 수익이나 시장 방향을 예측하지 않고, 특정 상품을 권유하지 "
            "않아요.",
            "과거의 경향과 통계가 미래 결과를 보장하지 않아요.",
        ],
    )
