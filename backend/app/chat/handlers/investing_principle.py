"""Deterministic "why" answers for basic investing principles.

용어 사전(§7-1)이 "무엇"에 답한다면 이 핸들러는 "왜"에 답한다. 타깃 사용자는
용어 뜻을 알아도 그렇게 하는 이유를 모르는 경우가 많다. 설명은 승인 문서
(연금 기초 §7-2 운용 원리)에 적힌 일반 원리를 인용하며, 미래 수익을 예측하거나
특정 상품을 권유하지 않는다. LLM이 새 사실을 만들지 않으므로 환각이 없다.
"""

from dataclasses import dataclass, field

from ...retrieval.repository import KnowledgeSearch
from ..models import ChatIntent, ChatResponse, SuggestedFollowUp
from ._shared import _knowledge_sources
from .glossary import subject_particle

PRINCIPLE_DOCUMENT_TITLE = "연금 기초"
PRINCIPLE_HEADING = "7-2. 운용 원리"


@dataclass(frozen=True)
class InvestingPrinciple:
    principle_id: str
    label: str
    # 결론을 먼저 말하고 이유를 잇는다. 모두 경향·일반론 표현으로만 쓴다.
    explanation: str
    # 원리마다 반드시 함께 말해야 하는 한계. 낙관적으로만 읽히지 않게 한다.
    caveat: str
    related_terms: tuple[str, ...] = field(default=())


INVESTING_PRINCIPLES: tuple[InvestingPrinciple, ...] = (
    InvestingPrinciple(
        principle_id="long_term_investing",
        label="장기투자",
        explanation=(
            "기간이 길수록 복리가 쌓일 시간이 생기기 때문이에요. 짧은 "
            "기간의 가격 등락이 전체 성과에 미치는 영향도 상대적으로 "
            "줄어드는 경향이 있어요."
        ),
        caveat="기간이 길다고 손실이 없어지는 것은 아니에요.",
        related_terms=("복리", "변동성"),
    ),
    InvestingPrinciple(
        principle_id="why_diversify",
        label="분산투자",
        explanation=(
            "자산마다 오르내리는 시점이 다르기 때문이에요. 여러 자산에 "
            "나눠 담으면 하나가 크게 흔들릴 때 전체가 함께 흔들릴 "
            "가능성을 줄이는 효과가 알려져 있어요."
        ),
        caveat=(
            "분산은 손실을 없애는 장치가 아니라 흔들림의 폭을 줄이려는 "
            "방법이에요."
        ),
        related_terms=("분산투자", "자산배분"),
    ),
    InvestingPrinciple(
        principle_id="concentration_risk",
        label="한 곳에 몰아넣는 위험",
        explanation=(
            "자산이 하나뿐이면 그 자산의 성과가 곧 전체 성과가 되기 "
            "때문이에요. 예상과 다르게 움직였을 때 이를 상쇄할 다른 "
            "자산이 없어요."
        ),
        caveat="특정 자산이 좋다 나쁘다를 판단해 드리는 것은 아니에요.",
        related_terms=("분산투자", "변동성"),
    ),
    InvestingPrinciple(
        principle_id="risk_return_tradeoff",
        label="위험과 수익의 관계",
        explanation=(
            "기대수익과 위험은 함께 움직이는 관계로 설명돼요. 변동성이 "
            "낮은 자산은 기대수익도 낮은 경향이 있어서, 한쪽만 골라 "
            "얻기는 어렵다고 봐요."
        ),
        caveat=(
            "위험을 줄이면 수익이 반드시 줄어든다고 단정할 수는 없고, "
            "일반적인 경향을 설명한 것이에요."
        ),
        related_terms=("변동성", "자산배분"),
    ),
    InvestingPrinciple(
        principle_id="fee_impact",
        label="수수료의 영향",
        explanation=(
            "수수료는 성과와 상관없이 매년 빠져나가기 때문이에요. "
            "연금계좌는 굴리는 기간이 특히 길어서 총보수 차이가 오래 "
            "쌓이면 장기 성과에 영향을 줄 수 있어요."
        ),
        caveat=(
            "수수료가 낮다고 성과가 더 좋다고 말할 수는 없어요. 구체적인 "
            "비용은 상품별 공시를 확인해야 해요."
        ),
        related_terms=("총보수", "복리"),
    ),
    InvestingPrinciple(
        principle_id="compounding_time",
        label="복리와 시간",
        explanation=(
            "복리는 이자에 다시 이자가 붙는 구조라서, 같은 수익률이라도 "
            "굴린 기간이 길수록 누적 효과가 커지기 때문이에요."
        ),
        caveat=(
            "수익률이 계속 같다는 가정에서의 설명이고, 실제 수익률은 "
            "해마다 달라져요."
        ),
        related_terms=("복리", "단리"),
    ),
    InvestingPrinciple(
        principle_id="installment_effect",
        label="적립식 투자",
        explanation=(
            "일정 금액을 나눠 사면 가격이 높을 때 적게, 낮을 때 많이 "
            "사게 되기 때문이에요. 언제 살지 고르는 판단 부담을 줄이려는 "
            "방법으로 설명돼요."
        ),
        caveat="수익을 보장하는 방법은 아니에요.",
        related_terms=("적립식", "변동성"),
    ),
    InvestingPrinciple(
        principle_id="young_risk_weight",
        label="젊을 때 위험자산 비중",
        explanation=(
            "은퇴까지 남은 기간이 길면 시장이 내려가도 회복을 기다릴 "
            "시간이 상대적으로 길다고 보기 때문이에요. 그래서 생애주기 "
            "관점에서 처음에 위험자산 비중을 높게 두고 점차 줄이는 "
            "방식이 널리 쓰여요."
        ),
        caveat=(
            "나이만으로 정해지는 것은 아니고, 투자성향과 계좌 규칙을 "
            "함께 봐야 해요."
        ),
        related_terms=("자산배분", "위험자산 한도", "TDF"),
    ),
    InvestingPrinciple(
        principle_id="age_safe_asset",
        label="나이 들면 안전자산",
        explanation=(
            "받을 시점이 가까울수록 손실을 회복할 시간이 줄어들기 "
            "때문이에요. 그래서 자산가치가 흔들리는 폭을 줄이는 쪽으로 "
            "옮겨가는 것이 일반적인 접근이에요."
        ),
        caveat=(
            "안전자산이 손실이 전혀 없다는 뜻은 아니고, 상품에 따라 "
            "달라요."
        ),
        related_terms=("안전자산", "자산배분"),
    ),
    InvestingPrinciple(
        principle_id="why_rebalance",
        label="리밸런싱의 이유",
        explanation=(
            "시간이 지나면 잘 오른 자산의 비중이 커져서 처음 정한 목표 "
            "비중에서 벗어나기 때문이에요. 그대로 두면 생각했던 것보다 "
            "위험이 커질 수 있어서 주기적으로 되돌려요."
        ),
        caveat="언제 얼마나 되돌릴지는 투자성향과 계좌 상황에 따라 달라요.",
        related_terms=("리밸런싱", "자산배분"),
    ),
    InvestingPrinciple(
        principle_id="why_currency_hedge",
        label="환헤지의 이유",
        explanation=(
            "해외 자산에 투자하면 자산 가격뿐 아니라 환율 변동도 성과에 "
            "반영되기 때문이에요. 환헤지는 이 환율 영향을 줄이려는 "
            "장치예요."
        ),
        caveat=(
            "비용이 들고, 환율이 유리하게 움직일 때 얻었을 이익도 함께 "
            "줄어들어요."
        ),
        related_terms=("환헤지", "환율"),
    ),
)

