from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import (
    ChatIntent,
    ChatRequest,
    CompletedSurveyProfile,
)
from backend.app.chat.query_planner import ThemeContentTopic, plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import (
    AccountType,
    EducationalPortfolioInput,
    EducationalRiskProfile,
    classify_etf_themes,
    normalize_kis_holdings,
    select_theme_etf_candidates,
)
from backend.app.etf_theme_repository import EtfThemeRepository

CATALOG_PATH = Path("data/reference/etf_theme_catalog.json")


def _theme_repository() -> EtfThemeRepository:
    base = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    return EtfThemeRepository(
        catalog=base.catalog,
        catalog_path=CATALOG_PATH,
        component_snapshot_date=date(2026, 7, 18),
        kis_products_by_code={
            "123456": {
                "isu_code": "123456",
                "price": {"etf_rprs_bstp_kor_isnm": "KRX 반도체 지수"},
                "components": [
                    {
                        "stck_shrn_iscd": "005930",
                        "hts_kor_isnm": "삼성전자",
                        "etf_cnfg_issu_rlim": "25.5",
                    },
                    {
                        "stck_shrn_iscd": "000660",
                        "hts_kor_isnm": "SK하이닉스",
                        "etf_cnfg_issu_rlim": "18.25",
                    },
                ],
            }
        },
    )


def _product() -> dict[str, object]:
    return {
        "isu_code": "123456",
        "isu_name": "테스트 반도체 ETF",
        "classification": {
            "asset_class": "equity",
            "strategy": "sector_or_theme",
            "region": "south_korea",
        },
        "account_eligibility": {
            "eligible": True,
            "allocation_bucket": "general_risky_70_cap",
        },
        "cost": {"kis_total_expense_ratio_percent": "0.25"},
        "implementation_metrics": {
            "median_daily_trading_value_krw": "1000000000",
            "median_net_assets_krw": "100000000000",
            "median_abs_premium_discount_percent": "0.1",
            "kis_current_tracking_error_percent": "0.2",
        },
        "observation_count": 756,
    }


class _Universe:
    products = [_product()]
    histories = {}
    history_sources = {}
    as_of = date(2026, 7, 18)
    source_path = Path("data/cache/returns/dc_etf_cost_return_test.json")


def test_catalog_has_exactly_twenty_three_themes() -> None:
    repository = _theme_repository()

    assert [theme.number for theme in repository.list()] == list(range(1, 24))
    assert len({theme.theme_id for theme in repository.list()}) == 23
    assert all(theme.plain_summary for theme in repository.list())
    assert all(theme.exposure_segments for theme in repository.list())
    assert all(theme.performance_drivers for theme in repository.list())
    assert all(theme.one_line_analogy for theme in repository.list())
    assert all(
        len(theme.representative_companies) == 3 for theme in repository.list()
    )
    assert sum(
        len(theme.representative_companies) for theme in repository.list()
    ) == 69
    assert all(
        company.source_url.startswith("https://")
        and company.theme_role
        and company.plain_description
        and company.representative_reason
        for theme in repository.list()
        for company in theme.representative_companies
    )
    assert repository.resolve("2번 테마의 특징은?").theme_id == "semiconductor"
    assert repository.resolve("AI 소프트웨어 ETF").theme_id == "ai_software"
    assert repository.resolve("23번 테마 구성종목은?").theme_id == "shipbuilding"


def test_themes_nine_through_twenty_three_resolve_by_name() -> None:
    repository = _theme_repository()
    cases = {
        "정유 ETF": "energy_refining",
        "K콘텐츠 게임 ETF": "media_entertainment_gaming",
        "원전과 전력기기": "nuclear_power_grid",
        "리츠 부동산": "reit_real_estate",
        "휴머노이드 로봇": "robotics",
        "은행 금융주": "bank_finance",
        "방산 우주": "defense_space",
        "K푸드 소비재": "consumer_food",
        "금 ETF": "gold_commodities",
        "코리아밸류업": "korea_value_up",
        "ESG 책임투자": "esg",
        "철강 소재": "steel_materials",
        "양자컴퓨팅": "quantum_computing",
        "메타버스": "metaverse",
        "조선기자재": "shipbuilding",
    }

    assert {
        question: repository.resolve(question).theme_id
        for question in cases
    } == cases
    assert repository.resolve("연금 ETF 운용 원리") is None


