"""Deterministic glossary answers backed by the approved pension basics table.

타깃 사용자는 "무엇을 모르는지도 모르는" 입문자다. 용어 정의는 사람마다
달라질 이유가 없으므로 LLM이 만들지 않고, 승인 문서(연금 기초 §7 용어
사전)의 문장을 그대로 인용한다. 새 사실을 만들지 않으므로 환각이 없고
출처 칩도 항상 같은 문서를 가리킨다.
"""

from dataclasses import dataclass, field

from ...retrieval.repository import KnowledgeSearch
from ..models import (
    ChatIntent,
    ChatResponse,
    SuggestedFollowUp,
)
from ._shared import _knowledge_sources

GLOSSARY_DOCUMENT_TITLE = "연금 기초"
GLOSSARY_HEADING = "용어 사전"


@dataclass(frozen=True)
class GlossaryTerm:
    term_id: str
    label: str
    definition: str
    # 함께 알아야 뜻이 완성되는 용어. 입문자는 다음에 뭘 물어야 할지
    # 모르므로 연관 용어를 답변에 같이 붙인다.
    related: tuple[str, ...] = field(default=())


GLOSSARY_TERMS: tuple[GlossaryTerm, ...] = (
    GlossaryTerm(
        term_id="etf",
        label="ETF",
        definition=(
            "지수를 따라가도록 만든 펀드를 주식처럼 사고파는 상품이에요."
        ),
        related=("총보수", "리밸런싱", "실적배당상품"),
    ),
    GlossaryTerm(
        term_id="tdf",
        label="TDF",
        definition=(
            "은퇴 목표 시점에 맞춰 위험자산 비중을 자동으로 줄여가는 "
            "펀드예요."
        ),
        related=("위험자산 한도", "디폴트옵션"),
    ),
    GlossaryTerm(
        term_id="rebalancing",
        label="리밸런싱",
        definition="목표 비중에서 벗어난 자산을 다시 맞추는 것이에요.",
        related=("ETF", "위험자산 한도"),
    ),
    GlossaryTerm(
        term_id="risk_asset_cap",
        label="위험자산 한도",
        definition=(
            "DC형과 IRP에서 주식형 등 위험자산을 담을 수 있는 상한이에요. "
            "연금저축펀드에는 같은 한도가 없어요."
        ),
        related=("안전자산", "TDF", "디폴트옵션"),
    ),
    GlossaryTerm(
        term_id="default_option",
        label="디폴트옵션",
        definition=(
            "운용지시를 하지 않으면 미리 정해둔 방법으로 자동 운용되는 "
            "제도예요. DC형과 IRP가 대상이에요."
        ),
        related=("위험자산 한도", "TDF"),
    ),
    GlossaryTerm(
        term_id="principal_guaranteed",
        label="원리금보장상품",
        definition=(
            "예금·보험처럼 원금과 약정 이자를 보장하는 상품이에요."
        ),
        related=("실적배당상품", "안전자산"),
    ),
    GlossaryTerm(
        term_id="performance_based",
        label="실적배당상품",
        definition=(
            "펀드·ETF처럼 운용 성과에 따라 결과가 달라지는 상품이에요."
        ),
        related=("원리금보장상품", "ETF"),
    ),
    GlossaryTerm(
        term_id="safe_asset",
        label="안전자산",
        definition=(
            "DC형과 IRP에서 위험자산 한도의 반대편에 두는 자산이에요."
        ),
        related=("위험자산 한도", "원리금보장상품"),
    ),
    GlossaryTerm(
        term_id="total_expense_ratio",
        label="총보수",
        definition=(
            "상품을 보유하는 동안 매년 빠져나가는 비용 비율이에요."
        ),
        related=("ETF", "실적배당상품"),
    ),
    GlossaryTerm(
        term_id="tax_credit",
        label="세액공제",
        definition=(
            "연금계좌에 넣은 금액을 연말정산에서 돌려받는 제도예요."
        ),
        related=("과세이연", "연금소득세"),
    ),
    GlossaryTerm(
        term_id="tax_deferral",
        label="과세이연",
        definition=(
            "굴리는 동안 내야 할 세금을 인출 시점까지 미뤄주는 것이에요."
        ),
        related=("세액공제", "연금소득세"),
    ),
    GlossaryTerm(
        term_id="pension_income_tax",
        label="연금소득세",
        definition=(
            "연금으로 받을 때 내는 낮은 세율의 세금이에요. 받는 나이에 "
            "따라 달라져요."
        ),
        related=("과세이연", "세액공제"),
    ),
    GlossaryTerm(
        term_id="in_kind_transfer",
        label="실물이전",
        definition=(
            "가지고 있는 상품을 팔지 않고 금융회사만 옮기는 것이에요."
        ),
        related=("IRP", "연금저축"),
    ),
    GlossaryTerm(
        term_id="irp",
        label="IRP",
        definition=(
            "퇴직금과 추가 납입금을 함께 모으는 개인형퇴직연금 계좌예요."
        ),
        related=("위험자산 한도", "세액공제", "디폴트옵션"),
    ),
    GlossaryTerm(
        term_id="pension_savings",
        label="연금저축",
        definition=(
            "스스로 가입하는 개인연금 계좌예요. 증권사 연금저축펀드에서는 "
            "ETF를 직접 담을 수 있어요."
        ),
        related=("세액공제", "ETF", "IRP"),
    ),
    GlossaryTerm(
        term_id="db_dc",
        label="DB형·DC형",
        definition=(
            "DB형은 회사가 운용해 정해진 급여를 주고, DC형은 회사가 넣어준 "
            "부담금을 내가 운용해요."
        ),
        related=("IRP", "위험자산 한도", "디폴트옵션"),
    ),
    # 아래는 승인 문서 §7-1의 경제·투자 기초 용어. 제도 용어보다 앞서
    # 알아야 하는 배경 지식이라 타깃 사용자가 가장 먼저 막히는 지점이다.
    GlossaryTerm(
        term_id="compound_interest",
        label="복리",
        definition=(
            "이자에 다시 이자가 붙어 시간이 지날수록 불어나는 방식이에요."
        ),
        related=("단리", "과세이연"),
    ),
    GlossaryTerm(
        term_id="simple_interest",
        label="단리",
        definition="처음 원금에만 이자가 붙는 방식이에요.",
        related=("복리",),
    ),
    GlossaryTerm(
        term_id="stock",
        label="주식",
        definition=(
            "회사의 소유권을 잘게 나눈 것으로, 회사 가치에 따라 값이 "
            "오르내려요."
        ),
        related=("채권", "배당", "실적배당상품"),
    ),
    GlossaryTerm(
        term_id="bond",
        label="채권",
        definition="정부나 기업에 돈을 빌려주고 정해진 이자를 받는 것이에요.",
        related=("주식", "금리", "안전자산"),
    ),
    GlossaryTerm(
        term_id="fund",
        label="펀드",
        definition=(
            "여러 사람의 돈을 모아 운용 전문가가 대신 굴리는 상품이에요."
        ),
        related=("ETF", "실적배당상품", "총보수"),
    ),
    GlossaryTerm(
        term_id="diversification",
        label="분산투자",
        definition=(
            "한 곳에 몰지 않고 여러 자산에 나눠 담아 위험을 줄이는 "
            "방법이에요."
        ),
        related=("자산배분", "리밸런싱", "변동성"),
    ),
    GlossaryTerm(
        term_id="asset_allocation",
        label="자산배분",
        definition=(
            "주식·채권처럼 성격이 다른 자산에 비중을 정해 나눠 담는 "
            "것이에요."
        ),
        related=("분산투자", "리밸런싱", "위험자산 한도"),
    ),
    GlossaryTerm(
        term_id="installment_investing",
        label="적립식",
        definition="정해진 주기로 같은 금액을 나눠 넣는 방법이에요.",
        related=("복리", "변동성"),
    ),
    GlossaryTerm(
        term_id="volatility",
        label="변동성",
        definition=(
            "값이 위아래로 얼마나 크게 움직이는지를 나타내는 정도예요."
        ),
        related=("분산투자", "안전자산"),
    ),
    GlossaryTerm(
        term_id="annualized_return",
        label="연평균 수익률",
        definition="여러 해의 성과를 한 해 기준으로 환산해 본 값이에요.",
        related=("복리", "변동성"),
    ),
    GlossaryTerm(
        term_id="interest_rate",
        label="금리",
        definition="돈을 빌리거나 맡길 때 붙는 이자의 비율이에요.",
        related=("채권", "인플레이션"),
    ),
    GlossaryTerm(
        term_id="inflation",
        label="인플레이션",
        definition=(
            "물가가 올라 같은 돈으로 살 수 있는 양이 줄어드는 것이에요."
        ),
        related=("금리", "연평균 수익률"),
    ),
    GlossaryTerm(
        term_id="exchange_rate",
        label="환율",
        definition="우리 돈과 외국 돈을 바꾸는 비율이에요.",
        related=("환헤지",),
    ),
    GlossaryTerm(
        term_id="currency_hedge",
        label="환헤지",
        definition=(
            "환율이 변해도 수익이 흔들리지 않도록 미리 묶어두는 것이에요."
        ),
        related=("환율", "변동성"),
    ),
    GlossaryTerm(
        term_id="dividend",
        label="배당",
        definition="회사가 번 이익의 일부를 주주에게 나눠주는 돈이에요.",
        related=("주식", "실적배당상품"),
    ),
    GlossaryTerm(
        term_id="market_cap",
        label="시가총액",
        definition="회사 주식 전체의 값을 합한 크기예요.",
        related=("주식", "지수"),
    ),
    GlossaryTerm(
        term_id="index",
        label="지수",
        definition=(
            "시장 전체나 특정 묶음의 가격 흐름을 하나의 숫자로 나타낸 "
            "것이에요."
        ),
        related=("ETF", "코스피", "S&P500"),
    ),
    GlossaryTerm(
        term_id="kospi",
        label="코스피",
        definition=(
            "한국거래소 유가증권시장에 상장된 주식 전체의 흐름을 나타내는 "
            "대표 지수예요."
        ),
        related=("지수", "코스닥"),
    ),
    GlossaryTerm(
        term_id="kosdaq",
        label="코스닥",
        definition=(
            "한국거래소 코스닥시장에 상장된 주식의 흐름을 나타내는 "
            "지수예요."
        ),
        related=("지수", "코스피"),
    ),
    GlossaryTerm(
        term_id="sp500",
        label="S&P500",
        definition="미국 대표 기업 500곳의 주가 흐름을 나타내는 지수예요.",
        related=("지수", "나스닥"),
    ),
    GlossaryTerm(
        term_id="nasdaq",
        label="나스닥",
        definition=(
            "미국 나스닥시장에 상장된 주식의 흐름을 나타내는 지수예요. "
            "기술기업 비중이 커요."
        ),
        related=("지수", "S&P500"),
    ),
)

