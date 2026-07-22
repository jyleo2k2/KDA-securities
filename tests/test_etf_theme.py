import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import (
    ChatIntent,
    ChatRequest,
    CompletedSurveyProfile,
    DataBoundary,
)
from backend.app.chat.query_planner import ThemeContentTopic, plan_question
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.engine import (
    AccountType,
    EducationalRiskProfile,
    classify_etf_theme_matches,
    classify_etf_themes,
    normalize_kis_holdings,
    select_theme_etf_candidates,
)
from backend.app.etf_component_repository import (
    EtfComponentHolding,
    EtfComponentSnapshot,
)
from backend.app.etf_product_description_repository import (
    EtfProductDescription,
    EtfProductDescriptionRepository,
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


class _UniverseWithProduct(_Universe):
    def __init__(self, product: dict[str, object]) -> None:
        self.products = [product]


class _UniverseWithProducts(_Universe):
    def __init__(self, products: list[dict[str, object]]) -> None:
        self.products = products


def _product_descriptions() -> EtfProductDescriptionRepository:
    return EtfProductDescriptionRepository(
        (
            EtfProductDescription(
                product_name="테스트 반도체 ETF",
                full_description="테스트용 반도체 ETF 전체 설명입니다.",
                one_line_description=(
                    "국내 반도체 기업에 분산 투자하는 테스트 ETF입니다."
                ),
                source_document_ids=("approved:test",),
                as_of_date=date(2026, 7, 18),
            ),
        )
    )


def test_catalog_has_exactly_twenty_one_themes() -> None:
    repository = _theme_repository()

    assert repository.catalog.catalog_version == "2026-07-22.1"
    assert (
        repository.catalog.content_status
        == "project_approved_service_interpretation"
    )
    assert repository.catalog.source_urls == EXPECTED_RESEARCH_SOURCE_URLS
    assert [theme.number for theme in repository.list()] == list(range(1, 22))
    assert len({theme.theme_id for theme in repository.list()}) == 21
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
    ) == 63
    assert all(
        company.source_url.startswith("https://")
        and company.theme_role
        and company.plain_description
        and company.representative_reason
        for theme in repository.list()
        for company in theme.representative_companies
    )
    assert repository.resolve("1번 테마의 특징은?").theme_id == "semiconductor"
    assert repository.resolve("AI 소프트웨어 ETF") is None
    assert repository.resolve("코리아밸류업") is None
    assert repository.resolve("ESG 책임투자") is None
    assert repository.resolve("20번 테마 구성종목은?").theme_id == "shipbuilding"
    assert repository.resolve("21번 채권 테마 ETF상품").theme_id == "bonds"


def test_default_product_policy_restricts_all_twenty_one_themes() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )

    restricted = {
        theme.theme_id
        for theme in repository.list()
        if repository.allowed_product_codes(theme.theme_id) is not None
    }

    assert len(restricted) == 21
    assert repository.product_policy is not None
    assert repository.product_policy.deferred_theme_ids == set()
    assert all(
        len(repository.allowed_product_codes(theme_id) or ()) >= 3
        for theme_id in restricted
    )
    assert repository.allowed_product_codes("gold_commodities") >= {
        "0072R0",
        "411060",
        "0172V0",
        "0189B0",
        "160580",
    }
    assert repository.allowed_product_codes("gold_commodities") == {
        "0072R0",
        "411060",
        "0172V0",
        "0189B0",
        "160580",
    }
    commodity_policy = repository.commodity_selection_policy("gold_commodities")
    assert commodity_policy is not None
    assert [slot.slot_id for slot in commodity_policy.slots] == [
        "gold",
        "silver",
        "copper",
    ]
    assert repository.allowed_product_codes("metaverse") >= {
        "400970",
        "401170",
        "401470",
    }
    assert repository.allowed_product_codes("energy_refining") >= {
        "117460",
        "139250",
        "474800",
    }


