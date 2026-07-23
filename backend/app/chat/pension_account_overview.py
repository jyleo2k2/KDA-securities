from datetime import date

from .models import (
    AnswerBlock,
    AnswerBlockKind,
    AnswerSection,
    ChatIntent,
    ChatResponse,
    DataBoundary,
    SectionKind,
    SourceEvidence,
)
from .query_planner import AccountRuleTopic

_AS_OF = date(2026, 7, 20)
_TAX_CREDIT_SOURCE = "rule:pension_overview:tax_credit"
_RECEIPT_SOURCE = "rule:pension_overview:receipt"
_TAXATION_SOURCE = "rule:pension_overview:taxation"
_RETIREMENT_SOURCE = "rule:pension_overview:retirement"
_RISK_ASSET_SOURCE = "rule:pension_overview:risk_asset"
_WITHDRAWAL_SOURCE = "rule:pension_overview:withdrawal"
_LAW_SOURCE = "rule:pension_overview:law"
PENSION_TOPIC_DEFER_NOTICE = (
    "위 내용은 일반적인 제도 안내이며, 가입 시점·납입 재원·수령 방식·"
    "개인별 소득과 증빙에 따라 실제 적용 결과가 달라질 수 있습니다. "
    "자세한 내용은 세무전문가의 도움을 받아 확인하시기 바랍니다."
)
_FINANCIAL_INSTITUTION_NOTICE = (
    "실제 신청 가능 여부는 계좌를 관리하는 금융회사에도 확인하시기 바랍니다."
)


def _section(
    title: str,
    blocks: list[AnswerBlock],
    evidence_ids: list[str],
) -> AnswerSection:
    return AnswerSection(
        kind=SectionKind.FACT,
        title=title,
        content="\n".join(block.plain_text() for block in blocks),
        evidence_ids=evidence_ids,
        blocks=blocks,
    )


