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
    classify_etf_theme_matches,
    classify_etf_themes,
    normalize_kis_holdings,
    select_theme_etf_candidates,
)
from backend.app.etf_theme_repository import EtfThemeRepository

CATALOG_PATH = Path("data/reference/etf_theme_catalog.json")
EXPECTED_RESEARCH_SOURCE_URLS = (
    "https://chatgpt.com/share/6a5dbc76-9c4c-83ee-9b7f-7729b384befe",
    "https://chatgpt.com/share/6a5dbc89-8868-83ee-8d75-2f68d6e1bffc",
    "https://chatgpt.com/share/6a5d9df1-9eb0-83e8-a285-0d2aec036054",
    "https://chatgpt.com/share/6a5dbc9e-9d78-83e8-bb9c-5c2007c15d35",
    "https://chatgpt.com/share/6a5dbca9-74bc-83e8-9f83-7f105074a7be",
)


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


def _rankable_product(
    code: str,
    *,
    liquidity: str,
    fee: str | None,
    net_assets: str = "100000000000",
) -> dict[str, object]:
    product = _product()
    product["isu_code"] = code
    product["isu_name"] = f"테스트 반도체 ETF {code}"
    product["cost"] = (
        {"kis_total_expense_ratio_percent": fee} if fee is not None else {}
    )
    product["implementation_metrics"] = {
        "median_daily_trading_value_krw": liquidity,
        "median_net_assets_krw": net_assets,
        "median_abs_premium_discount_percent": "0.1",
        "kis_current_tracking_error_percent": "0.2",
    }
    return product


class _Universe:
    products = [_product()]
    histories = {}
    history_sources = {}
    as_of = date(2026, 7, 18)
    source_path = Path("data/cache/returns/dc_etf_cost_return_test.json")


def test_catalog_has_exactly_twenty_three_themes() -> None:
    repository = _theme_repository()

    assert repository.catalog.catalog_version == "2026-07-20.4"
    assert (
        repository.catalog.content_status
        == "project_approved_service_interpretation"
    )
    assert repository.catalog.source_urls == EXPECTED_RESEARCH_SOURCE_URLS
    assert [theme.number for theme in repository.list()] == list(range(1, 24))
    assert len({theme.theme_id for theme in repository.list()}) == 23
    assert all(theme.plain_summary for theme in repository.list())
    assert all(theme.exposure_segments for theme in repository.list())
    assert all(len(theme.performance_drivers) == 3 for theme in repository.list())
    forbidden_claims = ("수익률을 보장", "반드시 상승", "오를 것입니다", "수익이 확정")
    for theme in repository.list():
        for driver in theme.performance_drivers:
            label, separator, explanation = driver.partition(":")
            assert separator == ":"
            assert label.strip()
            assert len(explanation.strip()) >= 35
            assert not any(claim in driver for claim in forbidden_claims)
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

    matches = classify_etf_theme_matches(
        repository.catalog,
        isu_name="AI 반도체 모빌리티 ETF",
    )
    matched = classify_etf_themes(
        repository.catalog,
        isu_name="AI 반도체 모빌리티 ETF",
    )

    assert {"ai_software", "semiconductor", "automotive_mobility"} <= set(matched)
    assert matched == tuple(match.theme_id for match in matches)
    assert all(match.is_ambiguous for match in matches)
    assert all("isu_name" in match.matched_sources for match in matches)
    assert all(match.matched_terms for match in matches)


def test_theme_classification_evidence_identifies_kis_source_field() -> None:
    repository = _theme_repository()

    matches = classify_etf_theme_matches(
        repository.catalog,
        isu_name="테스트 ETF",
        kis_index_name="KRX 반도체 지수",
        kis_industry_name="전기전자",
    )

    semiconductor = next(
        match for match in matches if match.theme_id == "semiconductor"
    )
    assert semiconductor.matched_sources == ("kis_index_name",)
    assert "반도체" in semiconductor.matched_terms


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


def test_candidate_engine_ranks_liquidity_first_then_lower_fee() -> None:
    repository = _theme_repository()
    theme = repository.get("semiconductor")
    assert theme is not None

    evaluation = select_theme_etf_candidates(
        catalog=repository.catalog,
        theme=theme,
        products=[
            _rankable_product("000001", liquidity="2000000000", fee="0.90"),
            _rankable_product("000002", liquidity="2000000000", fee="0.10"),
            _rankable_product("000003", liquidity="1500000000", fee="0.01"),
            _rankable_product("000004", liquidity="9000000000", fee=None),
        ],
        kis_products_by_code={},
        component_snapshot_date=date(2026, 7, 18),
        request=EducationalPortfolioInput(
            account_type=AccountType.DC,
            age=35,
            retirement_start_age=60,
            risk_profile=EducationalRiskProfile.ACTIVE,
            loss_tolerance_percent=Decimal("30"),
        ),
        limit=3,
    )

    assert [candidate.isu_code for candidate in evaluation.candidates] == [
        "000002",
        "000001",
        "000003",
    ]
    assert any("거래대금 또는 총보수" in item for item in evaluation.limitations)


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