def test_product_policy_rejects_empty_ready_theme(tmp_path: Path) -> None:
    policy = json.loads(
        Path("data/reference/etf_theme_product_allowlist.json").read_text(
            encoding="utf-8"
        )
    )
    policy["restricted_themes"]["energy_refining"] = []
    policy_path = tmp_path / "invalid_policy.json"
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must contain at least 3 products"):
        EtfThemeRepository.from_local_cache(
            catalog_path=CATALOG_PATH,
            kis_cache_root=Path("tests/fixtures/no-kis-cache"),
            product_policy_path=policy_path,
        )


def test_remaining_themes_resolve_by_name() -> None:
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


def test_remaining_themes_classify_etf_text() -> None:
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
        isu_name="반도체 자동차 모빌리티 ETF",
    )
    matched = classify_etf_themes(
        repository.catalog,
        isu_name="반도체 자동차 모빌리티 ETF",
    )

    assert {"semiconductor", "automotive_mobility"} <= set(matched)
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


def test_candidate_engine_does_not_require_risk_profile_or_account() -> None:
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

    evaluation = select_theme_etf_candidates(**common)

    assert evaluation.account_type is None
    assert len(evaluation.candidates) == 1
    assert evaluation.candidates[0].account_type is None
    assert evaluation.candidates[0].top_holdings[0].component_name == "삼성전자"


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
        limit=3,
    )

    assert [candidate.isu_code for candidate in evaluation.candidates] == [
        "000002",
        "000001",
        "000003",
    ]
    assert any("거래대금 또는 총보수" in item for item in evaluation.limitations)


def test_candidate_allowlist_keeps_foreign_etf_without_component_snapshot() -> None:
    repository = _theme_repository()
    theme = repository.get("semiconductor")
    assert theme is not None
    allowed = _rankable_product(
        "381180",
        liquidity="2000000000",
        fee="0.45",
    )
    allowed["isu_name"] = "TIGER 미국필라델피아반도체나스닥"
    allowed["classification"]["region"] = "united_states"
    outside = _rankable_product(
        "0067Y0",
        liquidity="9000000000",
        fee="0.01",
    )
    outside["isu_name"] = "테스트 해외반도체 ETF"

    evaluation = select_theme_etf_candidates(
        catalog=repository.catalog,
        theme=theme,
        products=[outside, allowed],
        kis_products_by_code={},
        component_snapshot_date=None,
        limit=3,
        allowed_isu_codes=frozenset({"381180"}),
    )

    assert [candidate.isu_code for candidate in evaluation.candidates] == [
        "381180"
    ]
    assert evaluation.candidates[0].top_holdings == ()
    assert "theme_matched_from_research_allowlist" in (
        evaluation.candidates[0].reasons
    )


def test_candidate_engine_ignores_kis_holdings_for_foreign_equity() -> None:
    repository = _theme_repository()
    theme = repository.get("semiconductor")
    assert theme is not None
    product = _rankable_product("381180", liquidity="2000000000", fee="0.45")
    product["isu_name"] = "TIGER 미국필라델피아반도체나스닥"
    product["classification"]["region"] = "united_states"

    evaluation = select_theme_etf_candidates(
        catalog=repository.catalog,
        theme=theme,
        products=[product],
        kis_products_by_code={
            "381180": repository.kis_products_by_code["123456"],
        },
        component_snapshot_date=repository.component_snapshot_date,
        limit=3,
        allowed_isu_codes=frozenset({"381180"}),
    )

    candidate = evaluation.candidates[0]
    assert candidate.top_holdings == ()
    assert candidate.component_count == 0


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


def test_all_themes_route_natural_language_product_list_questions() -> None:
    repository = _theme_repository()

    for theme in repository.list():
        for question in (
            f"{theme.name} 테마 ETF상품 3개를 보여줘",
            f"{theme.name} 테마 ETF는 뭐가 있어?",
        ):
            plan = plan_question(
                question,
                default_max_results=5,
                theme_repository=repository,
            )
            assert plan.intent == ChatIntent.ETF_THEME
            assert plan.theme_id == theme.theme_id
            assert plan.requests_theme_candidates is True
            assert plan.requests_theme_holdings is False
            assert plan.max_results == 3


