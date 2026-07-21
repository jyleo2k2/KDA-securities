from datetime import date, timedelta
from decimal import Decimal

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import (
    ChatIntent,
    ChatRequest,
    CompletedSurveyProfile,
)
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import (
    AccountType,
    EducationalPortfolioInput,
    EducationalRiskProfile,
)
from backend.app.engine.macro_regime import (
    MACRO_REGIME_METRIC_IDS,
    MacroAnalogRegimeEvaluation,
    MacroRegimeMatch,
)
from backend.app.macro_evidence import MacroAnalogRegimeSnapshot


def _product(
    code: str, *, asset_class: str, strategy: str, bucket: str
) -> dict[str, object]:
    return {
        "isu_code": code,
        "isu_name": f"ETF {code}",
        "classification": {
            "asset_class": asset_class,
            "strategy": strategy,
            "region": "south_korea",
            "currency_hedge": "not_applicable",
            "classification_confidence": "high",
        },
        "account_eligibility": {
            "eligible": True,
            "allocation_bucket": bucket,
        },
        "cost": {"effective_total_cost_percent": "0.20"},
        "implementation_metrics": {
            "median_daily_trading_value_krw": 1_000_000_000,
            "median_net_assets_krw": 100_000_000_000,
            "median_abs_premium_discount_percent": "0.1",
            "kis_current_tracking_error_percent": "0.2",
            "tracking_error_proxy_percent": "0.3",
        },
        "observation_count": 756,
    }


def _history(multiplier: Decimal) -> dict[date, Decimal]:
    start = date(2025, 1, 1)
    value = Decimal("100")
    output = {start: value}
    for index in range(1, 91):
        daily = Decimal("0.001") * multiplier
        if index % 9 == 0:
            daily = Decimal("-0.004") * multiplier
        value *= Decimal("1") + daily
        output[start + timedelta(days=index)] = value
    return output


class Universe:
    as_of = date(2026, 7, 16)
    products = [
        _product(
            "EQ",
            asset_class="equity",
            strategy="broad_market",
            bucket="general_risky_70_cap",
        ),
        _product(
            "GOLD",
            asset_class="commodity",
            strategy="gold",
            bucket="general_risky_70_cap",
        ),
        _product(
            "BOND",
            asset_class="fixed_income",
            strategy="government_bond",
            bucket="full_allocation_eligible",
        ),
        _product(
            "CASH",
            asset_class="cash_equivalent",
            strategy="money_market",
            bucket="full_allocation_eligible",
        ),
    ]
    histories = {
        "EQ": _history(Decimal("2")),
        "GOLD": _history(Decimal("1.5")),
        "BOND": _history(Decimal("0.5")),
        "CASH": _history(Decimal("0.1")),
    }
    history_sources = {code: "test_total_return" for code in histories}


def _macro_outcome_history() -> dict[date, Decimal]:
    start = date(2024, 2, 1)
    return {
        start + timedelta(days=index): Decimal("100") + Decimal(index) / 10
        for index in range(368)
    }


class OutcomeUniverse(Universe):
    @staticmethod
    def load_total_return_histories(isu_codes):
        histories = {
            code: _macro_outcome_history() for code in isu_codes if code == "EQ"
        }
        return histories, {
            code: "kis_adjusted_close_plus_kind_cash_distribution" for code in histories
        }


class MacroRepository:
    @staticmethod
    def analog_regimes() -> MacroAnalogRegimeSnapshot:
        values = {metric_id: Decimal("1") for metric_id in MACRO_REGIME_METRIC_IDS}
        analysis = MacroAnalogRegimeEvaluation(
            engine_name="historical_macro_regime_similarity",
            engine_version="test",
            policy_version="test",
            current_period=date(2026, 6, 1),
            current_values=values,
            current_expanding_z_scores=values,
            metric_ids=list(MACRO_REGIME_METRIC_IDS),
            frequency="monthly",
            standardization="expanding_window_z_score",
            distance_metric="equal_weight_root_mean_square_distance",
            top_n=1,
            minimum_history_months=36,
            minimum_separation_months=12,
            excluded_recent_months=12,
            matches=[
                MacroRegimeMatch(
                    period=date(2024, 1, 1),
                    distance=Decimal("0.2500"),
                    values=values,
                    expanding_z_scores=values,
                )
            ],
            is_forecast=False,
            planning_return_input=False,
            allocation_weight_input=False,
            rebalancing_trigger_input=False,
            historical_outcomes_included=False,
            limitations=[],
        )
        return MacroAnalogRegimeSnapshot(
            as_of=date(2026, 7, 20),
            dataset_policy_version="test",
            period_start=date(2010, 1, 1),
            period_end=date(2026, 6, 1),
            complete_month_count=198,
            metrics=[],
            analysis=analysis,
        )