_PRINCIPLE_BY_ID = {item.principle_id: item for item in INVESTING_PRINCIPLES}


def investing_principle_by_id(principle_id: str) -> InvestingPrinciple | None:
    return _PRINCIPLE_BY_ID.get(principle_id)


def _related_follow_ups(principle: InvestingPrinciple) -> list[SuggestedFollowUp]:
    """Offer the terms this principle leans on so beginners can go deeper."""

    follow_ups: list[SuggestedFollowUp] = []
    for label in principle.related_terms:
        follow_ups.append(
            SuggestedFollowUp(
                follow_up_id=f"principle_term_{len(follow_ups)}",
                label=f"{label} 뜻 보기",
                message=f"{label}{subject_particle(label)} 뭐야?",
            )
        )
    return follow_ups


def build_investing_principle_response(
    principle: InvestingPrinciple,
    knowledge: KnowledgeSearch,
) -> ChatResponse:
    """Answer one principle with its caveat always attached."""

    lines = [principle.explanation, "", f"다만 {principle.caveat}"]
    matches = knowledge.search_knowledge(
        f"{PRINCIPLE_DOCUMENT_TITLE} {PRINCIPLE_HEADING} {principle.label}",
        limit=8,
    )
    selected = [
        match
        for match in matches
        if match.title.startswith(PRINCIPLE_DOCUMENT_TITLE)
    ]
    sources = _knowledge_sources(selected[:1]) if selected else []
    return ChatResponse(
        intent=ChatIntent.INVESTING_PRINCIPLE,
        answer="\n".join(lines),
        data_mode="verified_knowledge",
        sources=sources,
        suggested_follow_ups=_related_follow_ups(principle),
        limitations=[
            "일반적으로 알려진 운용 원리를 설명한 내용이에요. 특정 상품을 "
            "권유하거나 미래 수익을 예측하지 않아요.",
            "과거의 경향이 미래 결과를 보장하지 않아요.",
        ],
    )
