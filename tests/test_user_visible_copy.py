"""사용자 노출 문구에 내부 구현 표식이 새어 나오지 않는지 검사한다."""

import re
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.chat.handlers.presentation import build_capabilities
from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatRequest, ChatResponse
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import PensionTaxScenarioInput
from backend.app.main import app

client = TestClient(app)

# 사용자 화면·응답에 나오면 안 되는 내부 구현 표식.
# 동의어(샘플 데이터·테스트용·데모용·시연용)로 바꾸는 것도 금지 대상이다.
_INTERNAL_MARKER = re.compile(
    r"교육용"
    r"|목\s*데이터"
    r"|목\s*계좌"
    r"|목\s*시나리오"
    r"|가상"
    r"|샘플\s*데이터"
    r"|테스트용"
    r"|데모용"
    r"|시연용"
    r"|데모\s*DB"
    r"|데모\s*기준"
    r"|\bmock\b"
    r"|\bfixture\b",
    re.IGNORECASE,
)


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


def _visible_text(response: ChatResponse) -> list[str]:
    """사용자가 실제로 읽는 필드만 모은다(내부 식별자·locator는 제외)."""
    text = [response.answer, *response.limitations]
    if response.salutation is not None:
        text.append(response.salutation)
    for section in response.sections:
        text.extend((section.title, section.content))
        text.extend(block.plain_text() for block in section.blocks)
    for evidence in response.numeric_evidence:
        text.extend((evidence.label, evidence.basis))
    for visualization in response.visualizations:
        text.extend((visualization.title, visualization.description))
        text.extend(item.label for item in visualization.items)
        for series in visualization.series:
            text.append(series.label)
            text.extend(point.label for point in series.points)
    for source in response.sources:
        text.append(source.label)
        if source.publisher is not None:
            text.append(source.publisher)
    for follow_up in response.suggested_follow_ups:
        text.extend((follow_up.label, follow_up.message))
    if response.scenario_evaluation is not None:
        text.append(response.scenario_evaluation.source.label)
    return [item for item in text if item]


def _assert_clean(label: str, values: list[str]) -> None:
    offending = [value for value in values if _INTERNAL_MARKER.search(value)]
    assert not offending, f"{label}에 내부 구현 표식이 노출됐습니다: {offending}"


def test_scenario_response_copy_excludes_internal_markers() -> None:
    response = _service().ask(
        ChatRequest(
            message="중복·위험 편중 계좌를 진단해줘",
            scenario_code="overlap_risk_concentration",
        )
    )

    _assert_clean("계좌 진단 응답", _visible_text(response))


def test_unknown_scenario_copy_excludes_internal_markers() -> None:
    response = _service().ask(
        ChatRequest(message="계좌를 진단해줘", scenario_code="does_not_exist")
    )

    _assert_clean("계좌 선택 안내", _visible_text(response))


def test_unconfigured_disclosure_copy_excludes_internal_markers() -> None:
    response = _service().ask(ChatRequest(message="IRP 사업자 수익률을 알려줘"))

    _assert_clean("공시 미구성 안내", [response.answer])


def test_pension_tax_response_copy_excludes_internal_markers() -> None:
    response = _service().ask(
        ChatRequest(
            message="연금저축과 IRP 세액공제를 계산해줘",
            pension_tax=PensionTaxScenarioInput.model_validate(
                {
                    "tax_year": 2026,
                    "income_basis": "gross_salary",
                    "income_amount_krw": Decimal("50000000"),
                    "pension_savings": {
                        "balance_krw": Decimal("30000000"),
                        "current_year_contribution_krw": Decimal("6000000"),
                    },
                    "irp": {
                        "balance_krw": Decimal("50000000"),
                        "current_year_contribution_krw": Decimal("3000000"),
                    },
                    "withdrawal_reason": "general",
                    "irp_deferred_income_status": "none",
                }
            ),
        )
    )

    _assert_clean("세액공제 응답", _visible_text(response))


def test_capabilities_copy_excludes_internal_markers() -> None:
    capabilities = build_capabilities(scenarios=LocalScenarioRepository())

    _assert_clean(
        "기능 안내",
        [
            *capabilities.supported,
            *capabilities.conditional,
            *capabilities.unsupported,
        ],
    )


def test_account_link_options_notice_excludes_internal_markers() -> None:
    response = client.get("/accounts/link-options")

    assert response.status_code == 200
    body = response.json()
    notice_text = [body["notice"]]
    notice_text.extend(
        option["description"]
        for option in body["options"]
        if option["description"] is not None
    )

    _assert_clean("계좌 연동 안내", notice_text)