def build_pension_account_overview_response() -> ChatResponse:
    """Return the source-linked, deterministic pension-account overview."""

    sections = [
        _section(
            "핵심 숫자부터",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.CALLOUT,
                    title="2026년 7월 기준",
                    text=(
                        "연간 본인 납입한도 1,800만 원 · 기본 세액공제 대상 "
                        "한도 900만 원 · 연금저축 소한도 600만 원"
                    ),
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.PARAGRAPH,
                    text=(
                        "1,800만 원은 납입할 수 있는 한도이고, 900만 원은 "
                        "세액공제를 적용할 수 있는 기본 한도입니다. 두 한도를 "
                        "같은 의미로 보면 안 됩니다."
                    ),
                ),
            ],
            [_TAX_CREDIT_SOURCE],
        ),
        _section(
            "연금저축·IRP·DC형의 차이",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    headers=["구분", "연금저축", "IRP", "DC형"],
                    rows=[
                        [
                            "주된 역할",
                            "개인 노후자금 적립",
                            "개인 추가 적립·퇴직급여 관리",
                            "회사가 납입한 퇴직급여를 근로자가 운용",
                        ],
                        [
                            "세액공제",
                            "본인 납입액 중 연 600만 원까지",
                            "다른 연금계좌 본인 납입액과 합산해 연 900만 원까지",
                            "본인 추가납입액만 합산 한도에 포함",
                        ],
                        [
                            "위험자산",
                            "DC·IRP와 같은 총량 70% 한도 없음",
                            "원칙적으로 적립금의 70%까지",
                            "원칙적으로 적립금의 70%까지",
                        ],
                        [
                            "퇴직급여",
                            "해당 없음",
                            "이전된 퇴직급여는 개인 세액공제 대상 아님",
                            "회사 부담금은 개인 세액공제 대상 아님",
                        ],
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.PARAGRAPH,
                    text=(
                        "연금저축·IRP·DC형 본인 추가납입액은 금융회사가 달라도 "
                        "합산합니다. IRP·DC형의 70% 원칙에는 적격 TDF나 승인된 "
                        "디폴트옵션 등 법정 예외가 있을 수 있고, 연금저축펀드는 "
                        "총량 한도 대신 상품별 편입 적격성을 따로 확인합니다."
                    ),
                ),
            ],
            [
                _TAX_CREDIT_SOURCE,
                _RETIREMENT_SOURCE,
                _RISK_ASSET_SOURCE,
                _LAW_SOURCE,
            ],
        ),
        _section(
            "세액공제 규칙",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        "연금저축만으로는 최대 600만 원까지 세액공제 대상입니다.",
                        (
                            "연금저축과 IRP·DC형 본인 추가납입액을 합치면 "
                            "기본 한도는 900만 원입니다."
                        ),
                        (
                            "IRP 또는 DC형 본인 추가납입만으로 900만 원을 "
                            "채우는 것도 가능합니다."
                        ),
                        (
                            "900만 원 초과분은 당해 기본 세액공제 대상이 "
                            "아니지만 계좌 안에서 과세이연 효과를 받을 수 있습니다."
                        ),
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    headers=[
                        "소득 기준",
                        "법정 공제율",
                        "지방소득세 효과 포함",
                        "900만 원 적용 시 최대 효과",
                    ],
                    rows=[
                        [
                            "총급여 5,500만 원 이하 또는 종합소득금액 4,500만 원 이하",
                            "15%",
                            "16.5%",
                            "148만 5천 원",
                        ],
                        [
                            "위 기준 초과",
                            "12%",
                            "13.2%",
                            "118만 8천 원",
                        ],
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.PARAGRAPH,
                    text=(
                        "연금저축 600만 원과 IRP 또는 DC형 본인 추가납입 "
                        "300만 원은 한도를 설명하는 예시일 뿐 추천안이 아닙니다. "
                        "실제 공제액은 결정세액 등에 따라 계산상 최대액보다 "
                        "작을 수 있습니다."
                    ),
                ),
            ],
            [_TAX_CREDIT_SOURCE, _LAW_SOURCE],
        ),
        _section(
            "1,800만 원을 모두 넣으면 900만 원 초과분은 어떻게 되나",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        "기본 세액공제는 900만 원까지만 적용됩니다.",
                        (
                            "나머지 900만 원은 세액공제를 받지 않은 원금으로 "
                            "관리할 수 있습니다."
                        ),
                        "미공제 원금은 금융회사가 재원별로 구분해 관리해야 합니다.",
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.PARAGRAPH,
                    text=(
                        "금융회사가 미공제 원금을 정확히 기록하고 있는지 확인해야 "
                        "합니다. 필요하면 홈택스의 연금보험료 등 소득·세액공제 "
                        "확인 자료를 금융회사에 제출해야 할 수 있습니다."
                    ),
                ),
            ],
            [_TAX_CREDIT_SOURCE, _LAW_SOURCE],
        ),
        _section(
            "ISA 만기자금 이전 특례",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        (
                            "ISA 만기일부터 60일 이내에 만기자금의 전부 또는 "
                            "일부를 연금계좌로 옮겨야 합니다."
                        ),
                        (
                            "전환금액은 일반 연간 납입한도 1,800만 원에 더해 "
                            "납입할 수 있습니다."
                        ),
                        (
                            "전환금액의 10%를 세액공제 대상 한도에 추가하며 "
                            "추가 한도는 최대 300만 원입니다."
                        ),
                        (
                            "기본 한도와 합치면 세액공제 대상 납입액은 최대 "
                            "1,200만 원이 될 수 있습니다."
                        ),
                        (
                            "300만 원은 환급액이 아니라 세액공제율을 적용할 "
                            "추가 납입액 한도입니다."
                        ),
                    ],
                )
            ],
            [_TAX_CREDIT_SOURCE, _RECEIPT_SOURCE, _LAW_SOURCE],
        ),
        _section(
            "실제 관리할 때 중요한 원칙",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        "세액공제만을 위해 비상자금까지 연금계좌에 넣지 않습니다.",
                        ("장기간 사용하지 않아도 되는 자금과 비상자금을 구분합니다."),
                        (
                            "여러 금융회사의 연금저축·IRP·DC형 본인 추가납입액을 "
                            "합산해 900만 원과 1,800만 원 한도를 관리합니다."
                        ),
                        "계좌별 납입내역에서 미공제 원금이 구분됐는지 확인합니다.",
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.PARAGRAPH,
                    text=(
                        "총급여 또는 종합소득금액과 올해 계좌별 본인 납입액을 "
            "알려주면 규칙 엔진으로 세액공제 대상액과 예상 "
            "공제 효과를 계산해 설명할 수 있습니다."
                    ),
                ),
            ],
            [_TAX_CREDIT_SOURCE, _LAW_SOURCE],
        ),
    ]

    return ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer=(
            "국민연금이 아닌 연금저축·IRP·DC형 퇴직연금의 핵심 규칙을 "
            "2026년 7월 기준으로 정리했습니다."
        ),
        data_mode="verified_pension_account_overview",
        sections=sections,
        sources=[
            SourceEvidence(
                evidence_id=_TAX_CREDIT_SOURCE,
                label="연금계좌 세액공제",
                locator=(
                    "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7875"
                ),
                publisher="국세청",
                as_of=_AS_OF,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            ),
            SourceEvidence(
                evidence_id=_RECEIPT_SOURCE,
                label="ISA 만기자금의 연금계좌 전환",
                locator=(
                    "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?"
                    "cntntsId=7885&mi=6605"
                ),
                publisher="국세청",
                as_of=_AS_OF,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            ),
            SourceEvidence(
                evidence_id=_RETIREMENT_SOURCE,
                label="퇴직연금제도 안내",
                locator="https://www.moel.go.kr/retirementpay.do",
                publisher="고용노동부",
                as_of=_AS_OF,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            ),
            SourceEvidence(
                evidence_id=_RISK_ASSET_SOURCE,
                label="디폴트옵션과 위험자산 한도 예외",
                locator=(
                    "https://www.moel.go.kr/news/enews/report/"
                    "enewsView.do?news_seq=13711"
                ),
                publisher="고용노동부",
                as_of=_AS_OF,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            ),
            SourceEvidence(
                evidence_id=_LAW_SOURCE,
                label="소득세법·시행령 연금계좌 규정",
                locator=(
                    "https://law.go.kr/lsLinkCommonInfo.do?"
                    "lsJoLnkSeq=1021863203"
                ),
                publisher="국가법령정보센터",
                as_of=_AS_OF,
                data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
            ),
        ],
        limitations=[
            "세액공제 결과는 소득, 결정세액과 납입 재원에 따라 달라집니다.",
            "납입 조합은 제도 설명용 예시이며 개인별 납입 또는 상품 추천이 아닙니다.",
        ],
    )


