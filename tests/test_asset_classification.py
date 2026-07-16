import pytest

from backend.app.engine.asset_classification import (
    EtfClassificationInput,
    classify_etf,
)


def _classify(
    name: str,
    benchmark: str,
    kis_industry: str = "ETF(실물복제/수익증권)",
) -> dict[str, object]:
    return classify_etf(
        EtfClassificationInput(
            isu_code="000000",
            isu_name=name,
            benchmark_name=benchmark,
            kis_index_name=benchmark,
            kis_industry_name=kis_industry,
        )
    )


@pytest.mark.parametrize(
    ("name", "benchmark", "asset_class", "subtype", "region"),
    [
        (
            "RISE 국고채3년",
            "KTB index(시장가격)",
            "fixed_income",
            "government_bond",
            "south_korea",
        ),
        (
            "TIGER 원유선물Enhanced(H)",
            "S&P GSCI Crude Oil Enhanced Index ER",
            "commodity",
            "oil",
            "global",
        ),
        (
            "ACE 미국부동산리츠(합성 H)",
            "Dow Jones U.S. Real Estate Index",
            "real_estate",
            "reit",
            "united_states",
        ),
        (
            "KODEX 미국S&P500",
            "S&P 500",
            "equity",
            "equity_unspecified",
            "united_states",
        ),
        (
            "TIGER TDF2045 적격",
            "S&P Korea Target Date 2045 Global Index",
            "multi_asset",
            "target_date",
            "global",
        ),
        (
            "KODEX 유럽탄소배출권선물ICE(H)",
            "ICE EUA Carbon Futures Index",
            "commodity",
            "carbon_allowance",
            "global",
        ),
        (
            "TIGER CD1년금리액티브(합성)",
            "KIS CD 1Y 총수익지수",
            "cash_equivalent",
            "money_market",
            "south_korea",
        ),
        (
            "ACE MSCI필리핀(합성)",
            "MSCI Philippines IMI Index",
            "equity",
            "equity_unspecified",
            "philippines",
        ),
    ],
)
def test_classifies_primary_asset_and_region(
    name: str,
    benchmark: str,
    asset_class: str,
    subtype: str,
    region: str,
) -> None:
    result = _classify(name, benchmark)
    assert result["asset_class"] == asset_class
    assert result["sub_asset_class"] == subtype
    assert result["region"] == region


def test_uses_kis_replication_and_active_fields() -> None:
    synthetic = _classify(
        "ACE 미국부동산리츠(합성 H)",
        "Dow Jones U.S. Real Estate Index",
        "ETF(합성복제/수익증권)",
    )
    active = _classify(
        "KIWOOM 미국30년국채혼합액티브(H)",
        "Bloomberg Blended US Long Treasury Bond Index",
        "ETF(Active/수익증권)",
    )

    assert synthetic["replication_method"] == "synthetic"
    assert synthetic["currency_hedge"] == "hedged"
    assert active["management_style"] == "active"
    assert active["replication_method"] == "active_discretionary"
    assert active["asset_class"] == "multi_asset"

    inferred = _classify("SAMPLE 국내주식", "KOSPI200", "ETF")
    assert inferred["replication_method"] == "physical"
    assert inferred["replication_confidence"] == "medium"


def test_natural_gas_value_chain_remains_equity() -> None:
    result = _classify(
        "RISE 미국천연가스밸류체인",
        "Solactive US Natural Gas Value Chain Index PR",
    )
    assert result["asset_class"] == "equity"
    assert result["region"] == "united_states"
    assert result["management_style"] == "passive"


def test_components_corroborate_domestic_equity_and_raise_region_confidence() -> None:
    result = classify_etf(
        EtfClassificationInput(
            isu_code="000000",
            isu_name="SAMPLE 국내대표주",
            benchmark_name="SAMPLE INDEX",
            kis_index_name="SAMPLE INDEX",
            kis_industry_name="ETF(실물복제/수익증권)",
            component_holdings=(
                ("005930", "삼성전자", 60.0),
                ("000660", "SK하이닉스", 40.0),
            ),
        )
    )

    assert result["asset_class"] == "equity"
    assert result["component_profile"]["asset_class_signal"] == "corroborates"
    assert result["component_profile"]["region_signal"] == "corroborates"
    assert result["dimension_confidence"]["region"] == "high"


def test_components_do_not_override_explicit_derivative_underlying() -> None:
    result = classify_etf(
        EtfClassificationInput(
            isu_code="000000",
            isu_name="SAMPLE 미국장기국채선물(H)",
            benchmark_name="U.S. TREASURY BOND INDEX",
            kis_index_name="U.S. TREASURY BOND INDEX",
            kis_industry_name="ETF(실물복제/수익증권)",
            component_holdings=(
                ("005930", "삼성전자", 60.0),
                ("000660", "SK하이닉스", 40.0),
            ),
        )
    )

    assert result["asset_class"] == "fixed_income"
    assert result["sub_asset_class"] == "government_bond"
    assert result["component_profile"]["asset_class_signal"] == "conflicts"
    assert "kis_components_conflict_with_primary_asset_class" in result["reason_codes"]


def test_disclosure_override_resolves_multi_asset_currency_hedge() -> None:
    result = classify_etf(
        EtfClassificationInput(
            isu_code="435530",
            isu_name="KIWOOM TDF2030액티브 적격",
            benchmark_name="Dow Jones Target 2030 Index",
            kis_index_name="Dow Jones Target 2030 Index",
            kis_industry_name="ETF(Active/수익증권)",
            disclosure_currency_hedge="unhedged",
            disclosure_confidence="high",
        )
    )

    assert result["currency_hedge"] == "unhedged"
    assert result["currency_hedge_confidence"] == "high"
    assert result["decision_reasons"]["currency_hedge"] == (
        "issuer_disclosure_override"
    )
