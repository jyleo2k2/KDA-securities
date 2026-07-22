import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from .engine.etf_theme import EtfThemeCatalog, EtfThemeDefinition, resolve_theme

DEFAULT_THEME_CATALOG_PATH = Path("data/reference/etf_theme_catalog.json")
DEFAULT_THEME_PRODUCT_ALLOWLIST_PATH = Path(
    "data/reference/etf_theme_product_allowlist.json"
)
DEFAULT_GOLD_COMMODITIES_POLICY_PATH = Path(
    "data/reference/gold_commodities_etf_policy.json"
)
DEFAULT_KIS_CACHE_ROOT = Path("data/cache/kis")


@dataclass(frozen=True)
class EtfThemeProductPolicy:
    as_of_date: date
    source_document: str
    source_text_sha256: str
    source_urls: tuple[str, ...]
    deferred_theme_ids: frozenset[str]
    allowed_codes_by_theme: dict[str, frozenset[str]]


@dataclass(frozen=True)
class CommodityEtfCandidatePolicy:
    isu_code: str
    isu_name: str
    average_daily_trading_volume: int
    average_daily_trading_value_krw: Decimal
    fee_percent: Decimal
    benchmark_name: str

    def product_payload(self) -> dict[str, Any]:
        return {
            "isu_code": self.isu_code,
            "isu_name": self.isu_name,
            "classification": {
                "asset_class": "commodity",
                "strategy": "physical_commodity",
                "region": "south_korea",
            },
            "cost": {
                "kis_total_expense_ratio_percent": str(self.fee_percent),
            },
            "implementation_metrics": {
                "average_daily_trading_volume": self.average_daily_trading_volume,
                "average_daily_trading_value_krw": str(
                    self.average_daily_trading_value_krw
                ),
                "median_daily_trading_value_krw": str(
                    self.average_daily_trading_value_krw
                ),
                "benchmark_name": self.benchmark_name,
            },
            "observation_count": 10,
        }


@dataclass(frozen=True)
class CommodityEtfSelectionSlot:
    slot_id: str
    slot_label: str
    exposure_label: str
    candidates: tuple[CommodityEtfCandidatePolicy, ...]


@dataclass(frozen=True)
class CommodityEtfSelectionPolicy:
    as_of_date: date
    theme_id: str
    source_url: str
    metric_basis: str
    ranking_rule: str
    slots: tuple[CommodityEtfSelectionSlot, ...]

    @property
    def allowed_codes(self) -> frozenset[str]:
        return frozenset(
            candidate.isu_code
            for slot in self.slots
            for candidate in slot.candidates
        )

    @property
    def ordered_candidate_groups(self) -> tuple[frozenset[str], ...]:
        return tuple(
            frozenset(candidate.isu_code for candidate in slot.candidates)
            for slot in self.slots
        )

    @property
    def products(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            candidate.product_payload()
            for slot in self.slots
            for candidate in slot.candidates
        )

    def exposure_label(self, isu_code: str) -> str | None:
        for slot in self.slots:
            if any(candidate.isu_code == isu_code for candidate in slot.candidates):
                return slot.exposure_label
        return None