def _deferred_topic_sources(evidence_ids: list[str]) -> list[SourceEvidence]:
    sources = {
        _RECEIPT_SOURCE: SourceEvidence(
            evidence_id=_RECEIPT_SOURCE,
            label="연금계좌 납입·연금수령 요건·인출순서",
            locator=(
                "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?"
                "cntntsId=7885&mi=6605"
            ),
            publisher="국세청",
            as_of=_AS_OF,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        ),
        _TAXATION_SOURCE: SourceEvidence(
            evidence_id=_TAXATION_SOURCE,
            label="사적연금 원천징수·연금외수령 과세",
            locator=(
                "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?"
                "cntntsId=7888&mi=6608"
            ),
            publisher="국세청",
            as_of=_AS_OF,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        ),
        _RETIREMENT_SOURCE: SourceEvidence(
            evidence_id=_RETIREMENT_SOURCE,
            label="퇴직연금제도 안내",
            locator="https://www.moel.go.kr/retirementpay.do",
            publisher="고용노동부",
            as_of=_AS_OF,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        ),
        _WITHDRAWAL_SOURCE: SourceEvidence(
            evidence_id=_WITHDRAWAL_SOURCE,
            label="IRP·DC형 중도인출 사유",
            locator=(
                "https://m.easylaw.go.kr/MOB/CsmInfoRetrieve.laf?"
                "ccfNo=2&cciNo=1&cnpClsNo=2&csmSeq=999"
            ),
            publisher="찾기쉬운 생활법령",
            as_of=_AS_OF,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        ),
        _LAW_SOURCE: SourceEvidence(
            evidence_id=_LAW_SOURCE,
            label="소득세법·시행령 연금계좌 규정",
            locator=(
                "https://law.go.kr/lsLinkCommonInfo.do?"
                "lsJoLnkSeq=1021863203"
            ),
            publisher="국가법령정보센터",
            as_of=_AS_OF,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        ),
    }
    return [sources[evidence_id] for evidence_id in evidence_ids]