def test_all_themes_return_candidates_without_completed_survey() -> None:
    repository = _theme_repository()

    for theme in repository.list():
        product = _product()
        product["isu_name"] = f"{theme.name} ETF"
        service = ChatService(
            knowledge=LocalMarkdownKnowledgeRepository(),
            scenarios=LocalScenarioRepository(),
            theme_repository=repository,
            portfolio_universe_loader=lambda account_type, item=product: (
                _UniverseWithProduct(item)
            ),
        )

        response = service.ask(
            ChatRequest(message=f"{theme.name} 테마 ETF상품 3개를 보여줘")
        )

        assert response.data_mode == "theme_candidates", theme.theme_id
        assert response.sections[0].blocks, theme.theme_id
        assert response.conversation_context is not None
        assert response.conversation_context.survey_profile is None


def test_all_ready_themes_return_three_candidates_with_production_policy() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    assert repository.product_policy is not None
    products_by_code: dict[str, dict[str, object]] = {}
    for codes in repository.product_policy.allowed_codes_by_theme.values():
        for rank, code in enumerate(sorted(codes), start=1):
            products_by_code.setdefault(
                code,
                _rankable_product(
                    code,
                    liquidity=str(10_000_000_000 - rank),
                    fee="0.30",
                ),
            )

    def load_theme_products(codes: tuple[str, ...] | None):
        assert codes is not None
        return _UniverseWithProducts([products_by_code[code] for code in codes])

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        theme_product_universe_loader=load_theme_products,
    )
    for theme in repository.list():
        if theme.theme_id in repository.product_policy.deferred_theme_ids:
            continue

        response = service.ask(
            ChatRequest(message=f"{theme.name} 테마 ETF상품 3개를 보여줘")
        )

        assert response.data_mode == "theme_candidates", theme.theme_id
        assert len(response.sections[0].blocks) == 3, theme.theme_id
        assert "제시할 ETF 상품이 없습니다" not in response.answer


def test_chat_uses_research_allowlist_and_keeps_foreign_product_candidate() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    product = _rankable_product(
        "381180",
        liquidity="2000000000",
        fee="0.45",
    )
    product["isu_name"] = "TIGER 미국필라델피아반도체나스닥"
    product["classification"]["region"] = "united_states"
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda account_type: _UniverseWithProduct(
            product
        ),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 ETF상품 3개를 보여줘")
    )

    assert response.data_mode == "theme_candidates"
    assert [block.title for block in response.sections[0].blocks] == [
        "1. TIGER 미국필라델피아반도체나스닥"
    ]
    assert response.conversation_context.etf_theme.candidate_isu_codes == [
        "381180"
    ]
    assert "policy:theme_product_classification" in (
        response.sections[0].evidence_ids
    )
    assert all(
        "상품 범위는 공유 대화에 언급된 ETF" not in item
        for item in response.limitations
    )


def test_restricted_theme_uses_filtered_product_loader_without_history() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    product = _rankable_product(
        "381180",
        liquidity="2000000000",
        fee="0.45",
    )
    product["isu_name"] = "TIGER 미국필라델피아반도체나스닥"
    requested_codes: list[tuple[str, ...] | None] = []

    def load_theme_products(codes: tuple[str, ...] | None):
        requested_codes.append(codes)
        return _UniverseWithProduct(product)

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda _account_type: (_ for _ in ()).throw(
            AssertionError("theme cards must not load portfolio histories")
        ),
        theme_product_universe_loader=load_theme_products,
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 ETF상품 3개를 보여줘")
    )
    legacy_response = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda _account_type: _UniverseWithProduct(
            product
        ),
    ).ask(ChatRequest(message="반도체 테마 ETF상품 3개를 보여줘"))

    assert requested_codes == [
        tuple(sorted(repository.allowed_product_codes("semiconductor") or ()))
    ]
    assert response.data_mode == "theme_candidates"
    assert [block.title for block in response.sections[0].blocks] == [
        "1. TIGER 미국필라델피아반도체나스닥"
    ]
    assert response == legacy_response