def _service() -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        portfolio_universe_loader=lambda account: Universe(),
    )


def test_chatbot_only_explains_structured_portfolio_engine_result() -> None:
    request = ChatRequest(
        message="교육용 포트폴리오 계획가정을 설명해줘",
        educational_portfolio=EducationalPortfolioInput(
            account_type=AccountType.DC,
            age=25,
            retirement_start_age=60,
            risk_profile=EducationalRiskProfile.RISK_NEUTRAL,
            loss_tolerance_percent=Decimal("20"),
        ),
    )

    response = _service().ask(request)

    assert response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert response.educational_portfolio_evaluation is not None
    evaluation = response.educational_portfolio_evaluation
    assert evaluation.planning_return.is_forecast is False
    assert evaluation.planning_return.historical_performance_used is False
    assert evaluation.portfolio_risk.historical_return_used_for_risk_only is True
    assert response.narration_mode == "deterministic"
    sections = {section.title: section.content for section in response.sections}
    assert list(sections) == ["위험중립형 투자전략", "장기 계획수익률"]
    assert "35년" in sections["위험중립형 투자전략"]
    assert "위험중립형 코어·위성 전략" in sections["위험중립형 투자전략"]
    assert "엔진 편입 후보" in sections["위험중립형 투자전략"]
    assert "새 납입금" in sections["위험중립형 투자전략"]
    assert "미래 예측값이 아니라" in sections["장기 계획수익률"]


def test_current_holdings_include_realized_macro_regime_evidence_card() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        portfolio_universe_loader=lambda account: OutcomeUniverse(),
        macro_evidence=MacroRepository(),
    )
    response = service.ask(
        ChatRequest(
            message="현재 보유 ETF 리밸런싱 가이드를 보여줘",
            educational_portfolio=EducationalPortfolioInput(
                account_type=AccountType.IRP,
                age=35,
                retirement_start_age=60,
                risk_profile=EducationalRiskProfile.RISK_NEUTRAL,
                loss_tolerance_percent=Decimal("20"),
                current_holdings=[{"isu_code": "EQ", "amount_krw": Decimal("1000000")}],
            ),
        )
    )

    assert response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert response.macro_regime_etf_outcomes is not None
    outcome = response.macro_regime_etf_outcomes.groups[0].etfs[0]
    assert outcome.isu_code == "EQ"
    assert [item.horizon_months for item in outcome.horizons] == [3, 6, 12]
    assert outcome.source is not None
    assert "KIND" in outcome.source.label


def test_direct_future_return_prediction_remains_blocked() -> None:
    response = _service().ask(ChatRequest(message="내년 연금 수익률을 예측해줘"))

    assert response.intent == ChatIntent.OUT_OF_SCOPE
    assert response.data_mode == "blocked"
    assert "미래 수익률" in response.answer


def _completed_survey(
    risk_profile: EducationalRiskProfile = EducationalRiskProfile.RISK_NEUTRAL,
) -> CompletedSurveyProfile:
    return CompletedSurveyProfile(
        account_type=AccountType.IRP,
        current_age=25,
        retirement_start_age=60,
        risk_profile=risk_profile,
        loss_tolerance_percent=(
            Decimal("40")
            if risk_profile == EducationalRiskProfile.AGGRESSIVE
            else Decimal("20")
        ),
    )


def test_completed_survey_profile_calls_portfolio_engine() -> None:
    response = _service().ask(
        ChatRequest(
            message="내 투자스타일의 연금 운용 전략과 수익률을 알려줘",
            survey_profile=_completed_survey(),
        )
    )

    assert response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert response.data_mode == "engine_educational_planning"
    assert response.educational_portfolio_evaluation is not None
    risk_section = next(
        section.content
        for section in response.sections
        if section.title == "장기 계획수익률"
    )
    assert "보수 약" in risk_section
    assert "기준 약" in risk_section
    displayed_returns = [
        item.value
        for item in response.numeric_evidence
        if item.label in {"보수 계획수익률", "기준 계획수익률"}
    ]
    assert len(displayed_returns) == 2
    assert all(value.as_tuple().exponent == -1 for value in displayed_returns)
    assert [item.label for item in response.numeric_evidence[:4]] == [
        "일반 위험자산 목표비중",
        "보수 계획수익률",
        "기준 계획수익률",
        "수령 개시까지 운용기간",
    ]