def test_all_themes_route_five_content_question_types() -> None:
    repository = _theme_repository()

    for theme in repository.list():
        cases = {
            f"{theme.name} 테마가 뭐야?": ThemeContentTopic.OVERVIEW,
            (
                f"{theme.name} 테마 대표 기업은 뭐가 있어?"
            ): ThemeContentTopic.REPRESENTATIVE_COMPANIES,
            (
                f"{theme.name} 대표 테마기업은 뭐야?"
            ): ThemeContentTopic.REPRESENTATIVE_COMPANIES,
            (
                f"{theme.name} 테마에 투자할 때 고려할 점은 뭐야?"
            ): ThemeContentTopic.INVESTMENT_CONSIDERATIONS,
            (
                f"{theme.name} 테마 ETF에 투자할 때 장단점을 알려줘"
            ): ThemeContentTopic.INVESTMENT_CONSIDERATIONS,
            (
                f"{theme.name} 테마 성과에 영향을 주는 요인은 뭐야?"
            ): ThemeContentTopic.PERFORMANCE_DRIVERS,
            (
                f"{theme.name} 테마의 고유 위험은 뭐야?"
            ): ThemeContentTopic.RISKS,
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


def test_query_planner_routes_theme_product_button_to_three_candidates() -> None:
    plan = plan_question(
        "조선 테마 ETF상품 3개를 보여줘",
        theme_repository=_theme_repository(),
    )

    assert plan.intent == ChatIntent.ETF_THEME
    assert plan.theme_id == "shipbuilding"
    assert plan.requests_theme_candidates is True
    assert plan.max_results == 3


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


def test_theme_products_explain_trading_value_and_fee_per_etf() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        portfolio_universe_loader=lambda account_type: _Universe(),
    )
    response = service.ask(
        ChatRequest(
            message="DC 반도체 테마 ETF상품 3개를 보여줘",
            survey_profile=CompletedSurveyProfile(
                account_type=AccountType.DC,
                current_age=35,
                retirement_start_age=60,
                risk_profile=EducationalRiskProfile.ACTIVE,
                loss_tolerance_percent=Decimal("30"),
            ),
        )
    )

    product_section = next(
        section
        for section in response.sections
        if section.title == "반도체 테마 ETF상품"
    )
    assert "일별 거래대금 중앙값이 높은 순서" in product_section.content
    assert "총보수가 낮은 상품" in product_section.content
    assert product_section.blocks[0].headers == [
        "계좌",
        "ETF",
        "종목코드",
        "일별 거래대금 중앙값",
        "총보수",
    ]
    assert product_section.blocks[0].rows == [
        ["DC형", "테스트 반도체 ETF", "123456", "1,000,000,000원", "0.25%"]
    ]
    assert product_section.blocks[1].title == "DC형 1. 테스트 반도체 ETF"
    assert "거래대금 중앙값" in product_section.blocks[1].text
    assert "총보수는 0.25%" in product_section.blocks[1].text
    assert any(
        item.label == "테스트 반도체 ETF 일별 거래대금 중앙값"
        and item.value == Decimal("1000000000")
        and item.unit == "KRW"
        for item in response.numeric_evidence
    )


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
    assert [item.follow_up_id for item in response.suggested_follow_ups] == [
        "theme_representative_companies",
        "theme_pros_cons",
        "theme_products",
    ]
    assert response.suggested_follow_ups[0].label == "테마 대표기업"
    assert response.suggested_follow_ups[0].message == (
        "반도체 테마 대표기업은 뭐야?"
    )
    assert all(
        item.label != "성과 관찰요인" for item in response.suggested_follow_ups
    )
    assert response.suggested_follow_ups[1].label == "테마 장단점"
    assert response.suggested_follow_ups[1].message == (
        "반도체 테마 ETF에 투자할 때 장단점을 알려줘"
    )
    assert response.suggested_follow_ups[-1].label == "테마 ETF상품"
    assert response.suggested_follow_ups[-1].message == (
        "반도체 테마 ETF상품 3개를 보여줘"
    )
    assert all(
        plan_question(item.message, theme_repository=_theme_repository()).intent
        == ChatIntent.ETF_THEME
        for item in response.suggested_follow_ups
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
    assert all(
        "테마에서의 역할:" in block.text
        and "쉽게 말하면:" in block.text
        and "대표 사례로 보는 이유:" not in block.text
        and block.text.count("\n\n") == 1
        for block in response.sections[0].blocks
    )
    theme = _theme_repository().get("semiconductor")
    assert theme is not None
    for block, company in zip(
        response.sections[0].blocks,
        theme.representative_companies,
        strict=True,
    ):
        role_paragraph, plain_paragraph = block.text.split("\n\n")
        assert role_paragraph == (
            f"테마에서의 역할: {company.theme_role} "
            f"{company.representative_reason}"
        )
        assert plain_paragraph == f"쉽게 말하면: {company.plain_description}"
    assert len(response.sections[0].evidence_ids) == 3
    company_source_count = sum(
        source.evidence_id.startswith("company:") for source in response.sources
    )
    assert company_source_count == 3
    assert any("실제 편입종목이나 매수 추천" in item for item in response.limitations)


def test_chat_explains_three_benefits_and_three_risks_for_beginners() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 ETF에 투자할 때 장단점을 알려줘")
    )

    assert response.data_mode == "theme_investment_considerations"
    assert response.answer == (
        "반도체 테마 ETF에 투자할 때의 이점 3개와 위험 3개를 쉽게 정리했습니다."
    )
    assert response.sections[0].title == "반도체 테마 ETF 장단점"
    assert [block.title for block in response.sections[0].blocks] == [
        "투자할 때의 이점 3가지",
        "주의할 위험 3가지",
    ]
    assert [len(block.items) for block in response.sections[0].blocks] == [3, 3]