def test_gold_theme_uses_filtered_product_loader() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    product = _rankable_product(
        "411060",
        liquidity="2000000000",
        fee="0.10",
    )
    product["isu_name"] = "ACE KRX금현물"
    requested_codes: list[tuple[str, ...] | None] = []

    def load_theme_products(codes: tuple[str, ...] | None):
        requested_codes.append(codes)
        return _UniverseWithProduct(product)

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda _account_type: (_ for _ in ()).throw(
            AssertionError("theme cards must not load portfolio histories")
        ),
        theme_product_universe_loader=load_theme_products,
    )

    response = service.ask(
        ChatRequest(message="금·원자재 테마 ETF상품 3개를 보여줘")
    )

    assert requested_codes == [
        tuple(sorted(repository.allowed_product_codes("gold_commodities") or ()))
    ]
    assert response.data_mode == "theme_candidates"
    assert [block.title for block in response.sections[0].blocks] == [
        "1. ACE KRX금현물",
        "2. 1Q 은액티브",
        "3. TIGER 구리실물",
    ]
    assert response.conversation_context.etf_theme.candidate_isu_codes == [
        "411060",
        "0172V0",
        "160580",
    ]
    assert [
        item.value
        for item in response.numeric_evidence
        if item.label.endswith("최근 일평균 거래량")
    ] == [Decimal("733000"), Decimal("122000"), Decimal("87000")]
    assert all(
        "최근 일평균 거래량" in block.text
        for block in response.sections[0].blocks
    )


def test_reviewed_theme_does_not_backfill_unclassified_product() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    product = _rankable_product(
        "999999",
        liquidity="2000000000",
        fee="0.10",
    )
    product["isu_name"] = "테스트 정유 ETF"
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda account_type: _UniverseWithProduct(
            product
        ),
    )

    response = service.ask(
        ChatRequest(message="에너지·정유 테마 ETF상품 3개를 보여줘")
    )

    assert response.data_mode == "theme_overview_only"
    assert "거래대금과 총보수를 확인할 수 있는" in response.answer
    assert all("테스트 정유 ETF" not in str(section) for section in response.sections)
    assert all("교집합" not in item for item in response.limitations)


def test_reviewed_gold_theme_uses_approved_policy_not_unclassified_product() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    product = _rankable_product(
        "999998",
        liquidity="2000000000",
        fee="0.10",
    )
    product["isu_name"] = "테스트 GOLD ETF"
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        portfolio_universe_loader=lambda account_type: _UniverseWithProduct(
            product
        ),
    )

    response = service.ask(
        ChatRequest(message="금·원자재 테마 ETF상품 3개를 보여줘")
    )

    assert response.data_mode == "theme_candidates"
    assert all("테스트 GOLD ETF" not in str(section) for section in response.sections)
    assert [block.title for block in response.sections[0].blocks] == [
        "1. ACE KRX금현물",
        "2. 1Q 은액티브",
        "3. TIGER 구리실물",
    ]


class _ForbiddenCommodityComponents:
    def latest_for(self, _isu_codes: list[str]) -> dict[str, EtfComponentSnapshot]:
        raise AssertionError("physical commodity follow-up must not query components")