def build_deferred_pension_topic_response(
    topic: AccountRuleTopic,
) -> ChatResponse:
    """Answer a separately requested tax/receipt topic without personal judgment."""

    financial_notice = False
    if topic == AccountRuleTopic.PENSION_RECEIPT_START:
        answer = "연금수령을 시작할 때 확인할 일반 요건을 안내합니다."
        evidence_ids = [_RECEIPT_SOURCE, _LAW_SOURCE]
        section = _section(
            "연금수령을 시작하는 일반 요건",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        "일반적으로 55세 이후 연금수령 개시를 신청해야 합니다.",
                        "계좌 가입일부터 5년이 지나야 합니다.",
                        "해당 과세기간의 연금수령한도 이내에서 받아야 합니다.",
                        (
                            "이연퇴직소득을 연금계좌에서 받을 때는 5년 요건의 "
                            "예외가 적용될 수 있습니다."
                        ),
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.FORMULA,
                    title="연금수령연차 1~10년의 연간 한도",
                    text=(
                        "연금수령한도 = 과세기간 개시일 현재 연금계좌 평가액\n"
                        "             ÷ (11 - 연금수령연차)\n"
                        "             × 120%"
                    ),
                ),
            ],
            evidence_ids,
        )
        financial_notice = True
    elif topic == AccountRuleTopic.PENSION_RECEIPT_TAX:
        answer = "연금으로 받을 때 재원과 수령 조건에 따른 일반 과세 구조입니다."
        evidence_ids = [_TAXATION_SOURCE, _LAW_SOURCE]
        section = _section(
            "연금으로 받을 때의 일반 과세 구조",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    title="세액공제 받은 개인납입금과 운용수익",
                    headers=["수령 당시 나이·계약", "지방소득세 포함 세율"],
                    rows=[
                        ["70세 미만", "5.5%"],
                        ["70세 이상 80세 미만", "4.4%"],
                        ["80세 이상", "3.3%"],
                        ["요건을 갖춘 종신계약", "3.3%"],
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    title="퇴직급여 재원인 이연퇴직소득",
                    headers=["실제 연금수령연차", "연금외수령세율 대비 적용 비율"],
                    rows=[
                        ["1~10년", "70%"],
                        ["11~20년", "60%"],
                        ["21년 이상", "50%"],
                    ],
                ),
            ],
            evidence_ids,
        )
    elif topic == AccountRuleTopic.PRIVATE_PENSION_THRESHOLD:
        answer = "연간 사적연금 과세 기준의 일반적인 적용 구조입니다."
        evidence_ids = [_TAXATION_SOURCE, _LAW_SOURCE]
        section = _section(
            "연간 사적연금 1,500만 원 기준",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        (
                            "이연퇴직소득 등 별도 분리과세 항목을 제외한 "
                            "사적연금소득이 연 1,500만 원 이하이면 저율의 "
                            "연금소득 분리과세 구조가 적용됩니다."
                        ),
                        (
                            "연 1,500만 원을 넘으면 종합과세 신고 대상이지만, "
                            "신고할 때 지방소득세 포함 16.5% 분리과세를 "
                            "선택할 수 있습니다."
                        ),
                        (
                            "IRP로 이전한 퇴직급여 재원의 연금수령액은 "
                            "1,500만 원 판단에 단순 합산하지 않습니다."
                        ),
                    ],
                )
            ],
            evidence_ids,
        )
    elif topic == AccountRuleTopic.NON_PENSION_WITHDRAWAL:
        answer = "중도인출이나 해지에는 계좌 종류와 재원별 규칙이 적용됩니다."
        evidence_ids = [
            _RECEIPT_SOURCE,
            _TAXATION_SOURCE,
            _WITHDRAWAL_SOURCE,
            _LAW_SOURCE,
        ]
        section = _section(
            "중도인출·해지의 일반 원칙",
            [
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    headers=["재원", "일반적인 연금외수령 과세"],
                    rows=[
                        ["세액공제를 받지 않은 원금", "과세제외"],
                        ["이연퇴직소득", "원래 퇴직소득세 기준"],
                        [
                            "세액공제를 받은 납입금·운용수익",
                            "기타소득 15%, 지방소득세 포함 16.5%",
                        ],
                    ],
                ),
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    items=[
                        (
                            "연금저축은 일부 인출이 가능하지만 재원별 과세는 "
                            "그대로 적용됩니다."
                        ),
                        (
                            "IRP·DC형은 주택 구입·임차보증금, 장기요양 의료비, "
                            "파산·개인회생, 재난 등 법정 사유를 확인해야 합니다."
                        ),
                        (
                            "중도인출 가능 사유와 세법상 저율 과세 사유는 "
                            "서로 다를 수 있습니다."
                        ),
                    ],
                ),
            ],
            evidence_ids,
        )
        financial_notice = True
    else:
        raise ValueError(f"unsupported deferred pension topic: {topic}")

    limitations = []
    if financial_notice:
        limitations.append(_FINANCIAL_INSTITUTION_NOTICE)
    limitations.append(PENSION_TOPIC_DEFER_NOTICE)
    return ChatResponse(
        intent=ChatIntent.ACCOUNT_RULE,
        answer=answer,
        data_mode="verified_pension_account_deferred_topic",
        sections=[section],
        sources=_deferred_topic_sources(evidence_ids),
        limitations=limitations,
    )