def test_themes_nine_through_twenty_three_classify_etf_text() -> None:
    repository = _theme_repository()
    cases = {
        "OIL & GAS 정유": "energy_refining",
        "KPOP GAME": "media_entertainment_gaming",
        "NUCLEAR 전력망": "nuclear_power_grid",
        "GLOBAL REITS": "reit_real_estate",
        "HUMANOID ROBOTICS": "robotics",
        "은행 FINANCIAL": "bank_finance",
        "SPACE DEFENSE": "defense_space",
        "K-FOOD 생활소비재": "consumer_food",
        "GOLD COMMODITY": "gold_commodities",
        "KOREA VALUE-UP": "korea_value_up",
        "ESG SUSTAINABLE": "esg",
        "STEEL MATERIALS": "steel_materials",
        "QUANTUM 양자암호": "quantum_computing",
        "METAVERSE XR": "metaverse",
        "SHIPBUILDING LNG선": "shipbuilding",
    }

    for text, expected in cases.items():
        assert expected in classify_etf_themes(repository.catalog, isu_name=text)

    assert "gold_commodities" not in classify_etf_themes(
        repository.catalog,
        isu_name="은행 금융 ETF",
    )


def test_theme_classification_can_be_many_to_many() -> None:
    repository = _theme_repository()

    matched = classify_etf_themes(
        repository.catalog,
        isu_name="AI 반도체 모빌리티 ETF",
    )

    assert {"ai_software", "semiconductor", "automotive_mobility"} <= set(matched)


def test_kis_component_weights_are_preserved_and_sorted() -> None:
    holdings = normalize_kis_holdings(
        [
            {
                "stck_shrn_iscd": "1",
                "hts_kor_isnm": "작은 종목",
                "etf_cnfg_issu_rlim": "3.2",
            },
            {
                "stck_shrn_iscd": "2",
                "hts_kor_isnm": "큰 종목",
                "etf_cnfg_issu_rlim": "11.75",
            },
        ]
    )

    assert [holding.component_name for holding in holdings] == ["큰 종목", "작은 종목"]
    assert holdings[0].weight_percent == Decimal("11.75")


def test_candidate_engine_applies_risk_profile_sleeve() -> None:
    repository = _theme_repository()
    theme = repository.get("semiconductor")
    assert theme is not None
    common = {
        "catalog": repository.catalog,
        "theme": theme,
        "products": [_product()],
        "kis_products_by_code": repository.kis_products_by_code,
        "component_snapshot_date": repository.component_snapshot_date,
        "limit": 3,
    }

    stable = select_theme_etf_candidates(
        **common,
        request=EducationalPortfolioInput(
            account_type=AccountType.DC,
            age=35,
            retirement_start_age=60,
            risk_profile=EducationalRiskProfile.STABLE,
            loss_tolerance_percent=Decimal("10"),
        ),
    )
    active = select_theme_etf_candidates(
        **common,
        request=EducationalPortfolioInput(
            account_type=AccountType.DC,
            age=35,
            retirement_start_age=60,
            risk_profile=EducationalRiskProfile.ACTIVE,
            loss_tolerance_percent=Decimal("30"),
        ),
    )

    assert stable.candidates == ()
    assert len(active.candidates) == 1
    assert active.candidates[0].top_holdings[0].component_name == "삼성전자"


def test_query_planner_routes_theme_and_holding_request() -> None:
    plan = plan_question(
        "IRP 반도체 ETF 구성종목 비중을 세 개 보여줘",
        theme_repository=_theme_repository(),
    )

    assert plan.intent == ChatIntent.ETF_THEME
    assert plan.theme_id == "semiconductor"
    assert plan.account_types == (AccountType.IRP,)
    assert plan.max_results == 3
    assert plan.requests_theme_candidates is True
    assert plan.requests_theme_holdings is True


def test_all_themes_route_three_content_question_types() -> None:
    repository = _theme_repository()

    for theme in repository.list():
        cases = {
            f"{theme.name} 테마가 뭐야?": ThemeContentTopic.OVERVIEW,
            (
                f"{theme.name} 테마 대표 기업은 뭐가 있어?"
            ): ThemeContentTopic.REPRESENTATIVE_COMPANIES,
            (
                f"{theme.name} 테마에 투자할 때 고려할 점은 뭐야?"
            ): ThemeContentTopic.INVESTMENT_CONSIDERATIONS,
        }
        for question, expected_topic in cases.items():
            plan = plan_question(question, theme_repository=repository)
            assert plan.intent == ChatIntent.ETF_THEME
            assert plan.theme_id == theme.theme_id
            assert plan.theme_content_topic == expected_topic
            assert plan.requests_theme_candidates is False


