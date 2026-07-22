from backend.app.ingestion.kofia_fund_costs import (
    match_kofia_costs_to_etfs,
    normalize_etf_name,
)


def test_normalize_etf_name_keeps_post_suffix_hedge_and_synthetic_markers() -> None:
    kofia_name = (
        "삼성KODEX 미국30년국채타겟커버드콜증권상장지수투자신탁"
        "[채권혼합-파생형](합성 H)"
    )

    assert normalize_etf_name(kofia_name) == normalize_etf_name(
        "KODEX 미국30년국채타겟커버드콜(합성 H)"
    )


def test_match_kofia_costs_uses_only_unique_normalized_etf_names() -> None:
    report = {
        "rows": [
            {
                "normalized_etf_name": normalize_etf_name(
                    "삼성KODEX 검증주식증권상장지수투자신탁[주식형]"
                ),
                "ter_percent": "0.10",
                "brokerage_commission_percent": "0.0532",
                "standard_code": "K55105TEST01",
            }
        ]
    }

    matches = match_kofia_costs_to_etfs(
        report,
        etf_products=[
            {"isu_code": "123456", "isu_name": "KODEX 검증주식"},
            {"isu_code": "OTHER", "isu_name": "KODEX 검증"},
        ],
    )

    assert matches["123456"]["ter_percent"] == "0.10"
    assert matches["123456"]["brokerage_commission_percent"] == "0.0532"
    assert matches["123456"]["match_method"] == "unique_normalized_etf_name"


def test_match_kofia_costs_uses_documented_issuer_alias_standard_code() -> None:
    report = {
        "rows": [
            {
                "normalized_etf_name": normalize_etf_name(
                    "미래에셋TIGER원유선물특별자산상장지수투자신탁"
                    "(원유-파생형)(H)"
                ),
                "ter_percent": "0.75",
                "standard_code": "KR5225287949",
            }
        ]
    }

    matches = match_kofia_costs_to_etfs(
        report,
        etf_products=[
            {"isu_code": "130680", "isu_name": "TIGER 원유선물Enhanced(H)"},
        ],
    )

    assert matches["130680"]["ter_percent"] == "0.75"
    assert matches["130680"]["match_method"] == (
        "confirmed_issuer_alias_standard_code"
    )
    assert "miraeasset.com" in matches["130680"]["issuer_identity_source_url"]


def test_match_kofia_costs_uses_fsc_exact_name_standard_code() -> None:
    report = {
        "rows": [
            {
                "normalized_etf_name": "ASSETPLUSINDIA",
                "ter_percent": "1.26",
                "standard_code": "K55364ED4870",
            }
        ]
    }
    fsc_join = {
        "products": [
            {
                "isu_code": "0002C0",
                "match_status": "matched_exact_normalized_name",
                "fund": {"fund_standard_code": "K55364ED4870"},
            }
        ]
    }

    matches = match_kofia_costs_to_etfs(
        report,
        etf_products=[
            {"isu_code": "0002C0", "isu_name": "에셋플러스 인도일등기업포커스20액티브"},
        ],
        fsc_fund_join_report=fsc_join,
    )

    assert matches["0002C0"]["ter_percent"] == "1.26"
    assert matches["0002C0"]["match_method"] == (
        "fsc_exact_normalized_name_to_standard_code"
    )


def test_match_kofia_costs_uses_order_independent_name_only_with_kis_fee() -> None:
    report = {
        "rows": [
            {
                "fund_name": "미래에셋TIGER적격TDF2045증권상장지수투자신탁(주식혼합)",
                "normalized_etf_name": "TIGER적격TDF2045",
                "stated_fee_total_percent": "0.19",
                "ter_percent": "0.26",
                "standard_code": "K55301EH7354",
            }
        ]
    }

    matches = match_kofia_costs_to_etfs(
        report,
        etf_products=[{"isu_code": "0025N0", "isu_name": "TIGER TDF2045 적격"}],
        kis_stated_fee_by_code={"0025N0": "0.19"},
    )

    assert matches["0025N0"]["ter_percent"] == "0.26"
    assert matches["0025N0"]["match_method"] == (
        "unique_order_independent_name_and_kis_fee"
    )
