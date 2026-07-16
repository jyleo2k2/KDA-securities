import json

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest, DataBoundary
from backend.app.chat.narrator import ClaudeNarrator
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import PensionTaxScenarioInput
from backend.app.main import app, get_chat_narrator, get_chat_service


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
    )


def _input_payload() -> dict:
    return {
        "tax_year": 2026,
        "income_basis": "gross_salary",
        "income_amount_krw": "50000000",
        "pension_savings": {
            "balance_krw": "30000000",
            "current_year_contribution_krw": "6000000",
        },
        "irp": {
            "balance_krw": "50000000",
            "current_year_contribution_krw": "3000000",
        },
        "withdrawal_reason": "general",
        "irp_deferred_income_status": "none",
    }


def _inputs() -> PensionTaxScenarioInput:
    return PensionTaxScenarioInput.model_validate(_input_payload())


EXPECTED_CLOSING_NOTICE = (
    "자세한 내용은 금융기관을 통한 확인 및 세무전문가의 상담이 필요합니다."
)


def test_tax_question_without_structured_values_requests_input() -> None:
    response = _service().ask(
        ChatRequest(
            message="연금저축과 IRP 세액공제와 중도해지 세금을 알려줘"
        )
    )

    assert response.intent == ChatIntent.PENSION_TAX
    assert response.data_mode == "input_required"
    assert response.pension_tax_result is None
    assert any("계좌번호" in item for item in response.limitations)


def test_natural_language_tax_credit_question_runs_without_form_input() -> None:
    response = _service().ask(
        ChatRequest(
            message=(
                "올해 연금저축에 700만 원, IRP에 400만 원을 납입했고 "
                "총급여는 5,000만 원이야. 세액공제 대상 금액과 예상 "
                "세액공제액을 알려줘."
            )
        )
    )

    assert response.data_mode == "user_input_engine"
    assert response.pension_tax_result is not None
    assert response.pension_tax_result.tax_credit is not None
    assert response.pension_tax_result.withdrawal is None
    assert "900만 원" in response.answer
    assert "148.5만 원" in response.answer
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE


def test_natural_language_max_withdrawal_question_runs_without_form_input() -> None:
    response = _service().ask(
        ChatRequest(
            message=(
                "연금저축 잔액이 3,000만 원이고 IRP 잔액이 5,000만 "
                "원이야. 올해 납입액은 없고 IRP 퇴직금 이전분은 몰라. "
                "두 계좌를 일반 중도해지하면 최대로 얼마가 과세될 수 있어?"
            )
        )
    )

    assert response.data_mode == "user_input_engine"
    assert response.pension_tax_result is not None
    assert response.pension_tax_result.withdrawal is not None
    assert response.pension_tax_result.withdrawal.status == "estimated"
    assert "8,000만 원" in response.answer
    assert "1,320만 원" in response.answer
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE


def test_natural_language_unavoidable_reason_blocks_without_balances() -> None:
    response = _service().ask(
        ChatRequest(
            message=(
                "의료비 때문에 연금저축과 IRP를 중도인출하려고 해. "
                "부득이한 인출로 보고 16.5% 세금을 계산해줘."
            )
        )
    )

    assert response.data_mode == "user_input_engine"
    assert response.pension_tax_result is not None
    assert response.pension_tax_result.withdrawal is not None
    assert response.pension_tax_result.withdrawal.status == "requires_review"
    assert response.pension_tax_result.withdrawal.total_balance_krw is None
    assert "계산하지 않았습니다" in response.answer
    assert response.numeric_evidence == []
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE


def test_combined_tax_question_uses_engine_results_and_evidence() -> None:
    response = _service().ask(
        ChatRequest(
            message="연금저축과 IRP 세액공제와 중도해지 세금을 알려줘",
            pension_tax=_inputs(),
        )
    )

    assert response.intent == ChatIntent.PENSION_TAX
    assert response.data_mode == "user_input_engine"
    assert response.pension_tax_result is not None
    assert response.pension_tax_result.tax_credit is not None
    assert response.pension_tax_result.withdrawal is not None
    assert "148.5만 원" in response.answer
    assert "1,171.5만 원" in response.answer
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE
    assert {source.data_boundary for source in response.sources} >= {
        DataBoundary.USER_INPUT,
        DataBoundary.ENGINE,
        DataBoundary.VERIFIED_KNOWLEDGE,
    }
    assert all(item.evidence_id for item in response.numeric_evidence)