def test_gold_theme_follow_up_returns_physical_exposure_not_components() -> None:
    repository = EtfThemeRepository.from_local_cache(
        catalog_path=CATALOG_PATH,
        kis_cache_root=Path("tests/fixtures/no-kis-cache"),
    )
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        component_snapshots=_ForbiddenCommodityComponents(),
    )
    candidate_response = service.ask(
        ChatRequest(message="금·원자재 테마 ETF상품 3개를 보여줘")
    )

    response = service.ask(
        ChatRequest(
            message="금·원자재 ETF구성종목 비중을 보여줘",
            conversation_context=candidate_response.conversation_context,
        )
    )

    assert response.data_mode == "theme_physical_commodity_exposure"
    assert [section.blocks[0].rows for section in response.sections] == [
        [["금 현물", "100%"]],
        [["은 현물", "100%"]],
        [["구리 실물", "100%"]],
    ]
    assert all(
        block.headers == ["실물가격 노출", "노출비중"]
        for section in response.sections
        for block in section.blocks
    )
    assert [item.value for item in response.numeric_evidence] == [
        Decimal("100"),
        Decimal("100"),
        Decimal("100"),
    ]
    assert "구성종목 TOP3" not in response.answer


class _ComponentSnapshots:
    def latest_for(self, isu_codes: list[str]) -> dict[str, EtfComponentSnapshot]:
        assert isu_codes == ["123456"]
        return {
            "123456": EtfComponentSnapshot(
                isu_code="123456",
                captured_at=datetime(2026, 7, 21, 3, tzinfo=UTC),
                holdings=(
                    EtfComponentHolding(
                        rank=1,
                        component_isu_code="005930",
                        component_name="삼성전자",
                        weight_percent=Decimal("25.5"),
                    ),
                    EtfComponentHolding(
                        rank=2,
                        component_isu_code="000660",
                        component_name="SK하이닉스",
                        weight_percent=Decimal("18.25"),
                    ),
                ),
                as_of_date=date(2026, 7, 21),
                source_kind="actual_portfolio",
                coverage_kind="published_top_n",
                weight_basis="fund_nav_percent",
                source_code="official_sol_etf",
                publisher="신한자산운용",
                source_locator="https://www.soletf.com/example",
            )
        }


class _PartialComponentSnapshots:
    def __init__(self) -> None:
        self.requested_codes: list[str] = []

    def latest_for(self, isu_codes: list[str]) -> dict[str, EtfComponentSnapshot]:
        self.requested_codes = list(isu_codes)
        snapshots: dict[str, EtfComponentSnapshot] = {}
        for code in isu_codes[:2]:
            snapshots[code] = EtfComponentSnapshot(
                isu_code=code,
                captured_at=datetime(2026, 7, 21, 3, tzinfo=UTC),
                holdings=(
                    EtfComponentHolding(
                        rank=1,
                        component_isu_code="005930",
                        component_name=f"구성종목 {code}",
                        weight_percent=Decimal("25.5"),
                    ),
                ),
                as_of_date=date(2026, 7, 21),
                source_kind="creation_basket",
                coverage_kind="creation_basket",
                weight_basis="basket_value_percent",
                source_code="official_tiger_etf",
                publisher="미래에셋자산운용",
                source_locator="https://www.tigeretf.com/example",
            )
        return snapshots