def test_chat_does_not_collect_age_when_survey_is_missing() -> None:
    response = _service().ask(ChatRequest(message="내 연금 운용 전략을 알려줘"))

    assert response.data_mode == "survey_required"
    assert "프로필에서 설문을 마친 뒤" in response.answer
    assert "현재 나이" not in response.answer
    assert "수령 개시 나이" not in response.answer


def test_custom_portfolio_card_uses_completed_survey_age_and_profile() -> None:
    response = _service().ask(
        ChatRequest(
            message="내 상황에 맞는 연금저축전략을 알려줘.",
            survey_profile=_completed_survey(),
        )
    )

    assert response.data_mode == "engine_educational_planning"
    assert response.educational_portfolio_evaluation is not None
    evaluated = response.educational_portfolio_evaluation.evaluated_input
    assert evaluated.age == 25
    assert evaluated.risk_profile == EducationalRiskProfile.RISK_NEUTRAL


def test_custom_portfolio_card_requests_survey_when_profile_is_missing() -> None:
    response = _service().ask(
        ChatRequest(message="내 상황에 맞는 연금저축전략을 알려줘.")
    )

    assert response.data_mode == "survey_required"
    assert response.educational_portfolio_evaluation is None


def test_chat_explains_available_risk_profiles_before_selection() -> None:
    messages = (
        "투자성향에 대해 뭐가 있어?",
        "투자 스타일 종류를 알려줘",
        "어떤 투자 성향을 선택할 수 있어?",
        "투자성향을 잘 모르겠어",
    )

    for message in messages:
        response = _service().ask(ChatRequest(message=message))

        assert response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
        assert response.data_mode == "risk_profile_selection"
        assert response.educational_portfolio_evaluation is None
        assert response.numeric_evidence == []
        assert "원하는 유형을 하나 선택" in response.answer
        for label in (
            "안정형",
            "안정추구형",
            "위험중립형",
            "적극투자형",
            "공격투자형",
        ):
            assert label in response.answer
            assert label in response.sections[0].content


def test_chat_explains_portfolio_strategy_for_all_five_risk_profiles() -> None:
    response = _service().ask(
        ChatRequest(
            message=(
                "안정형, 안정추구형, 위험중립형, 적극투자형, 공격투자형 각각 "
                "어떤 전략으로 포트폴리오를 설계하고 투자하는지 알려줘"
            )
        )
    )

    assert response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert response.data_mode == "risk_profile_portfolio_guide"
    assert response.educational_portfolio_evaluation is None
    assert response.numeric_evidence == []
    assert "다섯 투자성향" in response.answer
    assert [section.title for section in response.sections] == [
        "안정형 연금운용 전략",
        "안정추구형 연금운용 전략",
        "위험중립형 연금운용 전략",
        "적극투자형 연금운용 전략",
        "공격투자형 연금운용 전략",
        "공통 실행 원칙",
    ]
    expected_strategies = (
        "자본보전 중심 전략",
        "방어적 분산 전략",
        "코어·위성 전략",
        "성장 코어·위성 전략",
        "바벨형 성장·전술 전략",
    )
    for section, strategy in zip(
        response.sections[:5], expected_strategies, strict=True
    ):
        assert strategy in section.content
        assert "설계:" in section.content
        assert "운용:" in section.content
    common = response.sections[-1].content
    assert "비용" in common
    assert "추적오차" in common
    assert "새 납입금" in common
    assert "분기" in common
    assert "매년" in common
    assert "DC·IRP" in response.limitations[0]
    assert "70%" in response.limitations[0]
    assert "자동" in response.limitations[-1]


def test_style_by_style_portfolio_question_does_not_require_completed_survey() -> None:
    response = _service().ask(
        ChatRequest(message="5가지 투자스타일별 연금운용 포트폴리오 전략을 비교해줘")
    )

    assert response.data_mode == "risk_profile_portfolio_guide"
    assert response.educational_portfolio_evaluation is None


def test_chat_explains_age_band_and_risk_style_portfolio_framework() -> None:
    response = _service().ask(
        ChatRequest(message="20대부터 50대까지 투자스타일별 ETF 운용전략을 알려줘")
    )

    assert response.intent == ChatIntent.EDUCATIONAL_PORTFOLIO
    assert response.data_mode == "age_style_portfolio_guide"
    assert response.educational_portfolio_evaluation is None
    assert response.numeric_evidence == []
    assert "연령대의 운용 초점과 투자성향별 설계를 함께 적용" in response.answer
    assert [section.title for section in response.sections] == [
        "연령대별 운용 초점",
        "투자스타일별 포트폴리오 설계",
    ]
    for age_band in ("20대", "30대", "40대", "50대"):
        assert age_band in response.sections[0].content
    for profile in (
        "안정형",
        "안정추구형",
        "위험중립형",
        "적극투자형",
        "공격투자형",
    ):
        assert profile in response.sections[1].content
    assert "DC·IRP" in response.limitations[0]
    assert "70%" in response.limitations[0]
    assert "만 55~60세" in response.sections[0].content
    assert "분기" in response.sections[1].content
    assert "매년" in response.sections[1].content


