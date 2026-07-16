import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EtfClassificationInput:
    isu_code: str
    isu_name: str
    benchmark_name: str
    kis_index_name: str
    kis_industry_name: str
    fsc_fund_type: str | None = None
    fsc_coarse_asset_class: str | None = None
    kis_currency_code: str = ""
    component_holdings: tuple[tuple[str, str, float], ...] = ()
    disclosure_currency_hedge: str | None = None
    disclosure_confidence: str | None = None


def _has(text: str, *tokens: str) -> bool:
    return any(token.upper() in text for token in tokens)


def _asset_class(text: str) -> tuple[str, str, str]:
    if _has(
        text,
        "TDF",
        "TARGET DATE",
        "혼합",
        "자산배분",
        "밸런스",
        "BALANCED",
        "BLENDED",
        "주식채권",
    ):
        subtype = "target_date" if _has(text, "TDF", "TARGET DATE") else "balanced"
        return "multi_asset", subtype, "explicit_multi_asset_keyword"
    if _has(text, "리츠", "REIT", "REAL ESTATE", "부동산"):
        return "real_estate", "reit", "explicit_real_estate_keyword"
    if _has(
        text,
        "KOFR",
        "SOFR",
        "CD금리",
        "CD1년금리",
        "CD 1Y",
        "CD91일",
        "머니마켓",
        "MONEY MARKET",
    ):
        return "cash_equivalent", "money_market", "explicit_cash_rate_keyword"
    if _has(
        text,
        "달러선물",
        "엔선물",
        "유로선물",
        "USD/KRW",
        "KRW/USD",
        "FX FUTURES",
    ):
        return "currency", "currency_futures", "explicit_currency_keyword"

    commodity_chain = _has(text, "밸류체인", "생산기업", "MINERS", "EQUITY")
    commodity_direct = _has(
        text,
        "GSCI",
        "원유선물",
        "골드선물",
        "금선물",
        "은선물",
        "구리선물",
        "콩선물",
        "농산물선물",
        "금현물",
        "국제금",
        "CRUDE OIL INDEX",
        "GOLD INDEX",
        "SILVER INDEX",
        "COPPER INDEX",
        "SOYBEANS INDEX",
        "AGRICULTURE INDEX",
        "PRECIOUS METALS INDEX",
        "탄소배출권선물",
        "CARBON FUTURES",
    )
    if commodity_direct and not commodity_chain:
        if _has(text, "CARBON", "탄소배출권"):
            subtype = "carbon_allowance"
        elif _has(text, "CRUDE", "원유"):
            subtype = "oil"
        elif _has(text, "SILVER", "은선물"):
            subtype = "silver"
        elif _has(text, "COPPER", "구리"):
            subtype = "industrial_metals"
        elif _has(text, "AGRICULTURE", "SOYBEANS", "농산물", "콩선물"):
            subtype = "agriculture"
        elif _has(text, "PRECIOUS", "금은"):
            subtype = "precious_metals"
        else:
            subtype = "gold"
        return "commodity", subtype, "explicit_commodity_underlying"

    if _has(
        text,
        "국채",
        "국고채",
        "통안채",
        "회사채",
        "은행채",
        "금융채",
        "특수은행채",
        "채권",
        "TREASURY",
        "T-BOND",
        "T-NOTE",
        "KTB INDEX",
        "KOBI",
        "CREDIT",
        "HIGH YIELD",
        "IBOXX",
        "MSB ",
    ):
        if _has(text, "회사채", "은행채", "금융채", "특수은행채", "CREDIT"):
            subtype = "corporate_bond"
        elif _has(text, "HIGH YIELD", "하이일드"):
            subtype = "high_yield_bond"
        elif _has(text, "단기", "통안채", "0-5 YEAR", "MSB "):
            subtype = "short_term_bond"
        elif _has(text, "국채", "국고채", "TREASURY", "T-BOND", "KTB INDEX"):
            subtype = "government_bond"
        else:
            subtype = "aggregate_bond"
        return "fixed_income", subtype, "explicit_fixed_income_keyword"
    if _has(text, "VIX", "VOLATILITY INDEX", "변동성지수"):
        return "alternative", "volatility", "explicit_volatility_keyword"
    return "equity", "equity_unspecified", "equity_by_exclusion"