_TERM_BY_ID = {term.term_id: term for term in GLOSSARY_TERMS}
_TERM_BY_LABEL = {term.label: term for term in GLOSSARY_TERMS}

_HANGUL_SYLLABLE_START = 0xAC00
_HANGUL_SYLLABLE_END = 0xD7A3
# 영문 약어는 읽는 소리로 조사를 고른다. ETF는 "에프"로 끝나 받침이 없고,
# IRP는 "피"로 끝나 받침이 없다. 조사 선택에만 쓴다.
_ACRONYM_ENDS_WITH_CONSONANT = {
    "ETF": False,
    "TDF": False,
    "IRP": False,
    # "에스앤피오백"·"나스닥"으로 읽어 각각 받침이 없고 있다.
    "S&P500": False,
    "나스닥": True,
}


def _ends_with_consonant(label: str) -> bool:
    acronym = _ACRONYM_ENDS_WITH_CONSONANT.get(label)
    if acronym is not None:
        return acronym
    last = label[-1]
    code = ord(last)
    if _HANGUL_SYLLABLE_START <= code <= _HANGUL_SYLLABLE_END:
        return (code - _HANGUL_SYLLABLE_START) % 28 != 0
    return False


def _topic_particle(label: str) -> str:
    return "은" if _ends_with_consonant(label) else "는"