def test_all_theme_overviews_offer_three_by_three_pros_cons_follow_up() -> None:
    repository = _theme_repository()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
    )

    for theme in repository.list():
        response = service.ask(ChatRequest(message=f"{theme.name} 테마가 뭐야?"))
        pros_cons = next(
            item
            for item in response.suggested_follow_ups
            if item.follow_up_id == "theme_pros_cons"
        )
        assert pros_cons.label == "테마 장단점"
        assert pros_cons.message == (
            f"{theme.name} 테마 ETF에 투자할 때 장단점을 알려줘"
        )
        details = service.ask(ChatRequest(message=pros_cons.message))
        assert details.data_mode == "theme_investment_considerations"
        assert [block.title for block in details.sections[0].blocks] == [
            "투자할 때의 이점 3가지",
            "주의할 위험 3가지",
        ]
        assert [len(block.items) for block in details.sections[0].blocks] == [3, 3]


def test_all_theme_overviews_offer_three_representative_companies() -> None:
    repository = _theme_repository()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
    )

    for theme in repository.list():
        overview = service.ask(ChatRequest(message=f"{theme.name} 테마가 뭐야?"))
        follow_up = next(
            item
            for item in overview.suggested_follow_ups
            if item.follow_up_id == "theme_representative_companies"
        )
        assert follow_up.label == "테마 대표기업"
        assert follow_up.message == f"{theme.name} 테마 대표기업은 뭐야?"
        assert all(
            item.label != "성과 관찰요인"
            for item in overview.suggested_follow_ups
        )

        details = service.ask(ChatRequest(message=follow_up.message))
        assert details.data_mode == "theme_representative_companies"
        assert len(details.sections[0].blocks) == 3
        for block, company in zip(
            details.sections[0].blocks,
            theme.representative_companies,
            strict=True,
        ):
            assert block.text == (
                f"테마에서의 역할: {company.theme_role} "
                f"{company.representative_reason}\n\n"
                f"쉽게 말하면: {company.plain_description}"
            )
        assert sum(
            source.evidence_id.startswith(f"company:{theme.theme_id}:")
            for source in details.sources
        ) == 3


def test_chat_separates_performance_drivers_from_future_predictions() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 성과에 영향을 주는 요인은 뭐야?")
    )

    assert response.data_mode == "theme_performance_drivers"
    assert response.sections[0].blocks[0].title == "성과를 평가할 관찰 요인 3가지"
    assert len(response.sections[0].blocks[0].items) == 3
    assert all(":" in item for item in response.sections[0].blocks[0].items)
    assert "각각이 중요한 이유" in response.answer
    assert any("수익률을 예측하지 않습니다" in item for item in response.limitations)


def test_all_theme_performance_answers_explain_why_each_driver_matters() -> None:
    repository = _theme_repository()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
    )

    for theme in repository.list():
        response = service.ask(
            ChatRequest(message=f"{theme.name} 테마 성과에 영향을 주는 요인은 뭐야?")
        )
        items = response.sections[0].blocks[0].items
        assert len(items) == 3
        for item in items:
            label, separator, explanation = item.partition(":")
            assert separator == ":"
            assert label.strip()
            assert len(explanation.strip()) >= 35


def test_chat_answers_theme_risks_without_repeating_benefits() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
    )

    response = service.ask(ChatRequest(message="반도체 테마의 고유 위험은 뭐야?"))

    assert response.data_mode == "theme_risks"
    assert [block.title for block in response.sections[0].blocks] == [
        "주의할 위험 3가지"
    ]
    assert len(response.sections[0].blocks[0].items) == 3


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
