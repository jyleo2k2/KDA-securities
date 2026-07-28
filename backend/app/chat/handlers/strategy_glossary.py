"""Deterministic answers for the ten investing strategies shown in the app.

전략 탐색 화면(`frontend/src/pages/strategyExplore/strategies.ts`)에는 전략
10종의 설명이 이미 있는데 챗봇은 그 어휘를 몰라서 "탑다운 전략이 뭐야?"에
엉뚱한 용어 정의를 답했다. 여기서는 화면과 같은 승인 문구를 해요체로만
옮겨 인용한다. LLM이 새 사실을 만들지 않으므로 환각이 없고, 근거 문서에
없는 자산배분 비율·수익률 같은 수치는 넣지 않는다.

근거: docs/team/주식 전략을 활용한 연금 포트폴리오 운용안.md
"""

from dataclasses import dataclass, field

from ..models import ChatIntent, ChatResponse, SuggestedFollowUp
from .glossary import subject_particle

STRATEGY_GLOSSARY_DATA_MODE = "verified_strategy_guide"


@dataclass(frozen=True)
class InvestingStrategy:
    strategy_id: str
    label: str
    # 화면의 desc. 무엇을 하는 전략인지 한 문장으로 먼저 말한다.
    summary: str
    # 코어·위성 중 어디에 두는 전략인지. 비중 감각을 같이 줘야 오해가 없다.
    bucket: str
    # 연금계좌에서 어떻게 쓰는지. 계좌 규칙·한도를 항상 함께 말한다.
    account_application: str
    # 작동 방식과 한계. 한계를 빼면 낙관적으로만 읽힌다.
    how_it_works: str
    # 이 전략을 이해하는 데 먼저 필요한 용어 사전 항목.
    related_terms: tuple[str, ...] = field(default=())