def subject_particle(label: str) -> str:
    """Return 이/가 for a term label so follow-up wording reads naturally."""

    return "이" if _ends_with_consonant(label) else "가"


def find_glossary_term(term_id: str) -> GlossaryTerm | None:
    return _TERM_BY_ID.get(term_id)


def _related_follow_ups(term: GlossaryTerm) -> list[SuggestedFollowUp]:
    follow_ups: list[SuggestedFollowUp] = []
    for label in term.related:
        related = _TERM_BY_LABEL.get(label)
        if related is None:
            continue
        particle = "이" if _ends_with_consonant(related.label) else "가"
        follow_ups.append(
            SuggestedFollowUp(
                follow_up_id=f"glossary_{related.term_id}",
                label=f"{related.label} 알아보기",
                message=f"{related.label}{particle} 뭐야?",
            )
        )
    return follow_ups


def build_glossary_response(
    term: GlossaryTerm,
    knowledge: KnowledgeSearch,
) -> ChatResponse:
    """Answer one term and surface the neighbouring terms it depends on."""

    related_labels = [
        label for label in term.related if label in _TERM_BY_LABEL
    ]
    lines = [f"{term.label}{_topic_particle(term.label)} {term.definition}"]
    if related_labels:
        lines.append("")
        lines.append(
            "함께 알아두면 좋은 말이에요: " + ", ".join(related_labels) + "."
        )
    matches = knowledge.search_knowledge(
        f"{GLOSSARY_DOCUMENT_TITLE} {GLOSSARY_HEADING} {term.label}",
        limit=8,
    )
    selected = [
        match for match in matches if match.title.startswith(GLOSSARY_DOCUMENT_TITLE)
    ]
    sources = _knowledge_sources(selected[:1]) if selected else []
    return ChatResponse(
        intent=ChatIntent.GLOSSARY,
        answer="\n".join(lines),
        data_mode="verified_knowledge",
        sources=sources,
        suggested_follow_ups=_related_follow_ups(term),
        limitations=[
            "용어 뜻을 설명한 내용이고, 특정 상품을 권유하지 않아요."
        ],
    )