def test_chat_applies_user_selected_retirement_start_age_to_engine() -> None:
    response = _service().ask(
        ChatRequest(
            message="연금 수령은 58세로 선택하고 위험중립형 ETF 포트폴리오를 보여줘",
            survey_profile=_completed_survey(),
        )
    )

    assert response.data_mode == "engine_educational_planning"
    assert response.educational_portfolio_evaluation is not None
    evaluation = response.educational_portfolio_evaluation
    assert evaluation.retirement_start_age == 58
    assert evaluation.planning_horizon_years == 33
    assert evaluation.planning_return.retirement_start_age == 58
    assert evaluation.planning_return.is_forecast is False
    assert response.conversation_context is not None
    assert response.conversation_context.survey_profile is not None
    assert response.conversation_context.survey_profile.retirement_start_age == 58
    assert "분기마다" in response.sections[0].content
    assert "매년" in response.sections[0].content


def test_chat_rejects_retirement_start_age_outside_supported_range() -> None:
    response = _service().ask(
        ChatRequest(
            message="연금 수령은 61세로 하고 ETF 포트폴리오를 보여줘",
            survey_profile=_completed_survey(),
        )
    )

    assert response.data_mode == "retirement_age_selection"
    assert response.educational_portfolio_evaluation is None
    assert "만 55세부터 60세" in response.answer


def test_completed_survey_is_kept_for_follow_up_strategy_question() -> None:
    first = _service().ask(
        ChatRequest(
            message="내 연금 운용 전략을 알려줘",
            survey_profile=_completed_survey(),
        )
    )

    second = _service().ask(
        ChatRequest(
            message="그럼 계획수익률도 설명해줘",
            conversation_context=first.conversation_context,
        )
    )

    assert second.data_mode == "engine_educational_planning"
    assert second.educational_portfolio_evaluation is not None
    evaluated = second.educational_portfolio_evaluation.evaluated_input
    assert evaluated.account_type == AccountType.IRP
    assert evaluated.age == 25
    assert evaluated.retirement_start_age == 60


def test_each_allowed_chat_style_builds_its_own_etf_portfolio() -> None:
    cases = (
        (
            "안정형으로 보여줘",
            EducationalRiskProfile.STABLE,
            "안정형 투자전략",
            "capital_preservation_core",
        ),
        (
            "안정 추구형으로 보여줘",
            EducationalRiskProfile.STABLE_SEEKING,
            "안정추구형 투자전략",
            "defensive_diversified_core",
        ),
        (
            "위험중립형으로 보여줘",
            EducationalRiskProfile.RISK_NEUTRAL,
            "위험중립형 투자전략",
            "balanced_core_satellite",
        ),
        (
            "적극투자형으로 보여줘",
            EducationalRiskProfile.ACTIVE,
            "적극투자형 투자전략",
            "growth_core_satellite",
        ),
        (
            "공격 투자형으로 보여줘",
            EducationalRiskProfile.AGGRESSIVE,
            "공격투자형 투자전략",
            "barbell_growth_tactical",
        ),
    )
    allocations: set[tuple[tuple[str, Decimal], ...]] = set()

    for message, expected_profile, expected_title, expected_strategy in cases:
        response = _service().ask(
            ChatRequest(
                message=message,
                survey_profile=_completed_survey(EducationalRiskProfile.AGGRESSIVE),
            )
        )

        assert response.data_mode == "engine_educational_planning"
        assert response.educational_portfolio_evaluation is not None
        evaluation = response.educational_portfolio_evaluation
        assert evaluation.evaluated_input.risk_profile == expected_profile
        assert evaluation.strategy_label == expected_strategy
        assert evaluation.target_sleeves
        assert evaluation.candidates
        allocations.add(
            tuple(
                (target.sleeve, target.target_percent)
                for target in evaluation.target_sleeves
            )
        )
        assert response.sections[0].title == expected_title
        assert "목표 포트폴리오" in response.sections[0].content
        assert "엔진 편입 후보" in response.sections[0].content
        assert response.conversation_context is not None
        assert response.conversation_context.selected_risk_profile == expected_profile

    assert len(allocations) == len(cases)