def test_etf_representative_holding_wording_keeps_kis_flow() -> None:
    plan = plan_question(
        "반도체 ETF 대표 종목을 보여줘",
        theme_repository=_theme_repository(),
    )

    assert plan.theme_content_topic == ThemeContentTopic.OVERVIEW
    assert plan.requests_theme_candidates is True
    assert plan.requests_theme_holdings is True


def test_query_planner_keeps_plain_etf_explanation_out_of_candidate_flow() -> None:
    plan = plan_question(
        "반도체 ETF가 뭐야?",
        theme_repository=_theme_repository(),
    )

    assert plan.intent == ChatIntent.ETF_THEME
    assert plan.theme_id == "semiconductor"
    assert plan.requests_theme_candidates is False
    assert plan.requests_theme_holdings is False
    assert plan.theme_content_topic == ThemeContentTopic.OVERVIEW


def test_query_planner_routes_new_shipbuilding_theme() -> None:
    plan = plan_question(
        "IRP 조선 ETF 구성종목 비중을 보여줘",
        theme_repository=_theme_repository(),
    )

    assert plan.intent == ChatIntent.ETF_THEME
    assert plan.theme_id == "shipbuilding"
    assert plan.requests_theme_holdings is True


def test_chat_response_links_kis_holding_weights_to_numeric_evidence() -> None:
    repository = _theme_repository()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda account_type: _Universe(),
    )
    response = service.ask(
        ChatRequest(
            message="DC 반도체 ETF 구성종목 비중을 보여줘",
            survey_profile=CompletedSurveyProfile(
                account_type=AccountType.DC,
                current_age=35,
                retirement_start_age=60,
                risk_profile=EducationalRiskProfile.ACTIVE,
                loss_tolerance_percent=Decimal("30"),
            ),
        )
    )

    assert response.intent == ChatIntent.ETF_THEME
    assert response.data_mode == "theme_candidates"
    assert any(
        source.evidence_id == "kis:components:123456"
        for source in response.sources
    )
    assert {item.value for item in response.numeric_evidence} >= {
        Decimal("25.5"),
        Decimal("18.25"),
    }
    assert any(section.title.endswith("주요 구성종목") for section in response.sections)


def test_chat_overview_only_explains_theme_and_analogy() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
    )

    response = service.ask(ChatRequest(message="반도체 테마가 뭐야?"))

    assert response.data_mode == "theme_overview"
    assert len(response.sections) == 1
    assert [block.title for block in response.sections[0].blocks] == [
        "분류상 정의",
        "어떤 기업·분야를 담나",
        "한 줄 비유",
    ]
    assert response.sections[0].blocks[-1].text == (
        "디지털 산업에 필요한 쌀과 두뇌 부품에 투자하는 ETF입니다."
    )


def test_chat_introduces_exactly_three_representative_companies() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 대표 기업은 뭐가 있어?")
    )

    assert response.data_mode == "theme_representative_companies"
    assert len(response.sections) == 1
    assert [block.title for block in response.sections[0].blocks] == [
        "Samsung Electronics",
        "NVIDIA",
        "TSMC",
    ]
    assert len(response.sections[0].evidence_ids) == 3
    company_source_count = sum(
        source.evidence_id.startswith("company:") for source in response.sources
    )
    assert company_source_count == 3
    assert any("실제 편입종목이나 매수 추천" in item for item in response.limitations)


def test_chat_separates_three_benefits_and_three_risks() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마에 투자할 때 고려할 점은 뭐야?")
    )

    assert response.data_mode == "theme_investment_considerations"
    assert [block.title for block in response.sections[0].blocks] == [
        "기대할 수 있는 점 3가지",
        "주의할 위험 3가지",
    ]
    assert [len(block.items) for block in response.sections[0].blocks] == [3, 3]


def test_chat_uses_requested_safer_profile_for_theme_guardrail() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        portfolio_universe_loader=lambda account_type: _Universe(),
    )
    response = service.ask(
        ChatRequest(
            message="안정형으로 반도체 ETF 후보를 보여줘",
            survey_profile=CompletedSurveyProfile(
                account_type=AccountType.DC,
                current_age=35,
                retirement_start_age=60,
                risk_profile=EducationalRiskProfile.ACTIVE,
                loss_tolerance_percent=Decimal("30"),
            ),
        )
    )

    assert response.intent == ChatIntent.ETF_THEME
    assert response.data_mode == "theme_overview_only"
    assert not any("비교 후보" in section.title for section in response.sections)
