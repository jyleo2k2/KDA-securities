import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .educational_portfolio import (
    CandidateQuality,
    _product_sleeve,
    _score_candidates,
)
from .models import AccountType


class RepresentativeCompany(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    theme_role: str = Field(min_length=1)
    plain_description: str = Field(min_length=1)
    representative_reason: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    as_of_date: date


class EtfThemeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1, le=21)
    theme_id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)
    include_terms: tuple[str, ...] = Field(min_length=1)
    exclude_terms: tuple[str, ...] = ()
    default_sleeve: str
    definition: str
    plain_summary: str
    exposure_segments: tuple[str, ...] = Field(min_length=1)
    performance_drivers: tuple[str, ...] = Field(min_length=1)
    one_line_analogy: str
    representative_companies: tuple[RepresentativeCompany, ...] = Field(
        min_length=3,
        max_length=3,
    )
    benefits: tuple[str, ...] = Field(min_length=3, max_length=3)
    risks: tuple[str, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique_representative_companies(self) -> "EtfThemeDefinition":
        names = [company.name.casefold() for company in self.representative_companies]
        if len(set(names)) != len(names):
            raise ValueError("representative company names must be unique per theme")
        return self


class EtfThemeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=3, ge=3, le=3)
    catalog_version: str
    as_of_date: date
    content_status: str
    source_urls: tuple[str, ...] = Field(min_length=1)
    themes: tuple[EtfThemeDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_theme_keys(self) -> "EtfThemeCatalog":
        if len({theme.number for theme in self.themes}) != len(self.themes):
            raise ValueError("ETF theme numbers must be unique")
        if len({theme.theme_id for theme in self.themes}) != len(self.themes):
            raise ValueError("ETF theme ids must be unique")
        return self


class KisComponentHolding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_code: str
    component_name: str
    weight_percent: Decimal = Field(gt=0, allow_inf_nan=False)


class ThemeEtfCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_type: AccountType | None = None
    isu_code: str
    isu_name: str
    sleeve: str
    quality: CandidateQuality
    fee_percent: Decimal | None = None
    average_daily_trading_volume: Decimal | None = None
    median_daily_trading_value_krw: Decimal | None = None
    median_net_assets_krw: Decimal | None = None
    median_abs_premium_discount_percent: Decimal | None = None
    tracking_error_percent: Decimal | None = None
    observation_count: int
    component_snapshot_date: date | None = None
    component_count: int
    reported_component_weight_percent: Decimal
    top_holdings: tuple[KisComponentHolding, ...] = ()
    reasons: tuple[str, ...]


class ThemeCandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    theme_id: str
    theme_name: str
    account_type: AccountType | None = None
    status: str
    candidates: tuple[ThemeEtfCandidate, ...] = ()
    limitations: tuple[str, ...] = ()


class ThemeClassificationMatch(BaseModel):
    """Explain one deterministic theme match without changing its rank or scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    theme_id: str = Field(pattern=r"^[a-z0-9_]+$")
    matched_terms: tuple[str, ...] = Field(min_length=1)
    matched_sources: tuple[str, ...] = Field(min_length=1)
    is_ambiguous: bool


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.upper()).strip()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalized(term)
    starts_with_single_hangul_word = re.match(
        r"^[가-힣](?:\s|[·-])",
        normalized_term,
    )
    if starts_with_single_hangul_word:
        pattern = rf"(?<![가-힣]){re.escape(normalized_term)}"
        return re.search(pattern, text) is not None
    is_short_ascii = (
        normalized_term.isascii()
        and normalized_term.isalnum()
        and len(normalized_term) <= 3
    )
    if is_short_ascii:
        pattern = rf"(?<![A-Z0-9]){re.escape(normalized_term)}(?![A-Z0-9])"
        return re.search(pattern, text) is not None
    return normalized_term in text


def resolve_theme(
    catalog: EtfThemeCatalog, message: str
) -> EtfThemeDefinition | None:
    text = _normalized(message)
    matches = [
        theme
        for theme in catalog.themes
        if any(_contains_term(text, alias) for alias in (theme.name, *theme.aliases))
    ]
    if not matches:
        number_match = re.search(r"(?<!\d)(\d{1,2})\s*번\s*(?:테마)?", message)
        if number_match is not None:
            number = int(number_match.group(1))
            return next(
                (theme for theme in catalog.themes if theme.number == number),
                None,
            )
        return None
    return max(
        matches,
        key=lambda theme: max(len(alias) for alias in (theme.name, *theme.aliases)),
    )


def classify_etf_themes(
    catalog: EtfThemeCatalog,
    *,
    isu_name: str,
    kis_index_name: str = "",
    kis_industry_name: str = "",
) -> tuple[str, ...]:
    return tuple(
        match.theme_id
        for match in classify_etf_theme_matches(
            catalog,
            isu_name=isu_name,
            kis_index_name=kis_index_name,
            kis_industry_name=kis_industry_name,
        )
    )


def classify_etf_theme_matches(
    catalog: EtfThemeCatalog,
    *,
    isu_name: str,
    kis_index_name: str = "",
    kis_industry_name: str = "",
) -> tuple[ThemeClassificationMatch, ...]:
    """Return the same many-to-many matches with auditable term/source evidence."""

    source_texts = (
        ("isu_name", _normalized(isu_name)),
        ("kis_index_name", _normalized(kis_index_name)),
        ("kis_industry_name", _normalized(kis_industry_name)),
    )
    text = _normalized(" ".join((isu_name, kis_index_name, kis_industry_name)))
    matched: list[tuple[EtfThemeDefinition, tuple[str, ...]]] = []
    for theme in catalog.themes:
        if any(_contains_term(text, term) for term in theme.exclude_terms):
            continue
        matched_terms = tuple(
            term for term in theme.include_terms if _contains_term(text, term)
        )
        if matched_terms:
            matched.append((theme, matched_terms))

    is_ambiguous = len(matched) > 1
    results: list[ThemeClassificationMatch] = []
    for theme, matched_terms in matched:
        matched_sources = tuple(
            source
            for source, source_text in source_texts
            if source_text
            and any(_contains_term(source_text, term) for term in matched_terms)
        )
        results.append(
            ThemeClassificationMatch(
                theme_id=theme.theme_id,
                matched_terms=matched_terms,
                matched_sources=matched_sources or ("combined_fields",),
                is_ambiguous=is_ambiguous,
            )
        )
    return tuple(results)


def normalize_kis_holdings(rows: object) -> tuple[KisComponentHolding, ...]:
    if not isinstance(rows, list):
        return ()
    holdings: list[KisComponentHolding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("hts_kor_isnm") or "").strip()
        if not name:
            continue
        weight = _decimal(row.get("etf_cnfg_issu_rlim"))
        if weight is None or weight <= 0:
            continue
        holdings.append(
            KisComponentHolding(
                component_code=str(row.get("stck_shrn_iscd") or "").strip(),
                component_name=name,
                weight_percent=weight,
            )
        )
    return tuple(
        sorted(
            holdings,
            key=lambda holding: (-holding.weight_percent, holding.component_code),
        )
    )


def _decimal(value: object) -> Decimal | None:
    if value in {None, "", "-"}:
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _rank_theme_products(
    products: list[dict[str, object]],
    *,
    by_trading_volume: bool = False,
) -> tuple[list[tuple[dict[str, object], CandidateQuality]], int]:
    quality_by_code = {
        str(product["isu_code"]): quality
        for product, quality in _score_candidates(products)
    }
    rankable: list[
        tuple[
            dict[str, object],
            CandidateQuality,
            Decimal,
            Decimal,
            Decimal | None,
        ]
    ] = []
    excluded_count = 0
    for product in products:
        metrics = product.get("implementation_metrics")
        cost = product.get("cost")
        if not isinstance(metrics, dict):
            metrics = {}
        if not isinstance(cost, dict):
            cost = {}
        liquidity = _decimal(
            metrics.get("average_daily_trading_volume")
            if by_trading_volume
            else metrics.get("median_daily_trading_value_krw")
        )
        fee = _decimal(cost.get("kis_total_expense_ratio_percent"))
        if liquidity is None or fee is None:
            excluded_count += 1
            continue
        code = str(product["isu_code"])
        rankable.append(
            (
                product,
                quality_by_code[code],
                liquidity,
                fee,
                _decimal(metrics.get("median_net_assets_krw")),
            )
        )
    rankable.sort(
        key=lambda item: (
            -item[2],
            item[3],
            item[4] is None,
            -(item[4] or Decimal("0")),
            str(item[0]["isu_code"]),
        )
    )
    return [(product, quality) for product, quality, *_ in rankable], excluded_count


def select_theme_etf_candidates(
    *,
    catalog: EtfThemeCatalog,
    theme: EtfThemeDefinition,
    products: list[dict[str, object]],
    kis_products_by_code: dict[str, dict[str, object]],
    component_snapshot_date: date | None,
    limit: int,
    allowed_isu_codes: frozenset[str] | None = None,
    ordered_candidate_groups: tuple[frozenset[str], ...] | None = None,
) -> ThemeCandidateEvaluation:
    if limit < 1 or limit > 5:
        raise ValueError("theme ETF candidate limit must be between 1 and 5")
    pool: list[dict[str, object]] = []
    for product in products:
        code = str(product.get("isu_code") or "")
        if allowed_isu_codes is not None:
            if code in allowed_isu_codes:
                pool.append(product)
            continue
        snapshot = kis_products_by_code.get(code, {})
        price = snapshot.get("price") if isinstance(snapshot, dict) else None
        if not isinstance(price, dict):
            price = {}
        theme_ids = classify_etf_themes(
            catalog,
            isu_name=str(product.get("isu_name") or ""),
            kis_index_name=str(price.get("etf_rprs_bstp_kor_isnm") or ""),
            kis_industry_name=str(price.get("bstp_kor_isnm") or ""),
        )
        if theme.theme_id not in theme_ids:
            continue
        pool.append(product)

    if not pool:
        return ThemeCandidateEvaluation(
            theme_id=theme.theme_id,
            theme_name=theme.name,
            status="data_unavailable",
            limitations=(
                "통합 ETF 상품 데이터에서 제시할 테마 ETF가 없습니다.",
            ),
        )

    if ordered_candidate_groups is None:
        ranked, excluded_count = _rank_theme_products(pool)
        ranked = ranked[:limit]
    else:
        ranked = []
        excluded_count = 0
        for group in ordered_candidate_groups[:limit]:
            group_pool = [
                product
                for product in pool
                if str(product.get("isu_code") or "") in group
            ]
            group_ranked, group_excluded = _rank_theme_products(
                group_pool,
                by_trading_volume=True,
            )
            excluded_count += group_excluded
            if group_ranked:
                ranked.append(group_ranked[0])
        expected_count = min(limit, len(ordered_candidate_groups))
        if len(ranked) != expected_count:
            return ThemeCandidateEvaluation(
                theme_id=theme.theme_id,
                theme_name=theme.name,
                status="data_unavailable",
                limitations=(
                    "금·은·구리 중 거래량과 운용보수를 모두 확인할 수 없는 "
                    "실물 슬롯이 있습니다.",
                ),
            )
    if not ranked:
        return ThemeCandidateEvaluation(
            theme_id=theme.theme_id,
            theme_name=theme.name,
            status="data_unavailable",
            limitations=(
                "거래대금과 총보수가 모두 확인되는 테마 ETF가 없습니다.",
            ),
        )
    candidates: list[ThemeEtfCandidate] = []
    for product, quality in ranked:
        code = str(product["isu_code"])
        snapshot = kis_products_by_code.get(code, {})
        holdings = normalize_kis_holdings(snapshot.get("components"))
        classification = product.get("classification")
        if (
            isinstance(classification, dict)
            and classification.get("region") != "south_korea"
        ):
            holdings = ()
        metrics = product.get("implementation_metrics")
        cost = product.get("cost")
        if not isinstance(metrics, dict):
            metrics = {}
        if not isinstance(cost, dict):
            cost = {}
        tracking = _decimal(metrics.get("kis_current_tracking_error_percent"))
        if tracking is None:
            tracking = _decimal(metrics.get("tracking_error_proxy_percent"))
        candidates.append(
            ThemeEtfCandidate(
                isu_code=code,
                isu_name=str(product["isu_name"]),
                sleeve=_product_sleeve(product) or "unclassified",
                quality=quality,
                fee_percent=_decimal(cost.get("kis_total_expense_ratio_percent")),
                average_daily_trading_volume=_decimal(
                    metrics.get("average_daily_trading_volume")
                ),
                median_daily_trading_value_krw=_decimal(
                    metrics.get("median_daily_trading_value_krw")
                ),
                median_net_assets_krw=_decimal(metrics.get("median_net_assets_krw")),
                median_abs_premium_discount_percent=_decimal(
                    metrics.get("median_abs_premium_discount_percent")
                ),
                tracking_error_percent=tracking,
                observation_count=int(product.get("observation_count") or 0),
                component_snapshot_date=component_snapshot_date,
                component_count=len(holdings),
                reported_component_weight_percent=sum(
                    (holding.weight_percent for holding in holdings), Decimal("0")
                ),
                top_holdings=holdings[:10],
                reasons=(
                    "common_cross_account_universe",
                    (
                        "theme_matched_from_research_allowlist"
                        if allowed_isu_codes is not None
                        else "theme_matched_from_etf_name_or_kis_index"
                    ),
                    (
                        "ranked_within_ordered_group_by_average_volume_desc"
                        if ordered_candidate_groups is not None
                        else "ranked_by_median_daily_trading_value_desc"
                    ),
                    "lower_fee_breaks_liquidity_ties",
                    "kis_component_weights_preserved_as_reported",
                ),
            )
        )
    return ThemeCandidateEvaluation(
        theme_id=theme.theme_id,
        theme_name=theme.name,
        status="ok",
        candidates=tuple(candidates),
        limitations=tuple(
            item
            for item in (
                "교육용 비교 후보이며 매수 순위나 주문 지시가 아닙니다.",
                (
                    "거래량 또는 운용보수가 없는 ETF는 순위에서 제외했습니다."
                    if ordered_candidate_groups is not None
                    else "거래대금 또는 총보수가 없는 ETF는 순위에서 제외했습니다."
                )
                if excluded_count
                else None,
                "한국투자증권 구성종목 배열이 비어 있는 ETF는 "
                "비중 근거를 표시하지 않습니다.",
            )
            if item is not None
        ),
    )