INVESTING_STRATEGIES: tuple[InvestingStrategy, ...] = (
    InvestingStrategy(
        strategy_id="market-beta",
        label="시장 베타 전략",
        summary=(
            "시장 수익률을 포트폴리오의 기준 수익원으로 삼는 장기 분산 "
            "전략이에요."
        ),
        bucket="코어(장기 보유)",
        account_application=(
            "국내외 광범위 지수 ETF를 중심으로 분산해요. 계좌별 위험자산 "
            "한도와 전체 주식 비중을 함께 점검해요."
        ),
        how_it_works=(
            "개별 종목의 성패보다 시장 전체의 성장에 투자해요. 단기 전망에 "
            "따라 자주 바꾸기보다, 정한 자산배분을 주기적으로 점검하는 "
            "방식이에요."
        ),
        related_terms=("ETF", "지수", "자산배분"),
    ),
    InvestingStrategy(
        strategy_id="factor",
        label="팩터 전략",
        summary=(
            "재무 건전성·가격 수준·추세처럼 장기 성과와 관련된 기업 특성을 "
            "기준으로 ETF를 고르는 규칙 기반 전략이에요."
        ),
        bucket="코어 보완",
        account_application=(
            "퀄리티·가치·모멘텀·최소변동성 ETF를 성격이 다른 보조 슬리브로 "
            "나눠 담아요. 한 팩터에만 집중하지 않는 것이 중요해요."
        ),
        how_it_works=(
            "정해 둔 기업 특성을 가진 종목을 담은 ETF를 활용해요. 팩터별 "
            "성과 차이가 오래 이어질 수 있어서, 최근 성과만 보고 비중을 "
            "크게 바꾸지 않아요."
        ),
        related_terms=("ETF", "분산투자", "총보수"),
    ),
    InvestingStrategy(
        strategy_id="theme",
        label="테마 전략",
        summary=(
            "산업 구조 변화가 예상되는 분야에 집중해 성장 기회를 찾는 위성 "
            "전략이에요."
        ),
        bucket="위성(보조 비중)",
        account_application=(
            "AI·반도체·바이오·인프라 같은 테마 ETF는 코어 포트폴리오와 "
            "분리해 제한된 비중으로 담아요."
        ),
        how_it_works=(
            "성장 논리, 밸류에이션, 담긴 종목의 집중도를 함께 확인해요. "
            "기대가 이미 가격에 반영됐을 수 있어서 한 테마에 연금자산을 "
            "집중하지 않아요."
        ),
        related_terms=("ETF", "분산투자", "변동성"),
    ),
    InvestingStrategy(
        strategy_id="topdown",
        label="탑다운 전략",
        summary=(
            "금리·물가·경기 같은 거시 환경을 먼저 살펴본 뒤 국가·산업·자산군 "
            "비중을 조정하는 전략이에요."
        ),
        bucket="위성(보조 비중)",
        account_application=(
            "국가·산업 ETF와 채권 ETF의 비중을 조정할 때 활용할 수 있어요. "
            "계좌 규칙과 위험자산 한도 안에서만 비중을 바꿔요."
        ),
        how_it_works=(
            "경제지표가 자산 가격에 미칠 가능성을 점검하고, 그 결과를 "
            "자산배분에 제한적으로 반영해요. 하나의 거시 전망이 틀릴 수 "
            "있어서 포트폴리오 전체를 한 방향에 걸지 않아요."
        ),
        related_terms=("금리", "인플레이션", "자산배분"),
    ),
    InvestingStrategy(
        strategy_id="bottomup",
        label="바텀업 전략",
        summary=(
            "경제 전망보다 개별 기업의 경쟁력·재무상태·성장성을 먼저 분석해 "
            "투자 대상을 고르는 전략이에요."
        ),
        bucket="위성(보조 비중)",
        account_application=(
            "운용 철학과 담긴 종목이 뚜렷한 액티브 주식형 펀드나 ETF를 "
            "제한된 비중으로 검토해요."
        ),
        how_it_works=(
            "매출 성장, 이익률, 재무구조, 경쟁우위를 중심으로 기업을 "
            "평가해요. 개별 기업 판단이 틀릴 수 있어서 분산된 펀드·ETF와 "
            "작은 비중을 먼저 봐요."
        ),
        related_terms=("주식", "펀드", "분산투자"),
    ),
    InvestingStrategy(
        strategy_id="barbell",
        label="바벨 전략",
        summary=(
            "성장자산과 현금·단기채를 함께 보유해 성장 기회와 위험 완충 "
            "역할을 나누는 전략이에요."
        ),
        bucket="코어·안정화 조합",
        account_application=(
            "주식 같은 성장자산과 단기채·현금성 자산을 함께 보유해요. "
            "계좌별 위험자산 한도 안에서 성장자산 비중을 정해요."
        ),
        how_it_works=(
            "포트폴리오의 한쪽에는 장기 성장자산을, 다른 한쪽에는 단기채·"
            "현금성 자산을 둬요. 두 역할을 분명히 나누고 목표 비중에서 "
            "벗어나면 주기적으로 리밸런싱해요."
        ),
        related_terms=("채권", "자산배분", "리밸런싱"),
    ),
    InvestingStrategy(
        strategy_id="volatility",
        label="변동성 관리 전략",
        summary=(
            "포트폴리오의 가격 변동 폭을 관리하려고 주식·채권·현금 비중을 "
            "조절하는 위험관리 전략이에요."
        ),
        bucket="위험관리",
        account_application=(
            "저변동 ETF와 채권·현금성 자산을 조합해 목표 변동성에 맞는 "
            "비중을 관리해요. 계좌별 위험자산 한도는 별도로 지켜야 해요."
        ),
        how_it_works=(
            "시장 변동성이 커지면 위험자산 비중을 낮추고 안정화 자산 비중을 "
            "높이는 방식을 써요. 손실을 없애는 전략은 아니고, 상승장에서 "
            "시장 수익률을 일부 놓칠 수 있어요."
        ),
        related_terms=("변동성", "안전자산", "자산배분"),
    ),
    InvestingStrategy(
        strategy_id="longshort",
        label="롱숏·시장중립 전략",
        summary=(
            "오를 것으로 보는 자산과 하락 위험을 줄이는 포지션을 함께 써서 "
            "시장 방향에 대한 노출을 낮추려는 전략이에요."
        ),
        bucket="위성(보조 비중)",
        account_application=(
            "연금계좌에서 담을 수 있는 시장중립·절대수익형 펀드가 있을 "
            "때만 검토해요. 상품의 투자 방식·비용·유동성을 먼저 확인해요."
        ),
        how_it_works=(
            "매수 포지션과 헤지 포지션을 함께 운용해 시장 베타를 낮추는 것을 "
            "목표로 해요. 복잡한 파생상품이나 공매도 구조를 쓸 수 있어서 "
            "상품 설명서와 위험을 충분히 확인해야 해요."
        ),
        related_terms=("펀드", "변동성", "총보수"),
    ),
    InvestingStrategy(
        strategy_id="eventdriven",
        label="이벤트드리븐 전략",
        summary=(
            "합병·분할·자사주 매입 같은 기업 이벤트가 가격에 반영되는 "
            "과정에서 기회를 찾는 전략이에요."
        ),
        bucket="위성(보조 비중)",
        account_application=(
            "연금계좌에서 담을 수 있는 관련 펀드가 있을 때만 검토해요. "
            "단일 이벤트에 직접 투자하기보다 분산된 상품의 운용 방식과 "
            "위험을 확인해요."
        ),
        how_it_works=(
            "공시된 기업 이벤트의 성사 가능성, 일정, 가격 차이를 분석해요. "
            "거래 무산·일정 변경·규제 변수로 손실이 생길 수 있어서 코어 "
            "자산을 대체하는 방식으로 쓰지 않아요."
        ),
        related_terms=("주식", "펀드", "분산투자"),
    ),
    InvestingStrategy(
        strategy_id="trend",
        label="추세추종·글로벌 매크로 전략",
        summary=(
            "여러 자산의 가격 추세와 글로벌 경제 환경을 규칙에 따라 활용하는 "
            "멀티에셋 전략이에요."
        ),
        bucket="위성(보조 비중)",
        account_application=(
            "연금계좌에서 담을 수 있는 멀티에셋이나 글로벌 매크로 펀드가 "
            "있을 때만 제한된 비중으로 검토해요."
        ),
        how_it_works=(
            "주식·채권·원자재·통화 같은 여러 자산의 추세와 거시 환경을 함께 "
            "점검해요. 추세가 자주 바뀌는 구간에서는 손실과 매매 비용이 커질 "
            "수 있어서 규칙과 비용을 확인해야 해요."
        ),
        related_terms=("자산배분", "변동성", "총보수"),
    ),
)