def test_theme_holdings_follow_up_uses_previous_candidate_codes() -> None:
    repository = _theme_repository()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=repository,
        component_snapshots=_ComponentSnapshots(),
        portfolio_universe_loader=lambda account_type: _Universe(),
    )
    candidate_response = service.ask(
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
    response = service.ask(
        ChatRequest(
            message="반도체 ETF구성종목 비중을 보여줘",
            conversation_context=candidate_response.conversation_context,
        )
    )

    assert response.intent == ChatIntent.ETF_THEME
    assert response.data_mode == "theme_component_holdings"
    assert any(
        source.evidence_id.startswith("official_sol_etf:components:123456:")
        for source in response.sources
    )
    assert {item.value for item in response.numeric_evidence} >= {
        Decimal("25.5"),
        Decimal("18.25"),
    }
    assert any(
        section.title.endswith("실제 보유종목 TOP3")
        for section in response.sections
    )
    assert response.sources[0].publisher == "신한자산운용"
    assert response.sources[0].locator == "https://www.soletf.com/example"
    assert all("테마 ETF상품" not in section.title for section in response.sections)
    assert all(section.content == "" for section in response.sections)
    assert all(
        block.headers == ["구성종목", "구성비중"]
        for section in response.sections
        for block in section.blocks
    )
    assert response.sections[0].blocks[0].rows == [
        ["삼성전자", "25.5%"],
        ["SK하이닉스", "18.25%"],
    ]
    assert "005930" not in str(response.sections)
    assert "000660" not in str(response.sections)


def test_first_theme_holdings_request_batches_ranked_candidate_codes() -> None:
    products = [
        _rankable_product("000001", liquidity="3000000000", fee="0.30"),
        _rankable_product("000002", liquidity="2000000000", fee="0.20"),
        _rankable_product("000003", liquidity="1000000000", fee="0.10"),
    ]
    snapshots = _PartialComponentSnapshots()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        component_snapshots=snapshots,
        portfolio_universe_loader=lambda _account_type: _UniverseWithProducts(
            products
        ),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 ETF 구성종목 TOP3를 보여줘")
    )

    assert snapshots.requested_codes == ["000001", "000002", "000003"]
    assert response.data_mode == "theme_component_holdings"
    assert [section.title for section in response.sections] == [
        "테스트 반도체 ETF 000001 구성 바스켓 TOP3",
        "테스트 반도체 ETF 000002 구성 바스켓 TOP3",
    ]
    assert response.conversation_context.etf_theme.candidate_isu_codes == [
        "000001",
        "000002",
        "000003",
    ]
    assert "ETF 2개의 공식 상위 구성정보" in response.answer


def test_theme_products_explain_trading_value_and_fee_per_etf() -> None:
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        product_descriptions=_product_descriptions(),
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
    assert product_section.content == ""
    assert len(response.sections) == 1
    assert len(product_section.blocks) == 1
    assert product_section.blocks[0].title == "1. 테스트 반도체 ETF"
    assert product_section.blocks[0].text == (
        "연간 수수료율(운용보수): 0.25%\n\n"
        "하루 평균 거래대금: 10억원\n\n"
        "상품 특징: 국내 반도체 기업에 분산 투자하는 테스트 ETF입니다."
    )
    assert all(section.title != "반도체 테마란?" for section in response.sections)
    assert "verified:etf_product_descriptions" in product_section.evidence_ids
    assert any(
        source.evidence_id == "verified:etf_product_descriptions"
        and source.data_boundary == DataBoundary.VERIFIED_KNOWLEDGE
        for source in response.sources
    )
    assert any(
        item.label == "테스트 반도체 ETF 일별 거래대금 중앙값"
        and item.value == Decimal("1000000000")
        and item.unit == "KRW"
        for item in response.numeric_evidence
    )


def test_theme_product_without_approved_description_uses_grounded_fallback() -> None:
    product = _product()
    product["implementation_metrics"]["benchmark_name"] = "테스트 반도체 지수"
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        portfolio_universe_loader=lambda account_type: _UniverseWithProduct(
            product
        ),
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

    text = response.sections[0].blocks[0].text
    assert "상품 설명 확인 필요" not in text
    assert "상품 특징: 테스트 반도체 지수를 기준으로" in text
    assert "삼성전자·SK하이닉스 등을 담아 반도체 분야에 투자합니다." in text


def test_theme_product_feature_omits_numeric_benchmark_claim() -> None:
    product = _product()
    product["implementation_metrics"]["benchmark_name"] = (
        "테스트 금융지수 15% 프리미엄"
    )
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        portfolio_universe_loader=lambda account_type: _UniverseWithProduct(
            product
        ),
    )

    response = service.ask(
        ChatRequest(message="반도체 테마 ETF상품 3개를 보여줘")
    )

    assert response.data_mode == "theme_candidates"
    assert "15%" not in response.sections[0].blocks[0].text


class _ProductFeatureGenerator:
    def __init__(self) -> None:
        self.received_codes: tuple[str, ...] = ()

    def generate(self, facts):
        self.received_codes = tuple(item.isu_code for item in facts)
        return {
            item.isu_code: "국내 반도체 제조사와 장비 기업을 함께 담습니다."
            for item in facts
        }