def _region(text: str, asset_class: str) -> tuple[str, str]:
    if asset_class in {"commodity", "alternative", "currency"}:
        return "global", "underlying_not_single_country"
    if _has(text, "TDF", "TARGET DATE", "ACWI", "글로벌", "WORLD"):
        return "global", "explicit_global_keyword"
    if _has(text, "MSCI EAFE", "선진국"):
        return "developed_markets", "explicit_developed_market_keyword"
    if _has(text, "MSCI EM", "신흥국", "EMERGING"):
        return "emerging_markets", "explicit_emerging_market_keyword"
    if _has(text, "미국", "S&P", "NASDAQ", "DOW JONES", "RUSSELL", "U.S."):
        return "united_states", "explicit_us_keyword"
    if _has(text, "중국", "차이나", "CSI ", "CHINA", "HSCEI", "HANG SENG"):
        return "china", "explicit_china_keyword"
    if _has(text, "일본", "TOPIX", "NIKKEI"):
        return "japan", "explicit_japan_keyword"
    if _has(text, "인도", "NIFTY"):
        return "india", "explicit_india_keyword"
    if _has(text, "유럽", "EURO STOXX", "STOXX EUROPE"):
        return "europe", "explicit_europe_keyword"
    if _has(text, "베트남", "VIETNAM"):
        return "vietnam", "explicit_vietnam_keyword"
    if _has(text, "인도네시아", "INDONESIA"):
        return "indonesia", "explicit_indonesia_keyword"
    if _has(text, "라틴", "LATIN"):
        return "latin_america", "explicit_latin_america_keyword"
    if _has(text, "필리핀", "PHILIPPINES"):
        return "philippines", "explicit_philippines_keyword"
    if _has(text, "러시아", "RUSSIA"):
        return "russia", "explicit_russia_keyword"
    if _has(text, "멕시코", "MEXICO"):
        return "mexico", "explicit_mexico_keyword"
    if asset_class == "real_estate" and _has(text, "ASIA", "아시아"):
        return "asia_pacific", "explicit_asia_keyword"
    return "south_korea", "domestic_by_absence_of_foreign_marker"


def _strategy(text: str, asset_class: str, subtype: str) -> str:
    if _has(text, "TDF", "TARGET DATE"):
        return "target_date"
    if _has(text, "커버드콜", "COVERED CALL"):
        return "covered_call"
    if _has(text, "인버스", "INVERSE"):
        return "inverse"
    if _has(text, "레버리지", "2X"):
        return "leveraged"
    if _has(text, "만기매칭", "존속기한", "TARGET MATURITY"):
        return "target_maturity"
    if asset_class == "cash_equivalent":
        return "money_market"
    if _has(text, "고배당", "배당", "DIVIDEND"):
        return "dividend"
    if _has(text, "가치", "VALUE", "퀄리티", "QUALITY", "모멘텀", "저변동"):
        return "factor"
    if asset_class == "fixed_income":
        return subtype
    if asset_class in {"commodity", "real_estate", "currency", "alternative"}:
        return subtype
    if _has(
        text,
        "KOSPI200",
        "코스피 200",
        "S&P 500",
        "NASDAQ 100",
        "MSCI ACWI",
        "MSCI EAFE",
        "CSI 300",
        "TOPIX",
        "NIFTY 50",
    ):
        return "broad_market"
    return "sector_or_theme"