_STRATEGY_BY_ID = {item.strategy_id: item for item in INVESTING_STRATEGIES}


def find_investing_strategy(strategy_id: str) -> InvestingStrategy | None:
    return _STRATEGY_BY_ID.get(strategy_id)


def _follow_ups(strategy: InvestingStrategy) -> list[SuggestedFollowUp]:
    """전략을 이해하는 데 필요한 용어와 전략 목록을 함께 제안해요."""

    follow_ups = [
        SuggestedFollowUp(
            follow_up_id=f"strategy_term_{index}",
            label=f"{label} 뜻 보기",
            message=f"{label}{subject_particle(label)} 뭐야?",
        )
        for index, label in enumerate(strategy.related_terms)
    ]
    follow_ups.append(
        SuggestedFollowUp(
            follow_up_id="open_strategy_explore",
            label="전략 전체 살펴보기",
            message="투자 전략에는 어떤 것들이 있어?",
        )
    )
    return follow_ups


def build_strategy_glossary_response(
    strategy: InvestingStrategy,
) -> ChatResponse:
    """전략 하나를 설명하고 계좌에 적용하는 방법을 함께 붙여요."""

    lines = [
        f"{strategy.label}은 {strategy.summary}",
        "",
        f"포트폴리오에서는 {strategy.bucket} 역할로 봐요. "
        f"{strategy.account_application}",
        "",
        strategy.how_it_works,
    ]
    return ChatResponse(
        intent=ChatIntent.STRATEGY_GLOSSARY,
        answer="\n".join(lines),
        data_mode=STRATEGY_GLOSSARY_DATA_MODE,
        suggested_follow_ups=_follow_ups(strategy),
        limitations=[
            "전략의 개념을 설명한 내용이고, 특정 상품을 권유하지 않아요.",
            "실제 비중은 투자성향과 계좌 규칙에 따라 달라져요.",
        ],
    )