def test_theme_product_uses_validated_llm_feature_without_changing_card_shape() -> None:
    generator = _ProductFeatureGenerator()
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        product_feature_generator=generator,
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

    block = response.sections[0].blocks[0]
    assert generator.received_codes == ("123456",)
    assert block.title == "1. 테스트 반도체 ETF"
    assert "연간 수수료율(운용보수): 0.25%" in block.text
    assert "하루 평균 거래대금: 10억원" in block.text
    assert (
        "상품 특징: 국내 반도체 제조사와 장비 기업을 함께 담습니다."
        in block.text
    )
    assert "verified:etf_product_feature_evidence" in response.sections[0].evidence_ids


def test_theme_product_display_rounds_fee_and_trading_value_as_specified() -> None:
    product = _product()
    product["cost"] = {"kis_total_expense_ratio_percent": "0.305"}
    product["implementation_metrics"] = {
        "median_daily_trading_value_krw": "49079208237",
        "median_net_assets_krw": "100000000000",
        "median_abs_premium_discount_percent": "0.1",
        "kis_current_tracking_error_percent": "0.2",
    }
    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        product_descriptions=_product_descriptions(),
        portfolio_universe_loader=lambda account_type: _UniverseWithProduct(
            product
        ),
    )

    response = service.ask(
        ChatRequest(
            message="DC 반도체 테마 ETF는 뭐가 있어?",
            survey_profile=CompletedSurveyProfile(
                account_type=AccountType.DC,
                current_age=35,
                retirement_start_age=60,
                risk_profile=EducationalRiskProfile.ACTIVE,
                loss_tolerance_percent=Decimal("30"),
            ),
        )
    )

    text = response.sections[0].blocks[0].text
    assert "연간 수수료율(운용보수): 0.31%" in text
    assert "하루 평균 거래대금: 491억원" in text


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
        assert role_paragraph.startswith(
            f"테마에서의 역할: {company.theme_role} "
        )
        assert "때문입니다" not in role_paragraph
        assert role_paragraph.endswith("입니다.")
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
            role_paragraph, plain_paragraph = block.text.split("\n\n")
            assert role_paragraph.startswith(
                f"테마에서의 역할: {company.theme_role} "
            )
            assert "때문입니다" not in role_paragraph
            assert role_paragraph.endswith("입니다.")
            assert plain_paragraph == f"쉽게 말하면: {company.plain_description}"
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


def test_theme_top3_ignores_survey_profile_and_requested_account() -> None:
    loaded_accounts: list[AccountType] = []

    def load_universe(account_type: AccountType) -> _Universe:
        loaded_accounts.append(account_type)
        return _Universe()

    service = ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        theme_repository=_theme_repository(),
        portfolio_universe_loader=load_universe,
    )
    without_survey = service.ask(
        ChatRequest(message="IRP 반도체 ETF 상품 3개를 보여줘")
    )
    with_survey = service.ask(
        ChatRequest(
            message="공격투자형으로 반도체 ETF 상품 3개를 보여줘",
            survey_profile=CompletedSurveyProfile(
                account_type=AccountType.DC,
                current_age=35,
                retirement_start_age=60,
                risk_profile=EducationalRiskProfile.STABLE,
                loss_tolerance_percent=Decimal("10"),
            ),
        )
    )

    assert without_survey.data_mode == "theme_candidates"
    assert with_survey.data_mode == "theme_candidates"
    assert [block.title for block in without_survey.sections[0].blocks] == [
        block.title for block in with_survey.sections[0].blocks
    ]
    assert loaded_accounts == list(AccountType) * 2
    assert len(without_survey.sections[0].blocks) == 1
    assert without_survey.conversation_context is not None
    assert without_survey.conversation_context.account_type is None
    assert without_survey.conversation_context.survey_profile is None
    assert any(
        "정보성 비교 후보" in item for item in without_survey.limitations
    )
