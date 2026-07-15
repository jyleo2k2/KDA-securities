import re
from datetime import date
from decimal import Decimal
from typing import Protocol

from ..engine import AccountType, evaluate_mock_scenario, evaluate_risk_cap
from ..retrieval.repository import KnowledgeMatch, NewsMatch
from .disclosures import ProviderDisclosure
from .models import (
    AnswerSection,
    ChatCapabilities,
    ChatIntent,
    ChatRequest,
    ChatResponse,
    DataBoundary,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
    extract_numeric_claims,
)
from .query_planner import BlockedReason, QueryPlan, plan_question
from .scenarios import LocalScenarioRepository


class KnowledgeSearch(Protocol):
    def search_knowledge(
        self, query: str, *, limit: int = 8
    ) -> list[KnowledgeMatch]: ...


class DisclosureSearch(Protocol):
    def search(
        self,
        question: str,
        *,
        account_type: AccountType,
        limit: int,
    ) -> list[ProviderDisclosure]: ...


class NewsSearch(Protocol):
    def latest_news(self, search_query: str, *, limit: int = 10) -> list[NewsMatch]: ...


SCENARIO_KEYWORDS = {
    "방치": "dc_dormant",
    "세액공제": "tax_contribution_uninvested",
    "미운용": "tax_contribution_uninvested",
    "중복": "overlap_risk_concentration",
    "편중": "overlap_risk_concentration",
}
VERIFIED_AS_OF = date(2026, 7, 13)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _knowledge_sources(matches: list[KnowledgeMatch]) -> list[SourceEvidence]:
    return [
        SourceEvidence(
            evidence_id=f"knowledge:{match.chunk_id}",
            label=match.title,
            locator=match.source_url,
            publisher="연금 코파일럿 검증 지식",
            as_of=VERIFIED_AS_OF,
            data_boundary=DataBoundary.VERIFIED_KNOWLEDGE,
        )
        for match in matches
    ]


def _source_ids(sources: list[SourceEvidence]) -> list[str]:
    return [source.evidence_id for source in sources]