class EtfThemeRepository:
    """Read stable theme definitions and the latest full KIS ETF snapshot."""

    def __init__(
        self,
        *,
        catalog: EtfThemeCatalog,
        kis_products_by_code: dict[str, dict[str, Any]] | None = None,
        component_snapshot_date: date | None = None,
        catalog_path: Path = DEFAULT_THEME_CATALOG_PATH,
        kis_snapshot_path: Path | None = None,
        product_policy: EtfThemeProductPolicy | None = None,
        product_policy_path: Path | None = None,
        commodity_policy: CommodityEtfSelectionPolicy | None = None,
        commodity_policy_path: Path | None = None,
    ) -> None:
        self.catalog = catalog
        self.kis_products_by_code = kis_products_by_code or {}
        self.component_snapshot_date = component_snapshot_date
        self.catalog_path = catalog_path
        self.kis_snapshot_path = kis_snapshot_path
        self.product_policy = product_policy
        self.product_policy_path = product_policy_path
        self.commodity_policy = commodity_policy
        self.commodity_policy_path = commodity_policy_path

    @classmethod
    def from_local_cache(
        cls,
        *,
        catalog_path: Path = DEFAULT_THEME_CATALOG_PATH,
        kis_cache_root: Path = DEFAULT_KIS_CACHE_ROOT,
        product_policy_path: Path = DEFAULT_THEME_PRODUCT_ALLOWLIST_PATH,
        commodity_policy_path: Path = DEFAULT_GOLD_COMMODITIES_POLICY_PATH,
    ) -> "EtfThemeRepository":
        catalog = EtfThemeCatalog.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        product_policy = _load_product_policy(product_policy_path, catalog)
        commodity_policy = _load_commodity_policy(
            commodity_policy_path,
            catalog,
            product_policy,
        )
        snapshot_paths = sorted(kis_cache_root.glob("etf_snapshot_*.json"))
        if not snapshot_paths:
            return cls(
                catalog=catalog,
                catalog_path=catalog_path,
                product_policy=product_policy,
                product_policy_path=product_policy_path,
                commodity_policy=commodity_policy,
                commodity_policy_path=commodity_policy_path,
            )

        snapshot_path = snapshot_paths[-1]
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        products = payload.get("products")
        if not isinstance(products, list):
            raise ValueError("KIS ETF snapshot must contain a products array")
        by_code = {
            str(product["isu_code"]): product
            for product in products
            if isinstance(product, dict) and product.get("isu_code")
        }
        snapshot_date = date.fromisoformat(str(payload["snapshot_date"]))
        return cls(
            catalog=catalog,
            kis_products_by_code=by_code,
            component_snapshot_date=snapshot_date,
            catalog_path=catalog_path,
            kis_snapshot_path=snapshot_path,
            product_policy=product_policy,
            product_policy_path=product_policy_path,
            commodity_policy=commodity_policy,
            commodity_policy_path=commodity_policy_path,
        )

    def list(self) -> tuple[EtfThemeDefinition, ...]:
        return self.catalog.themes

    def get(self, theme_id: str) -> EtfThemeDefinition | None:
        return next(
            (theme for theme in self.catalog.themes if theme.theme_id == theme_id),
            None,
        )

    def resolve(self, message: str) -> EtfThemeDefinition | None:
        return resolve_theme(self.catalog, message)

    def allowed_product_codes(self, theme_id: str) -> frozenset[str] | None:
        if self.product_policy is None:
            return None
        return self.product_policy.allowed_codes_by_theme.get(theme_id)

    def commodity_selection_policy(
        self, theme_id: str
    ) -> CommodityEtfSelectionPolicy | None:
        if self.commodity_policy is None or self.commodity_policy.theme_id != theme_id:
            return None
        return self.commodity_policy


