from backend.app.chat.models import ChatRequest
from backend.app.engine import EducationalRiskProfile
from tests.test_chat_educational_portfolio import _completed_survey, _service


def test_selected_conservative_profile_is_not_described_as_survey_result() -> None:
    response = _service().ask(
        ChatRequest(
            message="안정형 ETF 포트폴리오를 보여줘",
            survey_profile=_completed_survey(EducationalRiskProfile.AGGRESSIVE),
        )
    )

    assert response.educational_portfolio_evaluation is not None
    assert (
        response.educational_portfolio_evaluation.evaluated_input.risk_profile
        == EducationalRiskProfile.STABLE
    )
    assert response.answer.startswith(
        "이번 포트폴리오에 적용한 운용 성향은 안정형입니다."
    )
    assert "설문 결과는 안정형" not in response.answer