def test_chat_rejects_style_above_completed_survey_result() -> None:
    response = _service().ask(
        ChatRequest(
            message="공격투자형 ETF 포트폴리오를 보여줘",
            survey_profile=_completed_survey(),
        )
    )

    assert response.data_mode == "profile_guardrail"
    assert response.educational_portfolio_evaluation is None
    assert "위험중립형" in response.answer
    assert "공격투자형" in response.answer
    assert "위험해서 제안하지 않아요" in response.answer
    assert response.conversation_context is not None
    assert (
        response.conversation_context.selected_risk_profile
        == EducationalRiskProfile.RISK_NEUTRAL
    )


def test_selected_chat_style_is_kept_for_follow_up_question() -> None:
    first = _service().ask(
        ChatRequest(
            message="안정추구형으로 포트폴리오를 설계해줘",
            survey_profile=_completed_survey(EducationalRiskProfile.AGGRESSIVE),
        )
    )

    second = _service().ask(
        ChatRequest(
            message="그 전략의 계획수익률도 설명해줘",
            conversation_context=first.conversation_context,
        )
    )

    assert second.educational_portfolio_evaluation is not None
    assert (
        second.educational_portfolio_evaluation.evaluated_input.risk_profile
        == EducationalRiskProfile.STABLE_SEEKING
    )
    assert second.sections[0].title == "안정추구형 투자전략"


def test_mvp_demo_profile_builds_separate_irp_and_pension_savings_plans() -> None:
    survey = CompletedSurveyProfile(
        account_type=AccountType.IRP,
        account_types=[AccountType.IRP, AccountType.PENSION_SAVINGS],
        current_age=30,
        retirement_start_age=55,
        risk_profile=EducationalRiskProfile.RISK_NEUTRAL,
        loss_tolerance_percent=Decimal("10"),
    )

    response = _service().ask(
        ChatRequest(
            message="내 ETF 투자 포트폴리오와 예상 수익률을 알려줘",
            survey_profile=survey,
        )
    )

    assert response.data_mode == "engine_multi_account_planning"
    assert len(response.educational_portfolio_evaluations) == 2
    evaluations = {
        evaluation.evaluated_input.account_type: evaluation
        for evaluation in response.educational_portfolio_evaluations
    }
    assert set(evaluations) == {AccountType.IRP, AccountType.PENSION_SAVINGS}
    for evaluation in evaluations.values():
        assert evaluation.evaluated_input.age == 30
        assert evaluation.evaluated_input.retirement_start_age == 55
        assert (
            evaluation.evaluated_input.risk_profile
            == EducationalRiskProfile.RISK_NEUTRAL
        )
        assert evaluation.evaluated_input.loss_tolerance_percent == Decimal("10")
        assert evaluation.planning_horizon_years == 25
        assert evaluation.candidates
        assert evaluation.planning_return.conservative_planning_return_percent
        assert evaluation.planning_return.base_planning_return_percent

    section_titles = [section.title for section in response.sections]
    assert section_titles == [
        "적용한 MVP 설문 조건",
        "IRP · 위험중립형 투자전략",
        "IRP · 장기 계획수익률",
        "연금저축펀드 · 위험중립형 투자전략",
        "연금저축펀드 · 장기 계획수익률",
    ]
    assert "현재 나이 30세" in response.sections[0].content
    assert "연금수령 개시 55세" in response.sections[0].content
    assert "손실감내율 약 10%" in response.sections[0].content
    assert all(
        "미래 예측값이 아니라" in section.content
        for section in response.sections
        if section.title.endswith("장기 계획수익률")
    )
    assert response.conversation_context is not None
    assert response.conversation_context.survey_profile == survey


def test_missing_return_master_names_each_unavailable_account() -> None:
    def missing(account_type: AccountType):
        raise FileNotFoundError(
            f"no cost-return master for account {account_type.value}"
        )

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        portfolio_universe_loader=missing,
    )
    survey = CompletedSurveyProfile(
        account_type=AccountType.IRP,
        account_types=[AccountType.IRP, AccountType.PENSION_SAVINGS],
        current_age=30,
        retirement_start_age=55,
        risk_profile=EducationalRiskProfile.RISK_NEUTRAL,
        loss_tolerance_percent=Decimal("10"),
    )

    response = service.ask(
        ChatRequest(message="내 ETF 포트폴리오를 알려줘", survey_profile=survey)
    )

    assert response.data_mode == "unavailable"
    assert "IRP 계좌용 ETF 비용·수익률 기준 데이터" in response.answer
    assert "연금저축펀드 계좌용 ETF 비용·수익률 기준 데이터" in response.answer
    assert "0원" not in response.answer