def _component_profile(
    holdings: tuple[tuple[str, str, float], ...],
    primary_asset_class: str,
    primary_region: str,
) -> dict[str, object]:
    if not holdings:
        return {
            "status": "not_available",
            "holding_count": 0,
            "reported_weight_percent": 0.0,
            "asset_class_weights_percent": {},
            "region_weights_percent": {},
            "dominant_asset_class": None,
            "dominant_asset_class_share_percent": None,
            "asset_class_signal": "not_available",
            "region_signal": "not_available",
        }

    asset_weights: dict[str, float] = {}
    region_weights: dict[str, float] = {}
    reported_weight = 0.0
    for _, name, raw_weight in holdings:
        weight = max(float(raw_weight), 0.0)
        if weight == 0:
            continue
        reported_weight += weight
        component_asset, _, _ = _asset_class(name.upper())
        component_region, _ = _region(name.upper(), component_asset)
        asset_weights[component_asset] = (
            asset_weights.get(component_asset, 0.0) + weight
        )
        region_weights[component_region] = (
            region_weights.get(component_region, 0.0) + weight
        )

    classified_weight = sum(asset_weights.values())
    if classified_weight == 0:
        return {
            "status": "insufficient",
            "holding_count": len(holdings),
            "reported_weight_percent": round(reported_weight, 4),
            "asset_class_weights_percent": {},
            "region_weights_percent": {},
            "dominant_asset_class": None,
            "dominant_asset_class_share_percent": None,
            "asset_class_signal": "insufficient",
            "region_signal": "insufficient",
        }

    dominant_asset, dominant_weight = max(
        asset_weights.items(), key=lambda item: item[1]
    )
    dominant_region, dominant_region_weight = max(
        region_weights.items(), key=lambda item: item[1]
    )
    dominant_share = dominant_weight / classified_weight * 100
    dominant_region_share = dominant_region_weight / classified_weight * 100
    material = reported_weight >= 50 and dominant_share >= 70
    asset_signal = "insufficient"
    if material:
        asset_signal = (
            "corroborates" if dominant_asset == primary_asset_class else "conflicts"
        )
    region_signal = "insufficient"
    if reported_weight >= 50 and dominant_region_share >= 70:
        region_signal = (
            "corroborates" if dominant_region == primary_region else "conflicts"
        )
    return {
        "status": "available",
        "holding_count": len(holdings),
        "reported_weight_percent": round(reported_weight, 4),
        "asset_class_weights_percent": {
            key: round(value, 4) for key, value in sorted(asset_weights.items())
        },
        "region_weights_percent": {
            key: round(value, 4) for key, value in sorted(region_weights.items())
        },
        "dominant_asset_class": dominant_asset,
        "dominant_asset_class_share_percent": round(dominant_share, 4),
        "asset_class_signal": asset_signal,
        "dominant_region": dominant_region,
        "dominant_region_share_percent": round(dominant_region_share, 4),
        "region_signal": region_signal,
    }


def _fsc_signal(asset_class: str, coarse_asset_class: str | None) -> str:
    if not coarse_asset_class:
        return "not_available"
    compatible = {
        "equity": {"equity"},
        "fixed_income": {"fixed_income"},
        "multi_asset": {"mixed_asset", "fund_of_funds"},
        "real_estate": {"real_estate"},
        "commodity": {"real_asset"},
        "cash_equivalent": {"cash_equivalent", "fixed_income"},
    }
    return (
        "corroborates"
        if coarse_asset_class in compatible.get(asset_class, set())
        else "conflicts"
    )