def _required_decimal(value: object, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"commodity ETF policy has invalid {field}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"commodity ETF policy has invalid {field}")
    return parsed


def _load_commodity_policy(
    path: Path,
    catalog: EtfThemeCatalog,
    product_policy: EtfThemeProductPolicy | None,
) -> CommodityEtfSelectionPolicy | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    theme_id = str(payload.get("theme_id") or "").strip()
    if theme_id not in {theme.theme_id for theme in catalog.themes}:
        raise ValueError("commodity ETF policy has an unknown theme_id")
    slots_payload = payload.get("slots")
    if not isinstance(slots_payload, list) or not slots_payload:
        raise ValueError("commodity ETF policy must define slots")
    slots: list[CommodityEtfSelectionSlot] = []
    seen_slot_ids: set[str] = set()
    seen_codes: set[str] = set()
    for slot_payload in slots_payload:
        if not isinstance(slot_payload, dict):
            raise ValueError("commodity ETF policy slot must be an object")
        slot_id = str(slot_payload.get("slot_id") or "").strip()
        slot_label = str(slot_payload.get("slot_label") or "").strip()
        exposure_label = str(slot_payload.get("exposure_label") or "").strip()
        if not slot_id or not slot_label or not exposure_label:
            raise ValueError("commodity ETF policy slot is incomplete")
        if slot_id in seen_slot_ids:
            raise ValueError("commodity ETF policy has duplicate slots")
        seen_slot_ids.add(slot_id)
        candidates_payload = slot_payload.get("candidates")
        if not isinstance(candidates_payload, list) or not candidates_payload:
            raise ValueError("commodity ETF policy slot must contain candidates")
        candidates: list[CommodityEtfCandidatePolicy] = []
        for candidate_payload in candidates_payload:
            if not isinstance(candidate_payload, dict):
                raise ValueError("commodity ETF candidate must be an object")
            code = str(candidate_payload.get("isu_code") or "").strip()
            name = str(candidate_payload.get("isu_name") or "").strip()
            benchmark = str(candidate_payload.get("benchmark_name") or "").strip()
            try:
                volume = int(candidate_payload["average_daily_trading_volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "commodity ETF candidate has invalid trading volume"
                ) from exc
            if not code or not name or not benchmark or volume < 0:
                raise ValueError("commodity ETF candidate is incomplete")
            if code in seen_codes:
                raise ValueError("commodity ETF policy has duplicate product codes")
            seen_codes.add(code)
            candidates.append(
                CommodityEtfCandidatePolicy(
                    isu_code=code,
                    isu_name=name,
                    average_daily_trading_volume=volume,
                    average_daily_trading_value_krw=_required_decimal(
                        candidate_payload.get("average_daily_trading_value_krw"),
                        field="average_daily_trading_value_krw",
                    ),
                    fee_percent=_required_decimal(
                        candidate_payload.get("fee_percent"),
                        field="fee_percent",
                    ),
                    benchmark_name=benchmark,
                )
            )
        slots.append(
            CommodityEtfSelectionSlot(
                slot_id=slot_id,
                slot_label=slot_label,
                exposure_label=exposure_label,
                candidates=tuple(candidates),
            )
        )
    policy = CommodityEtfSelectionPolicy(
        as_of_date=date.fromisoformat(str(payload["as_of_date"])),
        theme_id=theme_id,
        source_url=str(payload["source_url"]),
        metric_basis=str(payload["metric_basis"]),
        ranking_rule=str(payload["ranking_rule"]),
        slots=tuple(slots),
    )
    if not policy.source_url.startswith("https://"):
        raise ValueError("commodity ETF policy source_url must use https")
    if product_policy is not None:
        allowed = product_policy.allowed_codes_by_theme.get(theme_id)
        if allowed != policy.allowed_codes:
            raise ValueError(
                "commodity ETF policy codes must match the theme allowlist"
            )
    return policy


def _load_product_policy(
    path: Path,
    catalog: EtfThemeCatalog,
) -> EtfThemeProductPolicy | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    restricted = payload.get("restricted_themes")
    if not isinstance(restricted, dict):
        raise ValueError("ETF theme product allowlist must define restricted_themes")
    deferred = payload.get("deferred_themes")
    if not isinstance(deferred, list) or not all(
        isinstance(item, str) for item in deferred
    ):
        raise ValueError("ETF theme product allowlist must define deferred_themes")
    known_theme_ids = {theme.theme_id for theme in catalog.themes}
    unknown_theme_ids = set(restricted) - known_theme_ids
    deferred_theme_ids = frozenset(deferred)
    unknown_theme_ids.update(deferred_theme_ids - known_theme_ids)
    if unknown_theme_ids:
        raise ValueError(
            "ETF theme product allowlist contains unknown themes: "
            + ", ".join(sorted(unknown_theme_ids))
        )
    overlap = set(restricted) & deferred_theme_ids
    if overlap:
        raise ValueError(
            "ETF theme product allowlist cannot restrict deferred themes: "
            + ", ".join(sorted(overlap))
        )
    missing_theme_ids = known_theme_ids - set(restricted) - deferred_theme_ids
    if missing_theme_ids:
        raise ValueError(
            "ETF theme product allowlist does not classify themes: "
            + ", ".join(sorted(missing_theme_ids))
        )
    allowed_codes_by_theme: dict[str, frozenset[str]] = {}
    for theme_id, products in restricted.items():
        if not isinstance(products, list):
            raise ValueError(f"ETF theme allowlist for {theme_id} must be an array")
        codes: list[str] = []
        for product in products:
            if not isinstance(product, dict):
                raise ValueError(
                    f"ETF theme allowlist for {theme_id} has an invalid product"
                )
            code = str(product.get("isu_code") or "").strip()
            name = str(product.get("isu_name") or "").strip()
            if not code or not name:
                raise ValueError(
                    f"ETF theme allowlist for {theme_id} has an incomplete product"
                )
            codes.append(code)
        if len(codes) != len(set(codes)):
            raise ValueError(
                f"ETF theme allowlist for {theme_id} has duplicate codes"
            )
        if len(codes) < 3:
            raise ValueError(
                f"ETF theme allowlist for {theme_id} must contain at least 3 products"
            )
        allowed_codes_by_theme[theme_id] = frozenset(codes)
    return EtfThemeProductPolicy(
        as_of_date=date.fromisoformat(str(payload["as_of_date"])),
        source_document=str(payload["source_document"]),
        source_text_sha256=str(payload["source_text_sha256"]),
        source_urls=tuple(str(item) for item in payload.get("source_urls", [])),
        deferred_theme_ids=deferred_theme_ids,
        allowed_codes_by_theme=allowed_codes_by_theme,
    )


@lru_cache(maxsize=1)
def get_default_etf_theme_repository() -> EtfThemeRepository:
    return EtfThemeRepository.from_local_cache()