def test_service_calls_only_the_requested_tax_calculation() -> None:
    tax_credit = _service().ask(
        ChatRequest(
            message="연금계좌 세액공제 혜택을 계산해줘",
            pension_tax=_inputs(),
        )
    ).pension_tax_result
    withdrawal = _service().ask(
        ChatRequest(
            message="연금저축과 IRP 연금외수령 과세액을 알려줘",
            pension_tax=_inputs(),
        )
    ).pension_tax_result

    assert tax_credit is not None
    assert tax_credit.tax_credit is not None
    assert tax_credit.withdrawal is None
    assert withdrawal is not None
    assert withdrawal.tax_credit is None
    assert withdrawal.withdrawal is not None


def test_chatbot_reproduces_the_eighty_million_won_max_example() -> None:
    payload = _input_payload()
    payload["pension_savings"]["current_year_contribution_krw"] = "0"
    payload["irp"]["current_year_contribution_krw"] = "0"
    payload["irp_deferred_income_status"] = "unknown"
    response = _service().ask(
        ChatRequest(
            message="연금저축과 IRP 중도해지 세금을 알려줘",
            pension_tax=PensionTaxScenarioInput.model_validate(payload),
        )
    )

    assert "8,000만 원" in response.answer
    assert "1,320만 원" in response.answer
    assert any("이연퇴직소득" in item for item in response.limitations)
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE


def test_unavoidable_withdrawal_ends_with_expert_review_notice() -> None:
    payload = _input_payload()
    payload["withdrawal_reason"] = "unavoidable"
    response = _service().ask(
        ChatRequest(
            message="의료비 때문에 중도인출하려고 해. 16.5% 세금을 계산해줘.",
            pension_tax=PensionTaxScenarioInput.model_validate(payload),
        )
    )

    assert response.pension_tax_result is not None
    assert response.pension_tax_result.withdrawal is not None
    assert response.pension_tax_result.withdrawal.status == "requires_review"
    assert "계산하지 않았습니다" in response.answer
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE


def test_demo_chat_accepts_structured_tax_input() -> None:
    chatbot = _service()
    app.dependency_overrides[get_chat_service] = lambda: chatbot
    app.dependency_overrides[get_chat_narrator] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat/demo",
                json={
                    "message": "세액공제 혜택과 중도해지 세금을 알려줘",
                    "pension_tax": _input_payload(),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "pension_tax"
    assert payload["pension_tax_result"]["tax_credit"] is not None
    assert payload["pension_tax_result"]["withdrawal"] is not None


def test_demo_chat_runs_all_three_guide_questions_without_form_input() -> None:
    cases = (
        (
            "올해 연금저축에 700만 원, IRP에 400만 원을 납입했고 "
            "총급여는 5,000만 원이야. 세액공제 대상 금액과 예상 "
            "세액공제액을 알려줘.",
            "1485000.00",
            None,
        ),
        (
            "연금저축 잔액이 3,000만 원이고 IRP 잔액이 5,000만 "
            "원이야. 올해 납입액은 없고 IRP 퇴직금 이전분은 몰라. "
            "두 계좌를 일반 중도해지하면 최대로 얼마가 과세될 수 있어?",
            None,
            "13200000.00",
        ),
        (
            "의료비 때문에 연금저축과 IRP를 중도인출하려고 해. "
            "부득이한 인출로 보고 16.5% 세금을 계산해줘.",
            None,
            "requires_review",
        ),
    )
    chatbot = _service()
    app.dependency_overrides[get_chat_service] = lambda: chatbot
    app.dependency_overrides[get_chat_narrator] = lambda: None
    try:
        with TestClient(app) as client:
            responses = [
                client.post("/chat/demo", json={"message": message})
                for message, _, _ in cases
            ]
    finally:
        app.dependency_overrides.clear()

    for response, (_, expected_credit, expected_withdrawal) in zip(
        responses, cases, strict=True
    ):
        assert response.status_code == 200
        payload = response.json()
        assert payload["data_mode"] == "user_input_engine"
        assert payload["answer"].splitlines()[-1] == EXPECTED_CLOSING_NOTICE
        result = payload["pension_tax_result"]
        if expected_credit is not None:
            assert (
                result["tax_credit"]["rate_scenarios"][0][
                    "estimated_tax_credit_krw"
                ]
                == expected_credit
            )
        elif expected_withdrawal == "requires_review":
            assert result["withdrawal"]["status"] == "requires_review"
        else:
            assert (
                result["withdrawal"][
                    "estimated_max_other_income_withholding_krw"
                ]
                == expected_withdrawal
            )


def test_engine_tax_endpoints_share_the_same_contract() -> None:
    payload = _input_payload()
    credit_input = {
        "tax_year": payload["tax_year"],
        "income_basis": payload["income_basis"],
        "income_amount_krw": payload["income_amount_krw"],
        "pension_savings_contribution_krw": payload["pension_savings"][
            "current_year_contribution_krw"
        ],
        "irp_contribution_krw": payload["irp"][
            "current_year_contribution_krw"
        ],
    }
    withdrawal_input = {
        "tax_year": payload["tax_year"],
        "pension_savings": payload["pension_savings"],
        "irp": payload["irp"],
        "withdrawal_reason": payload["withdrawal_reason"],
        "irp_deferred_income_status": payload["irp_deferred_income_status"],
    }
    with TestClient(app) as client:
        credit = client.post("/engine/pension-tax-credit", json=credit_input)
        withdrawal = client.post(
            "/engine/non-pension-withdrawal-estimate",
            json=withdrawal_input,
        )

    assert credit.status_code == 200
    assert (
        credit.json()["rate_scenarios"][0]["estimated_tax_credit_krw"]
        == "1485000.00"
    )
    assert withdrawal.status_code == 200
    assert (
        withdrawal.json()["estimated_max_other_income_withholding_krw"]
        == "11715000.00"
    )


def test_narrator_must_call_both_tax_tools_before_rephrasing() -> None:
    inputs = _inputs()
    base = _service().ask(
        ChatRequest(
            message="세액공제 혜택과 중도해지 세금을 알려줘",
            pension_tax=inputs,
        )
    )
    output = json.dumps(
        {
            "narration": base.answer.rsplit("\n", maxsplit=1)[0],
            "review_note": "검증 답변을 유지했습니다.",
        },
        ensure_ascii=False,
    )
    turn = 0

    def respond(messages, info) -> ModelResponse:
        nonlocal turn
        turn += 1
        if turn == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "calculate_pension_tax_credit_tool",
                        args={
                            "inputs": inputs.to_tax_credit_input().model_dump(
                                mode="json"
                            )
                        },
                        tool_call_id="credit-1",
                    ),
                    ToolCallPart(
                        "estimate_non_pension_withdrawal_tax_tool",
                        args={
                            "inputs": inputs.to_withdrawal_input().model_dump(
                                mode="json"
                            )
                        },
                        tool_call_id="withdrawal-1",
                    ),
                ]
            )
        return ModelResponse(parts=[TextPart(output)])

    narrator = ClaudeNarrator(api_key="test-key", model="test-model")
    with narrator.agent.override(model=FunctionModel(respond)):
        response = narrator.narrate(base, pension_tax_input=inputs)

    assert turn == 2
    assert response.narration_mode == "claude_verified"
    assert response.answer == base.answer
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE


def test_narrator_falls_back_when_tax_tool_is_skipped() -> None:
    inputs = _inputs()
    base = _service().ask(
        ChatRequest(
            message="세액공제 혜택을 계산해줘",
            pension_tax=inputs,
        )
    )
    output = json.dumps(
        {"narration": base.answer, "review_note": "검증 답변을 유지했습니다."},
        ensure_ascii=False,
    )

    def respond(messages, info) -> ModelResponse:
        return ModelResponse(parts=[TextPart(output)])

    narrator = ClaudeNarrator(api_key="test-key", model="test-model")
    with narrator.agent.override(model=FunctionModel(respond)):
        response = narrator.narrate(base, pension_tax_input=inputs)

    assert response.narration_mode == "deterministic"
    assert "Tool을 호출하지 않아" in response.limitations[-1]


def test_narrator_uses_tool_input_extracted_from_natural_question() -> None:
    message = (
        "올해 연금저축에 700만 원, IRP에 400만 원을 납입했고 "
        "총급여는 5,000만 원이야. 세액공제 대상 금액과 예상 "
        "세액공제액을 알려줘."
    )
    base = _service().ask(ChatRequest(message=message))
    output = json.dumps(
        {"narration": base.answer, "review_note": "Tool 결과를 유지했습니다."},
        ensure_ascii=False,
    )
    turn = 0

    def respond(messages, info) -> ModelResponse:
        nonlocal turn
        turn += 1
        if turn == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "calculate_pension_tax_credit_tool",
                        args={
                            "inputs": {
                                "tax_year": 2026,
                                "income_basis": "gross_salary",
                                "income_amount_krw": "50000000",
                                "pension_savings_contribution_krw": "7000000",
                                "irp_contribution_krw": "4000000",
                            }
                        },
                        tool_call_id="natural-credit-1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(output)])

    narrator = ClaudeNarrator(api_key="test-key", model="test-model")
    with narrator.agent.override(model=FunctionModel(respond)):
        response = narrator.narrate(base, pension_tax_message=message)

    assert turn == 2
    assert response.narration_mode == "claude_verified"
    assert response.answer.splitlines()[-1] == EXPECTED_CLOSING_NOTICE