def classify_etf(source: EtfClassificationInput) -> dict[str, object]:
    text = " ".join(
        (
            source.isu_name,
            source.benchmark_name,
            source.kis_index_name,
            source.kis_industry_name,
            source.fsc_fund_type or "",
        )
    ).upper()
    asset_class, subtype, asset_reason = _asset_class(text)
    region, region_reason = _region(text, asset_class)
    component_profile = _component_profile(
        source.component_holdings,
        asset_class,
        region,
    )
    fsc_signal = _fsc_signal(asset_class, source.fsc_coarse_asset_class)

    kis_industry = source.kis_industry_name.upper()
    if _has(kis_industry, "ACTIVE"):
        management_style = "active"
        management_confidence = "high"
        management_reason = "kis_explicit_active_category"
    elif _has(source.isu_name.upper(), "ACTIVE", "액티브"):
        management_style = "active"
        management_confidence = "high"
        management_reason = "krx_name_explicit_active"
    elif _has(kis_industry, "실물복제", "합성복제"):
        management_style = "passive"
        management_confidence = "high"
        management_reason = "kis_non_active_replication_category"
    else:
        management_style = "passive"
        management_confidence = "medium"
        management_reason = "passive_by_absence_of_active_marker"
    if _has(kis_industry, "합성복제"):
        replication_method = "synthetic"
        replication_confidence = "high"
        replication_reason = "kis_explicit_synthetic_category"
    elif _has(kis_industry, "실물복제"):
        replication_method = "physical"
        replication_confidence = "high"
        replication_reason = "kis_explicit_physical_category"
    elif _has(kis_industry, "ACTIVE"):
        replication_method = "active_discretionary"
        replication_confidence = "high"
        replication_reason = "kis_explicit_active_category"
    elif _has(source.isu_name.upper(), "합성"):
        replication_method = "synthetic"
        replication_confidence = "medium"
        replication_reason = "krx_name_explicit_synthetic"
    elif management_style == "active":
        replication_method = "active_discretionary"
        replication_confidence = "medium"
        replication_reason = "active_name_implies_discretionary_replication"
    else:
        replication_method = "physical"
        replication_confidence = "medium"
        replication_reason = "physical_by_exclusion"

    if _has(text, "인버스", "INVERSE"):
        leverage_type = "inverse"
    elif _has(text, "레버리지", "2X"):
        leverage_type = "leveraged"
    else:
        leverage_type = "normal"

    hedged = bool(
        re.search(r"\([^)]*\bH\b[^)]*\)", source.isu_name.upper())
        or _has(text, "환헤지", "YEN HEDGED", "CURRENCY HEDGED")
    )
    if source.disclosure_currency_hedge:
        currency_hedge = source.disclosure_currency_hedge
        hedge_confidence = source.disclosure_confidence or "high"
        hedge_reason = "issuer_disclosure_override"
    elif hedged:
        currency_hedge = "hedged"
        hedge_confidence = "high"
        hedge_reason = "explicit_hedge_marker"
    elif region == "south_korea":
        currency_hedge = "not_applicable"
        hedge_confidence = "high"
        hedge_reason = "domestic_underlying"
    elif region == "global" and asset_class == "multi_asset":
        currency_hedge = "unknown"
        hedge_confidence = "low"
        hedge_reason = "multi_asset_requires_disclosure"
    else:
        currency_hedge = "unhedged"
        hedge_confidence = "medium"
        hedge_reason = "foreign_exposure_without_hedge_marker"

    strategy = _strategy(text, asset_class, subtype)
    asset_confidence = "medium" if asset_reason == "equity_by_exclusion" else "high"
    if component_profile["asset_class_signal"] == "corroborates":
        asset_confidence = "high"
    if fsc_signal == "corroborates":
        asset_confidence = "high"
    region_confidence = (
        "medium" if region_reason.startswith("domestic_by") else "high"
    )
    if component_profile["region_signal"] == "corroborates":
        region_confidence = "high"
    confidence = (
        "high"
        if asset_confidence == "high" and region_confidence == "high"
        else "medium"
    )
    reason_codes = [
        asset_reason,
        region_reason,
        management_reason,
        replication_reason,
        hedge_reason,
    ]
    if component_profile["asset_class_signal"] == "corroborates":
        reason_codes.append("kis_components_corroborate_asset_class")
    elif component_profile["asset_class_signal"] == "conflicts":
        reason_codes.append("kis_components_conflict_with_primary_asset_class")
    if fsc_signal == "corroborates":
        reason_codes.append("fsc_exact_type_corroborates_asset_class")
    elif fsc_signal == "conflicts":
        reason_codes.append("fsc_exact_type_conflicts_with_market_classification")
    if component_profile["region_signal"] == "corroborates":
        reason_codes.append("kis_components_corroborate_region")
    elif component_profile["region_signal"] == "conflicts":
        reason_codes.append("kis_components_conflict_with_primary_region")

    return {
        "asset_class": asset_class,
        "sub_asset_class": subtype,
        "region": region,
        "currency_hedge": currency_hedge,
        "currency_hedge_confidence": hedge_confidence,
        "management_style": management_style,
        "management_style_confidence": management_confidence,
        "replication_method": replication_method,
        "replication_confidence": replication_confidence,
        "leverage_type": leverage_type,
        "strategy": strategy,
        "classification_confidence": confidence,
        "dimension_confidence": {
            "asset_class": asset_confidence,
            "region": region_confidence,
            "currency_hedge": hedge_confidence,
            "management_style": management_confidence,
            "replication_method": replication_confidence,
        },
        "decision_reasons": {
            "asset_class": asset_reason,
            "region": region_reason,
            "currency_hedge": hedge_reason,
            "management_style": management_reason,
            "replication_method": replication_reason,
        },
        "component_profile": component_profile,
        "source_agreement": {
            "kis_components_asset_class": component_profile[
                "asset_class_signal"
            ],
            "kis_components_region": component_profile["region_signal"],
            "fsc_exact_type_asset_class": fsc_signal,
        },
        "reason_codes": reason_codes,
    }