class ChatService:
    def __init__(
        self,
        *,
        knowledge: KnowledgeSearch,
        scenarios: LocalScenarioRepository,
        disclosures: DisclosureSearch | None = None,
        news: NewsSearch | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scenarios = scenarios
        self._disclosures = disclosures
        self._news = news

    def capabilities(self) -> ChatCapabilities:
        return ChatCapabilities(
            supported=[
                "DC형·IRP·연금저축 계좌 규칙 근거 Q&A",
                "목계좌 시나리오 위험자산 한도와 통합 자산군 진단",
                "근거·기준일·실데이터/목데이터 경계 표시",
            ],
            conditional=[
                "Supabase 실적재 후 회사·사업자 과거 공시 비교",
                "NAVER 뉴스 적재 후 최신 뉴스 메타데이터 조회",
            ],
            unsupported=[
                "DC·IRP 개별 상품 비교",
                "미래 수익률·목표가 예측",
                "주문·자동운용",
            ],
            scenario_codes=[item.code for item in self._scenarios.list()],
        )

    def plan(self, request: ChatRequest) -> QueryPlan:
        return plan_question(
            request.message, default_max_results=request.max_results
        )

    def ask(
        self, request: ChatRequest, *, plan: QueryPlan | None = None
    ) -> ChatResponse:
        resolved_plan = plan or self.plan(request)
        if resolved_plan.blocked_reason is not None and not (
            resolved_plan.blocked_reason == BlockedReason.UNSUPPORTED
            and (request.portfolio is not None or request.scenario_code is not None)
        ):
            return self._blocked_response(resolved_plan.blocked_reason)
        request = request.model_copy(
            update={
                "message": resolved_plan.normalized_message,
                "max_results": resolved_plan.max_results,
            }
        )
        if request.portfolio is not None:
            return self._custom_portfolio(request)
        scenario_code = request.scenario_code or self._scenario_code(request.message)
        if scenario_code is not None:
            return self._scenario_response(scenario_code)
        if resolved_plan.intent == ChatIntent.MOCK_PORTFOLIO:
            return self._scenario_selection_response()
        if resolved_plan.intent == ChatIntent.NEWS:
            assert resolved_plan.news_query is not None
            return self._news_response(
                request, search_query=resolved_plan.news_query
            )
        if resolved_plan.intent == ChatIntent.PROVIDER_DISCLOSURE:
            account_type = resolved_plan.account_types[0]
            return self._disclosure_response(request, account_type)
        if resolved_plan.intent == ChatIntent.ACCOUNT_RULE:
            return self._account_rule_response(request, resolved_plan)
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "현재 MVP는 연금계좌 규칙, 목계좌 진단, 과거 공시와 뉴스 "
                "근거 조회에 답할 수 있습니다. 질문에 계좌 유형이나 진단할 "
                "목시나리오를 포함해 주세요."
            ),
            data_mode="safe_fallback",
            limitations=["범용 투자·세무·법률 상담은 지원하지 않습니다."],
        )

    @staticmethod
    def _blocked_response(reason: BlockedReason) -> ChatResponse:
        if reason == BlockedReason.SENSITIVE_INFORMATION:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "개인 식별정보나 인증정보가 포함된 질문은 처리하지 않습니다. "
                    "해당 값을 삭제한 뒤 제도나 운용 원리만 질문해 주세요."
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
                    "미래 수익률·목표가·수익 보장은 제공하지 않습니다. "
                    "승인된 가정 시나리오 엔진이 구현되기 전에는 과거 공시와 "
                    "손실 가능성만 설명합니다."
                ),
                data_mode="blocked",
                limitations=["미래 수익 예측은 MVP 범위 밖입니다."],
            )
        if reason == BlockedReason.ORDER_REQUEST:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "상품 선택과 주문은 이용자가 금융회사 공식 채널에서 직접 "
                    "수행해야 합니다. 챗봇은 판단 기준과 근거만 설명합니다."
                ),
                data_mode="blocked",
                limitations=["주문·자동운용은 지원하지 않습니다."],
            )
        if reason == BlockedReason.PRODUCT_LEVEL_UNAVAILABLE:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "현재 실적재 계약은 연금저축 회사와 퇴직연금 사업자 집계 "
                    "단위입니다. 개별 상품 데이터로 오인될 수 있어 상품 단위 "
                    "비교·추천은 제공하지 않습니다."
                ),
                data_mode="unavailable",
                limitations=["검증된 개별 상품 식별자와 적격성 데이터가 필요합니다."],
            )
        if reason == BlockedReason.ACCOUNT_SELECTION_REQUIRED:
            return ChatResponse(
                intent=ChatIntent.OUT_OF_SCOPE,
                answer=(
                    "공시 수치는 계좌 제도별 항목이 달라 한 번에 섞어 비교하지 "
                    "않습니다. DC형, IRP, 연금저축 중 하나를 지정해 주세요."
                ),
                data_mode="blocked",
                limitations=["계좌별 공시 계약을 분리해 조회합니다."],
            )
        return ChatResponse(
            intent=ChatIntent.OUT_OF_SCOPE,
            answer=(
                "현재 MVP는 연금계좌 규칙, 목계좌 진단, 과거 공시와 뉴스 "
                "근거 조회에 답할 수 있습니다. 질문에 계좌 유형이나 진단할 "
                "목시나리오를 포함해 주세요."
            ),
            data_mode="safe_fallback",
            limitations=["범용 투자·세무·법률 상담은 지원하지 않습니다."],
        )

    def _account_rule_response(
        self, request: ChatRequest, plan: QueryPlan
    ) -> ChatResponse:
        matches = self._knowledge.search_knowledge(request.message, limit=3)
        sources = _knowledge_sources(matches)
        if not matches:
            return ChatResponse(
                intent=ChatIntent.ACCOUNT_RULE,
                answer="검증된 근거 문서를 찾지 못해 답변을 생성하지 않았습니다.",
                data_mode="verified_knowledge",
                limitations=["질문을 계좌 유형과 함께 더 구체적으로 입력해 주세요."],
            )

        risk_question = "위험자산" in request.message or "한도" in request.message
        has_retirement_account = bool(
            {AccountType.DC, AccountType.IRP}.intersection(plan.account_types)
        )
        has_pension_savings = AccountType.PENSION_SAVINGS in plan.account_types
        numeric: list[NumericEvidence] = []
        if plan.combines_account_rules and risk_question:
            answer = (
                "여러 연금계좌를 합산해 하나의 위험자산 한도를 적용하지 "
                "않습니다. DC형과 IRP는 각 계좌에서 일반 위험자산을 적립금의 "
                "70%까지로 판정하고, 연금저축펀드에는 같은 총량 한도를 "
                "적용하지 않아 계좌별로 따로 확인해야 합니다."
            )
            numeric.append(
                NumericEvidence(
                    label="DC형·IRP 계좌별 일반 위험자산 한도",
                    value=Decimal("70"),
                    unit="%",
                    evidence_id=sources[0].evidence_id,
                    basis="검증된 계좌별 규칙",
                )
            )
        elif risk_question and has_pension_savings and not has_retirement_account:
            answer = (
                "연금저축펀드에는 DC형·IRP와 동일한 위험자산 총량 한도를 "
                "적용하지 않습니다. 대신 해당 계좌에서 편입 가능한 상품인지 "
                "별도 적격성 규칙으로 확인해야 합니다."
            )
        elif risk_question and has_retirement_account:
            answer = (
                "DC형과 IRP의 일반 위험자산은 적립금의 70%까지로 판정합니다. "
                "적격 TDF·디폴트옵션 같은 법정 예외는 적격성이 명시적으로 "
                "확인된 경우에만 일반 위험자산과 분리합니다. 연금저축펀드에는 "
                "같은 총량 한도를 적용하지 않습니다."
            )
            numeric.append(
                NumericEvidence(
                    label="DC형·IRP 계좌별 일반 위험자산 한도",
                    value=Decimal("70"),
                    unit="%",
                    evidence_id=sources[0].evidence_id,
                    basis="검증된 계좌 규칙",
                )
            )
        else:
            excerpt = re.sub(r"\s+", " ", matches[0].content).strip()[:600]
            answer = f"검증 문서에서 확인한 내용입니다. {excerpt}"
            for index, (value, unit) in enumerate(
                sorted(extract_numeric_claims(answer)), start=1
            ):
                numeric.append(
                    NumericEvidence(
                        label=f"{matches[0].title} 답변 수치 {index}",
                        value=value,
                        unit=unit,
                        evidence_id=sources[0].evidence_id,
                        basis="검증된 지식 문서 답변 인용",
                    )
                )

        return ChatResponse(
            intent=ChatIntent.ACCOUNT_RULE,
            answer=answer,
            data_mode="verified_knowledge",
            sections=[
                AnswerSection(
                    kind=SectionKind.FACT,
                    title="검색된 근거",
                    content=re.sub(r"\s+", " ", match.content).strip()[:800],
                    evidence_ids=[f"knowledge:{match.chunk_id}"],
                )
                for match in matches
            ],
            sources=sources,
            numeric_evidence=numeric,
            limitations=["상품별 적격성은 공식 상품 데이터로 별도 확인해야 합니다."],
        )

    def _custom_portfolio(self, request: ChatRequest) -> ChatResponse:
        assert request.portfolio is not None
        evaluation = evaluate_risk_cap(request.portfolio)
        source = SourceEvidence(
            evidence_id="engine:risk_cap",
            label=evaluation.evidence[0].source.label,
            locator=evaluation.evidence[0].source.reference,
            as_of=evaluation.evidence[0].source.as_of,
            publisher="연금 코파일럿 규칙 엔진",
            data_boundary=DataBoundary.ENGINE,
        )
        ratio = _decimal_text(evaluation.general_risky_ratio_percent)
        if evaluation.limit_percent is None:
            answer = (
                f"입력한 연금저축 목포트폴리오의 일반 위험자산 비중은 {ratio}%입니다. "
                "DC형·IRP의 총량 한도는 적용하지 않고 상품 적격성을 별도로 "
                "확인해야 합니다."
            )
        else:
            status_text = "한도 이내" if evaluation.within_limit else "한도 초과"
            answer = (
                f"입력한 {evaluation.evaluated_input.account_type.value.upper()} "
                f"목포트폴리오의 일반 위험자산 비중은 {ratio}%이며 {status_text}입니다."
            )
        numeric = [
            NumericEvidence(
                label="일반 위험자산 비중",
                value=evaluation.general_risky_ratio_percent,
                unit="%",
                evidence_id=source.evidence_id,
                basis="규칙 엔진 계산",
            )
        ]
        if evaluation.limit_percent is not None:
            numeric.append(
                NumericEvidence(
                    label="일반 위험자산 한도",
                    value=evaluation.limit_percent,
                    unit="%",
                    evidence_id=source.evidence_id,
                    basis="버전형 계좌 규칙",
                )
            )
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=answer,
            data_mode="request_mock",
            sources=[source],
            numeric_evidence=numeric,
            engine_results=[evaluation],
            limitations=["입력 포트폴리오는 실제 계좌가 아닌 목데이터로 처리했습니다."],
        )

    def _scenario_response(self, scenario_code: str) -> ChatResponse:
        scenario = self._scenarios.get(scenario_code)
        if scenario is None:
            return self._scenario_selection_response(
                limitation=f"알 수 없는 목시나리오 코드: {scenario_code}"
            )
        evaluation = evaluate_mock_scenario(scenario)
        sources = [
            SourceEvidence(
                evidence_id="mock:scenario",
                label=evaluation.source.label,
                locator=evaluation.source.reference,
                as_of=evaluation.source.as_of,
                data_boundary=DataBoundary.MOCK,
            ),
            SourceEvidence(
                evidence_id="engine:scenario",
                label="목계좌 통합 집계 엔진",
                locator=f"engine://{evaluation.engine_name}/{evaluation.engine_version}",
                as_of=evaluation.source.as_of,
                data_boundary=DataBoundary.ENGINE,
            ),
        ]
        account_lines: list[str] = []
        numeric = [
            NumericEvidence(
                label="목시나리오 총자산",
                value=evaluation.total_amount_krw,
                unit="KRW",
                evidence_id="engine:scenario",
                basis="목계좌 합산",
            )
        ]
        for result in evaluation.account_evaluations:
            account_name = result.evaluated_input.account_type.value
            ratio = _decimal_text(result.general_risky_ratio_percent)
            if result.limit_percent is None:
                account_lines.append(f"{account_name}: 일반 위험자산 {ratio}%")
            else:
                status_text = "이내" if result.within_limit else "초과"
                account_lines.append(
                    f"{account_name}: 일반 위험자산 {ratio}%로 한도 {status_text}"
                )
            numeric.append(
                NumericEvidence(
                    label=f"{account_name} 일반 위험자산 비중",
                    value=result.general_risky_ratio_percent,
                    unit="%",
                    evidence_id="engine:scenario",
                    basis="규칙 엔진 계산",
                )
            )
        for item in evaluation.asset_allocations:
            numeric.append(
                NumericEvidence(
                    label=f"{item.asset_class_code} 통합 자산군 비중",
                    value=item.allocation_percent,
                    unit="%",
                    evidence_id="engine:scenario",
                    basis="목계좌 통합 집계 엔진 계산",
                )
            )
        allocation_text = ", ".join(
            f"{item.asset_class_code} {_decimal_text(item.allocation_percent)}%"
            for item in evaluation.asset_allocations
        )
        duplicate_text = (
            ", ".join(evaluation.duplicated_asset_classes)
            if evaluation.duplicated_asset_classes
            else "계좌 간 반복 자산군 없음"
        )
        answer = (
            f"'{scenario.name}' 목시나리오를 규칙 엔진으로 진단했습니다. "
            + " / ".join(account_lines)
            + f". 통합 자산군은 {allocation_text}이며, 중복 확인 결과는 "
            + f"{duplicate_text}입니다."
        )
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=answer,
            data_mode="mock_scenario",
            sections=[
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="계좌별 위험자산 판정",
                    content=" / ".join(account_lines),
                    evidence_ids=["engine:scenario"],
                ),
                AnswerSection(
                    kind=SectionKind.SERVICE_EXPLANATION,
                    title="통합 자산군과 중복",
                    content=f"{allocation_text}; {duplicate_text}",
                    evidence_ids=["mock:scenario", "engine:scenario"],
                ),
            ],
            sources=sources,
            numeric_evidence=numeric,
            engine_results=evaluation.account_evaluations,
            scenario_evaluation=evaluation,
            limitations=["모든 계좌와 보유자산은 발표용 목데이터입니다."],
        )

    def _scenario_selection_response(
        self, limitation: str | None = None
    ) -> ChatResponse:
        names = ", ".join(item.code for item in self._scenarios.list())
        limitations = [limitation] if limitation else []
        limitations.append("진단할 scenario_code를 요청에 지정해 주세요.")
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=f"사용 가능한 목시나리오는 {names}입니다.",
            data_mode="mock_scenario_selection",
            limitations=limitations,
        )

    def _disclosure_response(
        self, request: ChatRequest, account_type: AccountType
    ) -> ChatResponse:
        if self._disclosures is None:
            return ChatResponse(
                intent=ChatIntent.PROVIDER_DISCLOSURE,
                answer=(
                    "원격 Supabase 실공시 적재가 확인되지 않아 회사·사업자 수치를 "
                    "표시하지 않았습니다. fixture를 실데이터로 대신하지 않습니다."
                ),
                data_mode="unavailable",
                limitations=["DATABASE_URL과 FSS 실적재가 필요합니다."],
            )
        rows = self._disclosures.search(
            request.message,
            account_type=account_type,
            limit=request.max_results,
        )
        if not rows:
            return ChatResponse(
                intent=ChatIntent.PROVIDER_DISCLOSURE,
                answer="조건에 맞는 최신 실공시 행을 찾지 못했습니다.",
                data_mode="official_disclosure",
                limitations=["수집 상태와 질문의 회사명을 확인해 주세요."],
            )
        sources: list[SourceEvidence] = []
        numeric: list[NumericEvidence] = []
        lines: list[str] = []
        for index, row in enumerate(rows, start=1):
            evidence_id = f"disclosure:{index}"
            sources.append(
                SourceEvidence(
                    evidence_id=evidence_id,
                    label=f"FSS {row.account_type.value} 사업자 공시",
                    locator=row.source_locator,
                    publisher="금융감독원 통합연금포털",
                    as_of=row.period_end,
                    data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
                )
            )
            current = (
                "공시값 없음"
                if row.earn_rate_current_pct is None
                else f"{_decimal_text(row.earn_rate_current_pct)}%"
            )
            three_year = (
                "공시값 없음"
                if row.avg_earn_rate_3y_pct is None
                else f"{_decimal_text(row.avg_earn_rate_3y_pct)}%"
            )
            lines.append(
                f"{row.company_name}: 당기 과거 수익률 {current}, "
                f"3년 연환산 {three_year}"
            )
            for label, value in (
                ("당기 과거 수익률", row.earn_rate_current_pct),
                ("3년 연환산 수익률", row.avg_earn_rate_3y_pct),
            ):
                if value is not None:
                    numeric.append(
                        NumericEvidence(
                            label=f"{row.company_name} {label}",
                            value=value,
                            unit="%",
                            evidence_id=evidence_id,
                            basis=f"{row.year}Q{row.quarter} FSS 공시",
                        )
                    )
        return ChatResponse(
            intent=ChatIntent.PROVIDER_DISCLOSURE,
            answer=" / ".join(lines),
            data_mode="official_disclosure",
            sections=[
                AnswerSection(
                    kind=SectionKind.FACT,
                    title="회사·사업자 과거 공시",
                    content=" / ".join(lines),
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            numeric_evidence=numeric,
            limitations=[
                "사업자 집계 공시이며 개별 상품 또는 개인 계좌 수익률이 아닙니다.",
                "과거 실적은 미래 수익을 의미하지 않습니다.",
            ],
        )

    def _news_response(
        self, request: ChatRequest, *, search_query: str
    ) -> ChatResponse:
        if self._news is None:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer=(
                    "저장된 뉴스 메타데이터가 없어 최신 뉴스 답변을 "
                    "생성하지 않았습니다."
                ),
                data_mode="unavailable",
                limitations=["NAVER 뉴스 수집과 DATABASE_URL이 필요합니다."],
            )
        matches = self._news.latest_news(search_query, limit=request.max_results)
        if not matches:
            return ChatResponse(
                intent=ChatIntent.NEWS,
                answer="해당 검색어로 저장된 뉴스 메타데이터를 찾지 못했습니다.",
                data_mode="news_metadata",
                limitations=["기사 본문을 임의로 생성하지 않습니다."],
            )
        sources = [
            SourceEvidence(
                evidence_id=f"news:{item.item_id}",
                label=item.title,
                locator=item.original_url,
                publisher="외부 뉴스 원문",
                as_of=item.published_at,
                data_boundary=DataBoundary.NEWS_METADATA,
            )
            for item in matches
        ]
        lines = [
            f"{item.title} ({item.published_at.date().isoformat()})"
            if item.published_at is not None
            else item.title
            for item in matches
        ]
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=" / ".join(lines),
            data_mode="news_metadata",
            sections=[
                AnswerSection(
                    kind=SectionKind.EXTERNAL_OPINION,
                    title="뉴스 검색 메타데이터",
                    content=" / ".join(lines),
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            limitations=[
                "기사 본문이 아닌 제목·요약·원문 링크 메타데이터입니다.",
                "뉴스 사실과 외부 의견은 원문에서 다시 확인해야 합니다.",
            ],
        )

    @staticmethod
    def _scenario_code(message: str) -> str | None:
        return next(
            (code for keyword, code in SCENARIO_KEYWORDS.items() if keyword in message),
            None,
        )
