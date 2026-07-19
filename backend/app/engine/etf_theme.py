import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .educational_portfolio import (
    CandidateQuality,
    EducationalPortfolioInput,
    _product_sleeve,
    _score_candidates,
    calculate_target_allocation,
)
from .models import AccountType


class EtfThemeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1, le=23)
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
    benefits: tuple[str, ...] = Field(min_length=3, max_length=3)
    risks: tuple[str, ...] = Field(min_length=3, max_length=3)


class EtfThemeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=2, ge=2, le=2)
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

    account_type: AccountType
    isu_code: str
    isu_name: str
    sleeve: str
    quality: CandidateQuality
    fee_percent: Decimal | None = None
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
    account_type: AccountType
    status: str
    candidates: tuple[ThemeEtfCandidate, ...] = ()
    limitations: tuple[str, ...] = ()


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
    text = _normalized(" ".join((isu_name, kis_index_name, kis_industry_name)))
    matched: list[str] = []
    for theme in catalog.themes:
        if any(_contains_term(text, term) for term in theme.exclude_terms):
            continue
        if any(_contains_term(text, term) for term in theme.include_terms):
            matched.append(theme.theme_id)
    return tuple(matched)


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


def select_theme_etf_candidates(
    *,
    catalog: EtfThemeCatalog,
    theme: EtfThemeDefinition,
    products: list[dict[str, object]],
    kis_products_by_code: dict[str, dict[str, object]],
    component_snapshot_date: date | None,
    request: EducationalPortfolioInput,
    limit: int,
) -> ThemeCandidateEvaluation:
    if limit < 1 or limit > 5:
        raise ValueError("theme ETF candidate limit must be between 1 and 5")
    sleeves, _ = calculate_target_allocation(request)
    pool: list[dict[str, object]] = []
    for product in products:
        code = str(product.get("isu_code") or "")
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
        sleeve = _product_sleeve(product)
        if sleeve is None or sleeves.get(sleeve, Decimal("0")) <= 0:
            continue
        pool.append(product)

    if not pool:
        return ThemeCandidateEvaluation(
            theme_id=theme.theme_id,
            theme_name=theme.name,
            account_type=request.account_type,
            status="profile_or_data_unavailable",
            limitations=(
                "계좌 적격 유니버스와 투자성향 범위 안에서 제시할 테마 ETF가 없습니다.",
            ),
        )

    ranked = _score_candidates(pool)[:limit]
    candidates: list[ThemeEtfCandidate] = []
    for product, quality in ranked:
        code = str(product["isu_code"])
        snapshot = kis_products_by_code.get(code, {})
        holdings = normalize_kis_holdings(snapshot.get("components"))
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
                account_type=request.account_type,
                isu_code=code,
                isu_name=str(product["isu_name"]),
                sleeve=str(_product_sleeve(product)),
                quality=quality,
                fee_percent=_decimal(cost.get("kis_total_expense_ratio_percent")),
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
                    "account_specific_eligible_universe",
                    "theme_matched_from_etf_name_or_kis_index",
                    "quality_score_excludes_historical_return",
                    "kis_component_weights_preserved_as_reported",
                ),
            )
        )
    return ThemeCandidateEvaluation(
        theme_id=theme.theme_id,
        theme_name=theme.name,
        account_type=request.account_type,
        status="ok",
        candidates=tuple(candidates),
        limitations=(
            "교육용 비교 후보이며 매수 순위나 주문 지시가 아닙니다.",
            "한국투자증권 구성종목 배열이 비어 있는 ETF는 "
            "비중 근거를 표시하지 않습니다.",
        ),
    )
